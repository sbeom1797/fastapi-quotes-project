from collections import Counter
import csv
from io import StringIO
import random
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import gradio as gr
import matplotlib
import pandas as pd
from pydantic import BaseModel

from database import create_table, get_connection


matplotlib.use("Agg")
import matplotlib.pyplot as plt


plt.rcParams["font.family"] = ["Noto Sans CJK KR", "Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

app = FastAPI(title="명언 프로젝트")


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "he", "her", "his", "i", "if", "in", "is", "it", "its",
    "me", "my", "not", "of", "on", "or", "our", "she", "so", "that", "the",
    "their", "them", "there", "they", "this", "to", "was", "we", "what",
    "when", "where", "which", "who", "will", "with", "you", "your",
}

ALL_CATEGORIES = "전체"


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
        <title>명언 프로젝트</title>
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
        <h1>명언 프로젝트 서버가 실행 중입니다</h1>
        <p>FastAPI 서버가 정상적으로 시작되었습니다.</p>
        <p><a href="/quotes">명언 JSON 보기</a></p>
        <p><a href="/word-count">단어 빈도 JSON 보기</a></p>
        <p><a href="/stats">기초 통계 JSON 보기</a></p>
        <p><a href="/random-quote">랜덤 명언 JSON 보기</a></p>
        <p><a href="/export/csv">명언 CSV 다운로드</a></p>
        <p><a href="/gradio">Gradio 대시보드 열기</a></p>
        <p>API 문서: <a href="/docs">/docs</a></p>
        <p>샘플 데이터를 수집하려면 문서에서 <code>POST /crawl/life</code>를 실행하세요.</p>
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
def word_count(limit: int = 10, include_stopwords: bool = False):
    return word_count_records(limit=limit, include_stopwords=include_stopwords)


@app.get("/stats")
def stats():
    return basic_stats()


@app.get("/random-quote")
def random_quote(category: str | None = None):
    conn = get_connection()
    cur = conn.cursor()
    if category:
        cur.execute(
            "SELECT id, text, author, category FROM quotes WHERE category = ?",
            (category,),
        )
    else:
        cur.execute("SELECT id, text, author, category FROM quotes")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No quotes found.")

    row = random.choice(rows)
    return {"id": row[0], "text": row[1], "author": row[2], "category": row[3]}


@app.get("/export/csv")
def export_csv():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, text, author, category FROM quotes ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "text", "author", "category"])
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quotes.csv"},
    )


def quotes_dataframe(search_text="", category="All"):
    conn = get_connection()
    query = "SELECT id, text, author, category FROM quotes"
    params = []
    filters = []

    if search_text:
        filters.append("(text LIKE ? OR author LIKE ? OR category LIKE ?)")
        search_value = f"%{search_text}%"
        params.extend([search_value, search_value, search_value])

    if category and category not in ("All", ALL_CATEGORIES):
        filters.append("category = ?")
        params.append(category)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df.rename(
        columns={
            "id": "ID",
            "text": "명언",
            "author": "작성자",
            "category": "카테고리",
        }
    )


def category_choices():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM quotes ORDER BY category")
    categories = [row[0] for row in cur.fetchall()]
    conn.close()
    return [ALL_CATEGORIES] + categories


def tokenize_quote_text(text, include_stopwords=False):
    cleaned = re.sub(r"[^a-zA-Z ]", "", text.lower())
    words = cleaned.split()
    if include_stopwords:
        return words
    return [word for word in words if word not in STOPWORDS and len(word) > 1]


def word_count_records(limit=10, include_stopwords=False):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT text FROM quotes")
    rows = cur.fetchall()
    conn.close()

    words = []
    for row in rows:
        words.extend(tokenize_quote_text(row[0], include_stopwords))

    counter = Counter(words)
    return [
        {"word": word, "count": count}
        for word, count in counter.most_common(max(1, int(limit)))
    ]


