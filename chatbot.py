from database import Database
import os
from dotenv import load_dotenv
import google.generativeai as genai

class AccountabilityAI:
    def __init__(self):
        """
        Initialize the AI with environment configuration and system prompt.
        """
        # Load and configure API key
        load_dotenv()
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        self.db = Database()
        self.messages = []
        
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

        Example style:
        User: "I'll start the report tomorrow."
        AI: "You've delayed this twice already. What's blocking you? At the rate we're going you won't be able to stay on track for your goal.
        """

    def call_ai_model(self, prompt: str) -> str:
        """
        Make an API call to Google's Gemini AI model.
        """
        response = self.model.generate_content(prompt)
        return response.text

    def generate_reply(self, user_message: str) -> str:
        """
        Generate a reply to the user's message using context from the database.
        """
        # Add user message to conversation history
        self.messages.append({"role": "user", "content": user_message})
        
        # Get context from database
        with self.db as db:
            goals = db.get_goals()
            cleaned_logs = db.get_cleaned_logs()
            recent_logs = db.get_uncleaned_logs(limit=25)
            db.add_uncleaned_log(user_message)

        # Build the prompt
        context = f"Goals:\n{goals}\n\nPast Activities:\n{cleaned_logs}\n\nRecent Activities:\n{recent_logs}"
        conversation = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.messages])
        full_prompt = f"{self.system_prompt}\n\nContext:\n{context}\n\nConversation:\n{conversation}\n\nAssistant:"
        
        # Get and store AI's reply
        reply = self.call_ai_model(full_prompt)
        self.messages.append({"role": "assistant", "content": reply})
        
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

            reply = self.generate_reply(user_input)
            print("AI:", reply)
