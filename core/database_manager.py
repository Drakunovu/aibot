import sqlite3
import time
from pathlib import Path

DB_FILE = Path("bot_usage.db")

def initialize_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            timestamp INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def log_token_usage(tokens: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO token_usage (timestamp, total_tokens) VALUES (?, ?)",
        (int(time.time()), tokens)
    )
    conn.commit()
    conn.close()

def get_tokens_from_last_7_days() -> int:
    seven_days_ago_ts = int(time.time()) - (7 * 24 * 60 * 60)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(total_tokens) FROM token_usage WHERE timestamp >= ?",
        (seven_days_ago_ts,)
    )
    result = cursor.fetchone()[0]
    conn.close()
    return result or 0

def cleanup_old_logs():
    seven_days_ago_ts = int(time.time()) - (7 * 24 * 60 * 60)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM token_usage WHERE timestamp < ?", (seven_days_ago_ts,))
    conn.commit()
    conn.close()
    print("Cleaned up old token logs from the database.")