def basic_stats():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COUNT(*),
            COUNT(DISTINCT author),
            COUNT(DISTINCT category),
            AVG(LENGTH(text)),
            MIN(LENGTH(text)),
            MAX(LENGTH(text))
        FROM quotes
        """
    )
    total, authors, categories, avg_length, min_length, max_length = cur.fetchone()
    conn.close()
    return {
        "total_quotes": total,
        "unique_authors": authors,
        "unique_categories": categories,
        "average_quote_length": round(avg_length or 0, 1),
        "shortest_quote_length": min_length or 0,
        "longest_quote_length": max_length or 0,
    }


def create_quote_ui(text, author, category):
    if not text or not author or not category:
        return "명언, 작성자, 카테고리를 모두 입력해 주세요.", quotes_dataframe()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quotes (text, author, category) VALUES (?, ?, ?)",
        (text, author, category),
    )
    conn.commit()
    conn.close()
    return "명언이 추가되었습니다.", quotes_dataframe()


def update_quote_ui(quote_id, text, author, category):
    if not quote_id:
        return "수정할 명언 ID를 입력해 주세요.", quotes_dataframe()

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
        return f"ID {int(quote_id)}에 해당하는 명언을 찾을 수 없습니다.", quotes_dataframe()

    return "명언이 수정되었습니다.", quotes_dataframe()


def delete_quote_ui(quote_id):
    if not quote_id:
        return "삭제할 명언 ID를 입력해 주세요.", quotes_dataframe()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM quotes WHERE id = ?", (int(quote_id),))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        return f"ID {int(quote_id)}에 해당하는 명언을 찾을 수 없습니다.", quotes_dataframe()

    return "명언이 삭제되었습니다.", quotes_dataframe()


def crawl_quotes_ui(category, limit):
    from crawler import crawl_quotes

    saved = crawl_quotes(category=category, limit=int(limit))
    return f"'{category}' 카테고리 명언 {saved}개를 저장했습니다.", quotes_dataframe()


def word_count_dataframe(limit=10, include_stopwords=False):
    return pd.DataFrame(
        word_count_records(limit, include_stopwords),
        columns=["word", "count"],
    ).rename(
        columns={
            "word": "단어",
            "count": "빈도",
        }
    )


def category_count_dataframe():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT category, COUNT(*) AS count FROM quotes GROUP BY category ORDER BY count DESC",
        conn,
    )
    conn.close()
    return df.rename(columns={"category": "카테고리", "count": "개수"})


def author_count_dataframe():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT author, COUNT(*) AS count FROM quotes GROUP BY author ORDER BY count DESC LIMIT 10",
        conn,
    )
    conn.close()
    return df.rename(columns={"author": "작성자", "count": "개수"})


def quote_length_dataframe():
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            id,
            author,
            category,
            LENGTH(text) AS characters,
            LENGTH(text) - LENGTH(REPLACE(text, ' ', '')) + 1 AS estimated_words,
            text
        FROM quotes
        ORDER BY characters DESC
        """,
        conn,
    )
    conn.close()
    return df.rename(
        columns={
            "id": "ID",
            "author": "작성자",
            "category": "카테고리",
            "characters": "글자 수",
            "estimated_words": "예상 단어 수",
            "text": "명언",
        }
    )


def longest_quotes_dataframe(limit=5):
    df = quote_length_dataframe()
    if df.empty:
        return df
    return df.head(int(limit))


def length_bucket_dataframe():
    df = quote_length_dataframe()
    if df.empty:
        return pd.DataFrame(columns=["길이 구간", "개수"])

    bins = [0, 50, 100, 150, 200, 300, float("inf")]
    labels = ["1-50", "51-100", "101-150", "151-200", "201-300", "301+"]
    df["길이 구간"] = pd.cut(
        df["글자 수"],
        bins=bins,
        labels=labels,
        right=True,
        include_lowest=True,
    )
    return (
        df.groupby("길이 구간", observed=False)
        .size()
        .reset_index(name="개수")
    )


def random_quote_text(selected_category=ALL_CATEGORIES):
    category = None if selected_category in ("All", ALL_CATEGORIES) else selected_category
    try:
        quote = random_quote(category)
    except HTTPException:
        return "명언이 없습니다."
    return f'"{quote["text"]}"\n- {quote["author"]} ({quote["category"]})'


def summary_text():
    stats = basic_stats()
    return (
        f"전체 명언 수: {stats['total_quotes']}\n"
        f"작성자 수: {stats['unique_authors']}\n"
        f"카테고리 수: {stats['unique_categories']}\n"
        f"평균 명언 길이: {stats['average_quote_length']}자\n"
        f"최단/최장 길이: {stats['shortest_quote_length']} / {stats['longest_quote_length']}자"
    )


def plot_dataframe(df, x_column, y_column, title, color):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if df.empty:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center")
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
    return plot_dataframe(df, "단어", "빈도", "상위 10개 단어", "#0f766e")


def word_count_plot_with_options(limit=10, include_stopwords=False):
    df = word_count_dataframe(limit, include_stopwords)
    return plot_dataframe(df, "단어", "빈도", f"상위 {int(limit)}개 단어", "#0f766e")


def category_count_plot():
    df = category_count_dataframe()
    return plot_dataframe(df, "카테고리", "개수", "카테고리별 명언 수", "#2563eb")


def author_count_plot():
    df = author_count_dataframe()
    return plot_dataframe(df, "작성자", "개수", "상위 작성자", "#7c3aed")


def length_bucket_plot():
    df = length_bucket_dataframe()
    return plot_dataframe(df, "길이 구간", "개수", "명언 길이 분포", "#ea580c")


