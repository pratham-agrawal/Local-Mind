import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

class Database:
    def __init__(self, db_path="accountability.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist (keeps original tables but add role/timestamp to logs)."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs_uncleaned (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT CHECK(role IN ('user','assistant')) DEFAULT 'user',
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs_cleaned (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER,
                    summary TEXT NOT NULL,
                    date DATE DEFAULT CURRENT_DATE,
                    FOREIGN KEY (goal_id) REFERENCES goals (id)
                )
            """)
            conn.commit()

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        # Let us access columns by name
        self.conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    # ---- Goals ----
    def add_goal(self, name: str, description: str):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO goals (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, datetime.utcnow().isoformat())
        )

    def get_goals(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, description FROM goals")
        rows = cur.fetchall()
        return [{"id": r["id"], "name": r["name"], "description": r["description"]} for r in rows]

    # ---- Uncleaned logs (now conversation-like) ----
    def add_message(self, role: str, message: str, timestamp: Optional[str] = None):
        """
        Generic message writer for both user and assistant.
        timestamp: ISO-8601 string; if None, we generate it here (UTC).
        """
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO logs_uncleaned (role, message, created_at) VALUES (?, ?, ?)",
            (role, message, timestamp)
        )

    def get_uncleaned_logs(self, limit: int = 50) -> List[Dict[str, str]]:
        """
        Returns most recent logs (both user & assistant) in chronological order.
        Each item: {"role": ..., "content": ..., "timestamp": ...}
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT role, message, created_at FROM logs_uncleaned ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        # rows are newest->oldest, reverse to chronological (old->new)
        messages = []
        for r in reversed(rows):
            messages.append({"role": r["role"], "content": r["message"], "timestamp": r["created_at"]})
        return messages

    # ---- Cleaned logs ----
    def add_cleaned_log(self, goal_id: int, summary: str):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO logs_cleaned (goal_id, summary) VALUES (?, ?)",
            (goal_id, summary)
        )

    def get_cleaned_logs(self, goal_id: int = None):
        cur = self.conn.cursor()
        if goal_id:
            cur.execute("SELECT id, goal_id, summary, date FROM logs_cleaned WHERE goal_id = ?", (goal_id,))
        else:
            cur.execute("SELECT id, goal_id, summary, date FROM logs_cleaned ORDER BY date DESC")
        rows = cur.fetchall()
        return [{"id": r["id"], "goal_id": r["goal_id"], "summary": r["summary"], "date": r["date"]} for r in rows]
