from database import Database
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from typing import List, Dict, Any

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
        self.model = genai.GenerativeModel('gemini-2.0-flash')
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

