import sqlite3

class Database:
    def __init__(self, db_path="accountability.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist"""
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
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs_cleaned (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER,
                    summary TEXT NOT NULL,
                    date DATE DEFAULT CURRENT_DATE,
                    FOREIGN KEY (goal_id) REFERENCES goals(id)
                )
            """)

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    # ---- Goals ----
    def add_goal(self, name: str, description: str):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO goals (name, description) VALUES (?, ?)",
            (name, description)
        )

    def get_goals(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, description FROM goals")
        rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]

    # ---- Uncleaned logs ----
    def add_uncleaned_log(self, message: str):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO logs_uncleaned (message) VALUES (?)",
            (message,)
        )

    def get_uncleaned_logs(self, limit: int = 50):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, message, created_at FROM logs_uncleaned ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        return [{"id": r[0], "message": r[1], "created_at": r[2]} for r in rows]

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
            cur.execute(
                "SELECT summary, date FROM logs_cleaned WHERE goal_id = ?",
                (goal_id,)
            )
        else:
            cur.execute("SELECT goal_id, summary, date FROM logs_cleaned")
        rows = cur.fetchall()
        return rows
