from collections import Counter
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import gradio as gr
import matplotlib
import pandas as pd
from pydantic import BaseModel

from database import create_table, get_connection


matplotlib.use("Agg")
import matplotlib.pyplot as plt


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
        <p><a href="/gradio">Open Gradio dashboard</a></p>
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


def quotes_dataframe(search_text="", category="All"):
    conn = get_connection()
    query = "SELECT id, text, author, category FROM quotes"
    params = []
    filters = []

    if search_text:
        filters.append("(text LIKE ? OR author LIKE ? OR category LIKE ?)")
        search_value = f"%{search_text}%"
        params.extend([search_value, search_value, search_value])

    if category and category != "All":
        filters.append("category = ?")
        params.append(category)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def category_choices():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM quotes ORDER BY category")
    categories = [row[0] for row in cur.fetchall()]
    conn.close()
    return ["All"] + categories


def create_quote_ui(text, author, category):
    if not text or not author or not category:
        return "Text, author, and category are required.", quotes_dataframe()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quotes (text, author, category) VALUES (?, ?, ?)",
        (text, author, category),
    )
    conn.commit()
    conn.close()
    return "Quote created.", quotes_dataframe()


def update_quote_ui(quote_id, text, author, category):
    if not quote_id:
        return "Quote ID is required.", quotes_dataframe()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE quotes SET text = ?, author = ?, category = ? WHERE id = ?",
        (text, author, category, int(quote_id)),
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    if updated == 0:
        return f"Quote ID {int(quote_id)} was not found.", quotes_dataframe()

    return "Quote updated.", quotes_dataframe()


def delete_quote_ui(quote_id):
    if not quote_id:
        return "Quote ID is required.", quotes_dataframe()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM quotes WHERE id = ?", (int(quote_id),))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        return f"Quote ID {int(quote_id)} was not found.", quotes_dataframe()

    return "Quote deleted.", quotes_dataframe()


def crawl_quotes_ui(category, limit):
    from crawler import crawl_quotes

    saved = crawl_quotes(category=category, limit=int(limit))
    return f"Saved {saved} quotes for category '{category}'.", quotes_dataframe()


def word_count_dataframe(limit=10):
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
    return pd.DataFrame(counter.most_common(int(limit)), columns=["word", "count"])


def category_count_dataframe():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT category, COUNT(*) AS count FROM quotes GROUP BY category ORDER BY count DESC",
        conn,
    )
    conn.close()
    return df


def author_count_dataframe():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT author, COUNT(*) AS count FROM quotes GROUP BY author ORDER BY count DESC LIMIT 10",
        conn,
    )
    conn.close()
    return df


def summary_text():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT author), COUNT(DISTINCT category), AVG(LENGTH(text)) FROM quotes")
    total, authors, categories, avg_length = cur.fetchone()
    conn.close()
    avg_length = round(avg_length or 0, 1)
    return (
        f"Total quotes: {total}\n"
        f"Authors: {authors}\n"
        f"Categories: {categories}\n"
        f"Average quote length: {avg_length} characters"
    )


def plot_dataframe(df, x_column, y_column, title, color):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_axis_off()
        return fig

    ax.bar(df[x_column].astype(str), df[y_column], color=color)
    ax.set_title(title)
    ax.set_xlabel(x_column)
    ax.set_ylabel(y_column)
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    return fig


def word_count_plot():
    df = word_count_dataframe(10)
    return plot_dataframe(df, "word", "count", "Top 10 Words", "#0f766e")


def category_count_plot():
    df = category_count_dataframe()
    return plot_dataframe(df, "category", "count", "Quotes by Category", "#2563eb")


def refresh_dashboard(search_text="", selected_category="All"):
    return (
        quotes_dataframe(search_text, selected_category),
        summary_text(),
        word_count_dataframe(10),
        category_count_dataframe(),
        author_count_dataframe(),
        word_count_plot(),
        category_count_plot(),
        gr.Dropdown(choices=category_choices(), value=selected_category),
    )


with gr.Blocks(title="Quotes Project Dashboard") as gradio_app:
    gr.Markdown("# Quotes Project Dashboard")

    with gr.Row():
        search_input = gr.Textbox(label="Search", placeholder="Search text, author, or category")
        category_filter = gr.Dropdown(label="Category", choices=category_choices(), value="All")
        refresh_btn = gr.Button("Refresh", variant="primary")

    quotes_table = gr.Dataframe(label="Quotes", interactive=False)
    status_output = gr.Textbox(label="Status", interactive=False)

    with gr.Tab("Create"):
        new_text = gr.Textbox(label="Text", lines=3)
        new_author = gr.Textbox(label="Author")
        new_category = gr.Textbox(label="Category", value="life")
        create_btn = gr.Button("Create Quote", variant="primary")

    with gr.Tab("Update"):
        update_id = gr.Number(label="Quote ID", precision=0)
        update_text = gr.Textbox(label="Text", lines=3)
        update_author = gr.Textbox(label="Author")
        update_category = gr.Textbox(label="Category")
        update_btn = gr.Button("Update Quote", variant="primary")

    with gr.Tab("Delete"):
        delete_id = gr.Number(label="Quote ID", precision=0)
        delete_btn = gr.Button("Delete Quote", variant="stop")

    with gr.Tab("Crawl"):
        crawl_category = gr.Textbox(label="Category", value="life")
        crawl_limit = gr.Slider(label="Limit", minimum=1, maximum=20, value=20, step=1)
        crawl_btn = gr.Button("Crawl Quotes", variant="primary")

    with gr.Tab("Analytics"):
        summary_box = gr.Textbox(label="Summary", lines=4, interactive=False)
        with gr.Row():
            word_plot = gr.Plot(label="Word Count")
            category_plot = gr.Plot(label="Category Count")
        with gr.Row():
            word_table = gr.Dataframe(label="Top Words", interactive=False)
            category_table = gr.Dataframe(label="Categories", interactive=False)
            author_table = gr.Dataframe(label="Top Authors", interactive=False)

    refresh_outputs = [
        quotes_table,
        summary_box,
        word_table,
        category_table,
        author_table,
        word_plot,
        category_plot,
        category_filter,
    ]

    refresh_btn.click(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter],
        outputs=refresh_outputs,
    )
    search_input.submit(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter],
        outputs=refresh_outputs,
    )
    category_filter.change(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter],
        outputs=refresh_outputs,
    )

    create_btn.click(
        fn=create_quote_ui,
        inputs=[new_text, new_author, new_category],
        outputs=[status_output, quotes_table],
    )
    update_btn.click(
        fn=update_quote_ui,
        inputs=[update_id, update_text, update_author, update_category],
        outputs=[status_output, quotes_table],
    )
    delete_btn.click(
        fn=delete_quote_ui,
        inputs=[delete_id],
        outputs=[status_output, quotes_table],
    )
    crawl_btn.click(
        fn=crawl_quotes_ui,
        inputs=[crawl_category, crawl_limit],
        outputs=[status_output, quotes_table],
    )
    gradio_app.load(fn=refresh_dashboard, outputs=refresh_outputs)


app = gr.mount_gradio_app(app, gradio_app, path="/gradio")
