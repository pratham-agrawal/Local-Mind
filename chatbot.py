from database import Database

def call_ai_model(payload: dict) -> str:
    """
    Placeholder for actual LLM API call.
    """
    return f"(AI would respond here using {len(payload['messages'])} messages and {len(payload['context']['goals'])} goals)"

def generate_reply(messages):
    """
    Build AI payload using:
    - all goals
    - cleaned logs
    - last 25 uncleaned logs
    """
    with Database() as db:
        goals = db.get_goals()
        cleaned_logs = db.get_cleaned_logs()
        recent_logs = db.get_uncleaned_logs(limit=25)

    context = {
        "goals": goals,
        "cleaned_logs": cleaned_logs,
        "recent_logs": recent_logs
    }

    payload = {
        "system": "You are a blunt accountability AI. Use goals + logs to evaluate progress.",
        "messages": messages,
        "context": context
    }

    return call_ai_model(payload)

def run_chat():
    messages = []
    print("💬 Accountability AI Chat (type 'quit' to exit)\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break

        with Database() as db:
            db.add_uncleaned_log(user_input)

        messages.append({"role": "user", "content": user_input})
        reply = generate_reply(messages)
        messages.append({"role": "assistant", "content": reply})

        print("AI:", reply)
