from database import Database
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
import json

# Remove timestamps from here, fill them in the DB directly when adding messages
# Add AI prompt to iterate on goal so that GOAL is SMART.
# stop backfilling at startup, trigger on close of chat?
# option to delete goals
# 

class AccountabilityAI:
    def __init__(self, db_path: str = "accountability.db"):
        """
        Initialize the accountability coach with API configuration and loads user's goals and conversation history.
        """
        load_dotenv()
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.db = Database(db_path)

        with self.db as db:
            recent = db.get_uncleaned_logs(limit=50)
            self.messages: List[Dict[str, Any]] = recent[:]
            self.goals = db.get_goals()

        self.system_prompt = """
        You are AccountabilityAI — a data-driven productivity coach and advisor.
        Your role is to help the user stay on track with their goals, reflect honestly on their progress, and diagnose the root causes of procrastination or avoidance when a pattern becomes clear. You are not a generic assistant; you are a coach that balances unflinching honesty with practical, adaptive solutions.

        You are given:
        The user's current goals (SMART format where possible).
        Cleaned logs (summaries of progress).
        Uncleaned logs (recent chat messages for conversational continuity).

        Core behaviors:
        Keep the user accountable. Reference their goals and past progress directly. If they are falling behind, call it out honestly.
        Offer constructive coaching. Don't just criticize — suggest practical, evidence-based techniques (chunking, scheduling, reframing) tailored to the user's situation.
        Adapt to context. If the user reports low energy, stress, or other personal factors, adjust your recommendations appropriately instead of treating them like a machine.
        Diagnose patterns. Notice repeated failures, delays, or contradictions over time. When a pattern emerges, ask probing questions to uncover root causes (motivation, distraction, fear of failure).
        Promote reflection. Point out inconsistencies between what the user says and what they actually do, encouraging self-awareness.
        Foster partnership. Treat the relationship as collaborative: the user provides personal context, you provide analysis, structure, and strategy.
        Never invent goals. Only use goals explicitly provided in the context object.

        Tone:
        Direct, candid, and realistic.
        Not artificially positive or "rah-rah."
        Supportive, but not indulgent — you challenge the user when they avoid responsibility.
        Conversational and personal, but concise — avoid long essays unless diagnosing a deeper pattern.
        """
        self.backfill_cleaned_logs(cutoff_hour=4)

    def call_ai_model(self, prompt: str) -> str:
        """
        Generate response using Gemini AI model with the given prompt.
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Error generating response: {str(e)}")

    def _make_timestamp(self) -> str:
        """Generate current UTC timestamp for message tracking."""
        return datetime.utcnow().isoformat()

    def generate_reply(self, user_message: str) -> str:
        """
        Generate a coaching response considering user's goals, progress history, and recent conversations.
        Stores both user messages and AI responses for continuous progress tracking.
        """
        ts_user = self._make_timestamp()
        with self.db as db:
            goals = db.get_goals()
            cleaned_logs = db.get_cleaned_logs()
            db.add_message("user", user_message, ts_user)

        self.messages.append({"role": "user", "content": user_message, "timestamp": ts_user})

        # Format goals and progress history for AI context
        goals_text = ""
        for g in goals:
            goals_text += f"- {g['name']}: {g['description']}\n"

        cleaned_text = ""
        for c in cleaned_logs:
            cleaned_text += f"- (goal_id={c['goal_id']}) {c['date']}: {c['summary']}\n"

        convo_text = ""
        for m in self.messages[-50:]:
            convo_text += f"[{m.get('timestamp','')}] {m['role']}: {m['content']}\n"

        full_prompt = (
            f"{self.system_prompt}\n\n"
            f"Context - Goals:\n{goals_text}\n"
            f"Context - Cleaned Logs:\n{cleaned_text}\n"
            f"Recent Conversation:\n{convo_text}\n\n"
            "Assistant:"
        )

        # Call model
        reply = self.call_ai_model(full_prompt)

        # Persist assistant reply with timestamp and append to memory
        ts_ai = self._make_timestamp()
        with self.db as db:
            db.add_message("assistant", reply, ts_ai)

        self.messages.append({"role": "assistant", "content": reply, "timestamp": ts_ai})

        return reply

    def run_chat(self):
        """
        Run the chat interface.
        """
        print("💬 Accountability AI Chat (type 'quit' to exit)\n")

        while True:
            user_input = input("You: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                break

            try:
                reply = self.generate_reply(user_input)
                print("AI:", reply)
            except Exception as e:
                print(f"\nError: {str(e)}")
                print("Please try again in a moment.")
                break

    def _day_start_from_timestamp(self, ts: str, cutoff_hour: int = 4) -> date:
        """
        Convert an ISO timestamp string to the 'day_start' date according to cutoff_hour.
        E.g., cutoff_hour=4 means day runs from 04:01 of day D -> 04:00 of day D+1.
        Returns the date D as a date() object.
        """
        dt = datetime.fromisoformat(ts)
        # If time is before or equal to cutoff_hour:00 (i.e., 04:00), attribute it to previous logical day
        cutoff = time(hour=cutoff_hour, minute=0, second=0)
        if dt.time() <= cutoff:
            # belongs to previous day
            return (dt.date() - timedelta(days=1))
        return dt.date()

    def _day_window_iso(self, day_start: date, cutoff_hour: int = 4) -> (str, str):
        """
        Given a day_start date D, return (start_iso, end_iso) for that day's activity window:
        start = D at 04:00:01 UTC (inclusive),
        end = (D + 1 day) at 04:00:01 UTC (exclusive).
        Using .isoformat() strings for DB queries.
        """
        # define start at D @ 04:00:00 (we'll include >= start and < end)
        start_dt = datetime.combine(day_start, time(hour=cutoff_hour, minute=0, second=0))
        end_dt = start_dt + timedelta(days=1)
        # Use ISO format (no timezone)
        return (start_dt.isoformat(), end_dt.isoformat())

    def summarize_logs_for_day(self, logs: List[Dict[str, Any]], goals: List[Dict[str, Any]], day_start: date) -> List[Dict[str, Any]]:
        """
        Ask the LLM to summarize a day's raw logs into per-goal cleaned summaries.
        Returns a list of dicts: [{"goal_id": <id or None>, "summary": "<text>"}, ...]
        - For each goal in `goals`, the model should produce a short summary (or an empty string).
        - If the model can't return structured JSON, we fallback to a general summary with goal_id=None.
        """
        # Build a compact prompt: provide goals and the day's messages, ask for JSON output.
        goals_text = "\n".join([f"{g['id']}: {g['name']} - {g['description']}" for g in goals]) if goals else "[]"
        logs_text = "\n".join([f"[{l['timestamp']}] {l['role']}: {l['content']}" for l in logs])

        prompt = (
            f"You are a summarization assistant. For the date {day_start.isoformat()}, given the user's goals and "
            f"the day's raw conversation logs, produce a JSON array of objects mapping goal_id -> concise summary "
            f"for that goal's progress that day. If no progress for a goal, provide an empty string for summary.\n\n"
            f"Goals (id: name - desc):\n{goals_text}\n\n"
            f"Raw logs:\n{logs_text}\n\n"
            "Return EXACTLY valid JSON like: "
            '[{"goal_id": 1, "summary": "Did work on X"}, {"goal_id": 2, "summary": ""}, {"goal_id": null, "summary": "General notes..."}]\n'
            "Include at least one object with goal_id === null for any general, non-goal-specific notes if appropriate."
        )

        # Call LLM (use your existing wrapper)
        try:
            raw = self.call_ai_model(prompt)
        except Exception as e:
            # On failure, fallback to a single general summary
            general = "Failed to generate structured summary: " + str(e)
            return [{"goal_id": None, "summary": general}]

        # Attempt to parse JSON from the model's output
        parsed = None
        # Try to locate first JSON substring if the model prepends commentary
        try:
            # sanitize and extract JSON
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end != -1 and end > start:
                json_text = raw[start:end]
                parsed = json.loads(json_text)
        except Exception:
            parsed = None

        if isinstance(parsed, list):
            # normalize items
            results = []
            for item in parsed:
                # accept keys 'goal_id' and 'summary' or fallbacks
                gid = item.get("goal_id") if isinstance(item, dict) else None
                summ = item.get("summary") if isinstance(item, dict) else str(item)
                results.append({"goal_id": gid, "summary": summ})
            return results

        # fallback: create a single general summary using raw as content
        return [{"goal_id": None, "summary": raw.strip()}]

    def backfill_cleaned_logs(self, cutoff_hour: int = 4) -> List[Dict[str, Any]]:
        """
        Backfill missing cleaned logs from the DB using lazy summarization.
        Workflow:
          - Determine earliest uncleaned log and latest cleaned day.
          - Compute list of day_start dates to ensure are covered (for days that have logs).
          - For each missing day, fetch raw logs between start/end; if logs exist, summarize and insert cleaned rows.
          - If no logs exist for that day, optionally insert a 'no activity' cleaned row with goal_id=None (skip if you prefer).
        Returns a list of inserted cleaned-log metadata.
        """
        inserted = []
        with self.db as db:
            # earliest raw log timestamp (iso) and latest cleaned day (YYYY-MM-DD)
            earliest_iso = db.get_earliest_uncleaned_timestamp()
            latest_cleaned_day = db.get_latest_cleaned_day()  # string YYYY-MM-DD or None

            if not earliest_iso:
                return inserted  # nothing to do

            # Compute start and end range
            first_day = self._day_start_from_timestamp(earliest_iso, cutoff_hour=cutoff_hour)
            if latest_cleaned_day:
                start_day = datetime.fromisoformat(latest_cleaned_day).date() + timedelta(days=1)
            else:
                start_day = first_day

            now_iso = datetime.utcnow().isoformat()
            last_day = self._day_start_from_timestamp(now_iso, cutoff_hour=cutoff_hour)

            # Process each day within the database context
            day = start_day
            while day <= last_day:
                start_iso, end_iso = self._day_window_iso(day, cutoff_hour=cutoff_hour)
                logs = db.get_uncleaned_logs_between(start_iso, end_iso)
                
                if logs:
                    goals = db.get_goals()
                    summaries = self.summarize_logs_for_day(logs, goals, day)
                    
                    for s in summaries:
                        gid = s.get("goal_id")
                        summary_text = s.get("summary", "").strip()
                        
                        if summary_text == "":
                            db.add_cleaned_log(gid, "(no progress noted)", date=day.isoformat())
                            inserted.append({"day": day.isoformat(), "goal_id": gid, "summary": "(no progress noted)"})
                        else:
                            db.add_cleaned_log(gid, summary_text, date=day.isoformat())
                            inserted.append({"day": day.isoformat(), "goal_id": gid, "summary": summary_text})
                
                day = day + timedelta(days=1)

        return inserted
