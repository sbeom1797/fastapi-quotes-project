from collections import Counter
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database import create_table, get_connection


app = FastAPI(title="Quotes Project")


class Quote(BaseModel):
    text: str
    author: str
    category: str


@app.on_event("startup")
def startup():
    create_table()


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8">
        <title>Quotes Project</title>
        <style>
          body {
            max-width: 880px;
            margin: 40px auto;
            padding: 0 20px;
            font-family: Arial, sans-serif;
            line-height: 1.6;
          }
          a {
            color: #0f766e;
            font-weight: 700;
          }
          code {
            background: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
          }
        </style>
      </head>
      <body>
        <h1>Quotes Project server is running</h1>
        <p>FastAPI server started successfully.</p>
        <p><a href="/quotes">View quotes JSON</a></p>
        <p><a href="/word-count">View word count JSON</a></p>
        <p>API docs: <a href="/docs">/docs</a></p>
        <p>To crawl sample data, open docs and run <code>POST /crawl/life</code>.</p>
      </body>
    </html>
    """


@app.post("/crawl/{category}")
def crawl(category: str):
    try:
        from crawler import crawl_quotes
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Crawler dependencies are missing. Run: python -m pip install beautifulsoup4 requests",
        ) from exc

    count = crawl_quotes(category)
    return {"message": f"Saved {count} quotes for category '{category}'."}


@app.post("/quotes")
def create_quote(quote: Quote):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quotes (text, author, category) VALUES (?, ?, ?)",
        (quote.text, quote.author, quote.category),
    )
    conn.commit()
    conn.close()
    return {"message": "Quote created."}


@app.get("/quotes")
def read_quotes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, text, author, category FROM quotes")
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": row[0], "text": row[1], "author": row[2], "category": row[3]}
        for row in rows
    ]


@app.get("/quotes/{quote_id}")
def read_quote(quote_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, text, author, category FROM quotes WHERE id = ?", (quote_id,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Quote not found.")

    return {"id": row[0], "text": row[1], "author": row[2], "category": row[3]}


@app.put("/quotes/{quote_id}")
def update_quote(quote_id: int, quote: Quote):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE quotes SET text = ?, author = ?, category = ? WHERE id = ?",
        (quote.text, quote.author, quote.category, quote_id),
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    if updated == 0:
        raise HTTPException(status_code=404, detail="Quote not found.")

    return {"message": "Quote updated."}


@app.delete("/quotes/{quote_id}")
def delete_quote(quote_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Quote not found.")

    return {"message": "Quote deleted."}


@app.get("/word-count")
def word_count():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT text FROM quotes")
    rows = cur.fetchall()
    conn.close()

    words = []
    for row in rows:
        text = row[0].lower()
        text = re.sub(r"[^a-zA-Z ]", "", text)
        words.extend(text.split())

    counter = Counter(words)
    return [
        {"word": word, "count": count}
        for word, count in counter.most_common(10)
    ]
