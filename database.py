import sqlite3

DB_NAME = "quotes.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def create_table():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        author TEXT NOT NULL,
        category TEXT NOT NULL,
        favorite INTEGER NOT NULL DEFAULT 0
    )
    """)

    cur.execute("PRAGMA table_info(quotes)")
    columns = [row[1] for row in cur.fetchall()]
    if "favorite" not in columns:
        cur.execute("ALTER TABLE quotes ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_text_author_category
    ON quotes (text, author, category)
    """)

    conn.commit()
    conn.close()
