from chatbot import run_chat
from database import Database

def main():
    while True:
        choice = input("\n(1) Chat  (2) Add Goal  (q) Quit: ")
        if choice == "1":
            run_chat()
        elif choice == "2":
            name = input("Goal name: ")
            desc = input("Goal description: ")
            with Database() as db:
                db.add_goal(name, desc)
            print("✅ Goal added")
        elif choice.lower() == "q":
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
