import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from datetime import datetime
from typing import List, Dict, Optional, Any



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
    def get_cleaned_logs(self, goal_id: int = None):
        cur = self.conn.cursor()
        if goal_id:
            cur.execute("SELECT id, goal_id, summary, date FROM logs_cleaned WHERE goal_id = ?", (goal_id,))
        else:
            cur.execute("SELECT id, goal_id, summary, date FROM logs_cleaned ORDER BY date DESC")
        rows = cur.fetchall()
        return [{"id": r["id"], "goal_id": r["goal_id"], "summary": r["summary"], "date": r["date"]} for r in rows]
    
    def get_uncleaned_logs_between(self, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
        """
        Return uncleaned logs (conversation rows) between two ISO timestamps (inclusive start, exclusive end).
        Each row: {"role": ..., "content": ..., "timestamp": ...}
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT role, message, created_at FROM logs_uncleaned WHERE created_at >= ? AND created_at < ? ORDER BY id ASC",
            (start_iso, end_iso)
        )
        rows = cur.fetchall()
        return [{"role": r["role"], "content": r["message"], "timestamp": r["created_at"]} for r in rows]

    def get_earliest_uncleaned_timestamp(self) -> Optional[str]:
        """
        Return the earliest created_at ISO timestamp in logs_uncleaned, or None if no logs.
        """
        cur = self.conn.cursor()
        cur.execute("SELECT created_at FROM logs_uncleaned ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        return row["created_at"] if row else None

    def get_latest_cleaned_day(self) -> Optional[str]:
        """
        Return the latest `date` value stored in logs_cleaned as ISO date string (YYYY-MM-DD),
        or None if no cleaned logs exist.
        """
        cur = self.conn.cursor()
        cur.execute("SELECT date FROM logs_cleaned ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        return row["date"] if row else None

    def add_cleaned_log(self, goal_id: Optional[int], summary: str, date: Optional[str] = None) -> int:
        """
        Insert a cleaned log. goal_id may be None (for general daily summaries).
        date should be a YYYY-MM-DD string representing the day_start per your cutoff.
        Returns lastrowid.
        """
        if date is None:
            date = datetime.utcnow().date().isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO logs_cleaned (goal_id, summary, date) VALUES (?, ?, ?)",
            (goal_id, summary, date)
        )
        self.conn.commit()
        return cur.lastrowid