def refresh_analytics(word_limit=10, include_stopwords=False, selected_category=ALL_CATEGORIES):
    return (
        summary_text(),
        word_count_dataframe(word_limit, include_stopwords),
        category_count_dataframe(),
        author_count_dataframe(),
        longest_quotes_dataframe(5),
        word_count_plot_with_options(word_limit, include_stopwords),
        category_count_plot(),
        author_count_plot(),
        length_bucket_plot(),
        random_quote_text(selected_category),
    )


def refresh_dashboard(search_text="", selected_category=ALL_CATEGORIES, word_limit=10, include_stopwords=False):
    analytics_outputs = refresh_analytics(word_limit, include_stopwords, selected_category)
    return (
        quotes_dataframe(search_text, selected_category),
        *analytics_outputs,
        gr.Dropdown(choices=category_choices(), value=selected_category),
    )


with gr.Blocks(title="명언 프로젝트 대시보드") as gradio_app:
    gr.Markdown("# 명언 프로젝트 대시보드")

    with gr.Row():
        search_input = gr.Textbox(label="검색", placeholder="명언, 작성자, 카테고리 검색")
        category_filter = gr.Dropdown(
            label="카테고리",
            choices=category_choices(),
            value=ALL_CATEGORIES,
        )
        refresh_btn = gr.Button("새로고침", variant="primary")

    quotes_table = gr.Dataframe(label="명언 목록", interactive=False)
    status_output = gr.Textbox(label="처리 상태", interactive=False)

    with gr.Tab("추가"):
        new_text = gr.Textbox(label="명언", lines=3)
        new_author = gr.Textbox(label="작성자")
        new_category = gr.Textbox(label="카테고리", value="life")
        create_btn = gr.Button("명언 추가", variant="primary")

    with gr.Tab("수정"):
        update_id = gr.Number(label="명언 ID", precision=0)
        update_text = gr.Textbox(label="명언", lines=3)
        update_author = gr.Textbox(label="작성자")
        update_category = gr.Textbox(label="카테고리")
        update_btn = gr.Button("명언 수정", variant="primary")

    with gr.Tab("삭제"):
        delete_id = gr.Number(label="명언 ID", precision=0)
        delete_btn = gr.Button("명언 삭제", variant="stop")

    with gr.Tab("수집"):
        crawl_category = gr.Textbox(label="카테고리", value="life")
        crawl_limit = gr.Slider(label="수집 개수", minimum=1, maximum=20, value=20, step=1)
        crawl_btn = gr.Button("명언 수집", variant="primary")

    with gr.Tab("분석"):
        with gr.Row():
            word_limit = gr.Slider(label="단어 표시 개수", minimum=5, maximum=30, value=10, step=1)
            include_stopwords = gr.Checkbox(label="흔한 단어 포함", value=False)
            analytics_refresh_btn = gr.Button("분석 새로고침", variant="primary")
        summary_box = gr.Textbox(label="요약 통계", lines=4, interactive=False)
        random_quote_box = gr.Textbox(label="랜덤 명언", lines=3, interactive=False)
        with gr.Row():
            word_plot = gr.Plot(label="단어 빈도")
            category_plot = gr.Plot(label="카테고리별 개수")
        with gr.Row():
            author_plot = gr.Plot(label="작성자별 개수")
            length_plot = gr.Plot(label="길이 분포")
        with gr.Row():
            word_table = gr.Dataframe(label="상위 단어", interactive=False)
            category_table = gr.Dataframe(label="카테고리", interactive=False)
            author_table = gr.Dataframe(label="상위 작성자", interactive=False)
        longest_table = gr.Dataframe(label="가장 긴 명언", interactive=False)

    refresh_outputs = [
        quotes_table,
        summary_box,
        word_table,
        category_table,
        author_table,
        longest_table,
        word_plot,
        category_plot,
        author_plot,
        length_plot,
        random_quote_box,
        category_filter,
    ]

    analytics_outputs = [
        summary_box,
        word_table,
        category_table,
        author_table,
        longest_table,
        word_plot,
        category_plot,
        author_plot,
        length_plot,
        random_quote_box,
    ]

    refresh_btn.click(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )
    search_input.submit(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )
    category_filter.change(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )
    analytics_refresh_btn.click(
        fn=refresh_analytics,
        inputs=[word_limit, include_stopwords, category_filter],
        outputs=analytics_outputs,
    )
    word_limit.change(
        fn=refresh_analytics,
        inputs=[word_limit, include_stopwords, category_filter],
        outputs=analytics_outputs,
    )
    include_stopwords.change(
        fn=refresh_analytics,
        inputs=[word_limit, include_stopwords, category_filter],
        outputs=analytics_outputs,
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
    gradio_app.load(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )


app = gr.mount_gradio_app(app, gradio_app, path="/gradio")
