from collections import Counter
import csv
from io import StringIO
import random
import re

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import gradio as gr
import matplotlib
import pandas as pd
from pydantic import BaseModel, Field

from database import create_table, get_connection


matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


AVAILABLE_FONTS = {font.name for font in font_manager.fontManager.ttflist}
for font_name in ("Noto Sans CJK KR", "Malgun Gothic", "DejaVu Sans"):
    if font_name in AVAILABLE_FONTS:
        plt.rcParams["font.family"] = font_name
        break
plt.rcParams["axes.unicode_minus"] = False

API_TAGS = [
    {"name": "홈", "description": "서비스 첫 화면과 주요 링크입니다."},
    {"name": "수집", "description": "quotes.toscrape.com에서 명언을 수집합니다."},
    {"name": "명언 관리", "description": "명언 데이터를 생성, 조회, 수정, 삭제합니다."},
    {"name": "분석", "description": "단어 빈도수와 기초 통계를 제공합니다."},
    {"name": "내보내기", "description": "저장된 명언 데이터를 파일로 내려받습니다."},
]

app = FastAPI(
    title="명언 프로젝트 API",
    description=(
        "quotes.toscrape.com에서 수집한 명언 데이터를 SQLite에 저장하고, "
        "FastAPI와 Gradio로 조회, 관리, 분석할 수 있는 프로젝트입니다."
    ),
    version="1.0.0",
    openapi_tags=API_TAGS,
)


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "he", "her", "his", "i", "if", "in", "is", "it", "its",
    "me", "my", "not", "of", "on", "or", "our", "she", "so", "that", "the",
    "their", "them", "there", "they", "this", "to", "was", "we", "what",
    "when", "where", "which", "who", "will", "with", "you", "your",
}

ALL_CATEGORIES = "전체"
ALL_AUTHORS = "전체 작성자"


class Quote(BaseModel):
    text: str = Field(..., title="명언", description="저장할 명언 문장입니다.")
    author: str = Field(..., title="작성자", description="명언을 남긴 작성자입니다.")
    category: str = Field(..., title="카테고리", description="명언의 주제 또는 태그입니다.")


@app.on_event("startup")
def startup():
    create_table()


@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["홈"],
    summary="서비스 홈 화면",
    description="명언 프로젝트의 주요 API와 Gradio 대시보드 링크를 보여줍니다.",
)
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
        <p>샘플 데이터를 수집하려면 문서에서 <code>POST /crawl/default-categories</code>를 실행하세요.</p>
      </body>
    </html>
    """


@app.post(
    "/crawl/{category}",
    tags=["수집"],
    summary="카테고리별 명언 수집",
    description="quotes.toscrape.com에서 지정한 카테고리의 명언을 수집하여 SQLite에 저장합니다.",
)
def crawl(
    category: str = Path(..., description="수집할 카테고리입니다. 예: life, love, books")
):
    try:
        from crawler import crawl_quotes
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="크롤러 의존성이 없습니다. python -m pip install beautifulsoup4 requests 를 실행하세요.",
        ) from exc

    count = crawl_quotes(category)
    return {"message": f"'{category}' 카테고리 명언 {count}개를 저장했습니다."}


@app.post(
    "/crawl/default-categories",
    tags=["수집"],
    summary="기본 카테고리 여러 개 수집",
    description="기본으로 지정한 여러 카테고리의 명언을 한 번에 수집합니다.",
)
def crawl_default_categories(
    limit: int = Query(20, ge=1, le=20, description="카테고리마다 수집할 최대 명언 개수입니다.")
):
    from crawler import DEFAULT_CATEGORIES, crawl_multiple_categories

    results = crawl_multiple_categories(DEFAULT_CATEGORIES, limit)
    return {"message": "기본 카테고리 수집이 완료되었습니다.", "results": results}


@app.post(
    "/crawl/all-tags",
    tags=["수집"],
    summary="전체 사이트 태그 수집",
    description="quotes.toscrape.com 전체 페이지를 순회하며 각 명언의 태그를 카테고리로 저장합니다.",
)
def crawl_all_tags(
    max_pages: int = Query(10, ge=1, le=10, description="수집할 최대 페이지 수입니다.")
):
    from crawler import crawl_all_quote_tags

    result = crawl_all_quote_tags(max_pages)
    return {"message": "전체 태그 수집이 완료되었습니다.", "result": result}


@app.post(
    "/quotes",
    tags=["명언 관리"],
    summary="명언 추가",
    description="새 명언을 데이터베이스에 추가합니다.",
)
def create_quote(quote: Quote):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quotes (text, author, category) VALUES (?, ?, ?)",
        (quote.text, quote.author, quote.category),
    )
    conn.commit()
    conn.close()
    return {"message": "명언이 추가되었습니다."}


@app.get(
    "/quotes",
    tags=["명언 관리"],
    summary="전체 명언 조회",
    description="데이터베이스에 저장된 모든 명언을 조회합니다.",
)
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


@app.get(
    "/quotes/{quote_id}",
    tags=["명언 관리"],
    summary="명언 단건 조회",
    description="ID로 특정 명언 하나를 조회합니다.",
)
def read_quote(quote_id: int = Path(..., description="조회할 명언 ID입니다.")):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, text, author, category FROM quotes WHERE id = ?", (quote_id,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="명언을 찾을 수 없습니다.")

    return {"id": row[0], "text": row[1], "author": row[2], "category": row[3]}


@app.put(
    "/quotes/{quote_id}",
    tags=["명언 관리"],
    summary="명언 수정",
    description="ID로 특정 명언의 문장, 작성자, 카테고리를 수정합니다.",
)
def update_quote(
    quote: Quote,
    quote_id: int = Path(..., description="수정할 명언 ID입니다."),
):
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
        raise HTTPException(status_code=404, detail="명언을 찾을 수 없습니다.")

    return {"message": "명언이 수정되었습니다."}


@app.delete(
    "/quotes/{quote_id}",
    tags=["명언 관리"],
    summary="명언 삭제",
    description="ID로 특정 명언을 삭제합니다.",
)
def delete_quote(quote_id: int = Path(..., description="삭제할 명언 ID입니다.")):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="명언을 찾을 수 없습니다.")

    return {"message": "명언이 삭제되었습니다."}


@app.get(
    "/word-count",
    tags=["분석"],
    summary="단어 빈도수 조회",
    description="저장된 명언 텍스트에서 자주 등장하는 단어와 빈도수를 계산합니다.",
)
def word_count(
    limit: int = Query(10, ge=1, le=100, description="조회할 상위 단어 개수입니다."),
    include_stopwords: bool = Query(False, description="the, and 같은 흔한 단어를 포함할지 선택합니다."),
):
    return word_count_records(limit=limit, include_stopwords=include_stopwords)


@app.get(
    "/stats",
    tags=["분석"],
    summary="기초 통계 조회",
    description="전체 명언 수, 작성자 수, 카테고리 수, 평균/최소/최대 길이를 조회합니다.",
)
def stats():
    return basic_stats()


@app.get(
    "/random-quote",
    tags=["분석"],
    summary="랜덤 명언 조회",
    description="전체 또는 특정 카테고리에서 랜덤 명언 하나를 조회합니다.",
)
def random_quote(
    category: str | None = Query(None, description="선택적으로 필터링할 카테고리입니다.")
):
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
        raise HTTPException(status_code=404, detail="명언이 없습니다.")

    row = random.choice(rows)
    return {"id": row[0], "text": row[1], "author": row[2], "category": row[3]}


@app.get(
    "/export/csv",
    tags=["내보내기"],
    summary="CSV 다운로드",
    description="저장된 모든 명언을 CSV 파일로 다운로드합니다.",
)
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


def quotes_dataframe(search_text="", category="All", author=ALL_AUTHORS, favorites_only=False):
    conn = get_connection()
    query = "SELECT id, text, author, category, favorite FROM quotes"
    params = []
    filters = []

    if search_text:
        filters.append("(text LIKE ? OR author LIKE ? OR category LIKE ?)")
        search_value = f"%{search_text}%"
        params.extend([search_value, search_value, search_value])

    if category and category not in ("All", ALL_CATEGORIES):
        filters.append("category = ?")
        params.append(category)

    if author and author != ALL_AUTHORS:
        filters.append("author = ?")
        params.append(author)

    if favorites_only:
        filters.append("favorite = 1")

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df = df.rename(
        columns={
            "id": "ID",
            "text": "명언",
            "author": "작성자",
            "category": "카테고리",
            "favorite": "즐겨찾기",
        }
    )
    if "즐겨찾기" in df.columns:
        df["즐겨찾기"] = df["즐겨찾기"].map({1: "★", 0: ""})
    return df


def category_choices():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM quotes ORDER BY category")
    categories = [row[0] for row in cur.fetchall()]
    conn.close()
    return [ALL_CATEGORIES] + categories


def author_choices():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT author FROM quotes ORDER BY author")
    authors = [row[0] for row in cur.fetchall()]
    conn.close()
    return [ALL_AUTHORS] + authors


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


def crawl_default_categories_ui(limit):
    from crawler import DEFAULT_CATEGORIES, crawl_multiple_categories

    results = crawl_multiple_categories(DEFAULT_CATEGORIES, int(limit))
    details = ", ".join(
        f"{category}: {saved}개" for category, saved in results.items()
    )
    return f"기본 카테고리 수집 완료 ({details})", quotes_dataframe()


def crawl_all_tags_ui(max_pages):
    from crawler import crawl_all_quote_tags

    result = crawl_all_quote_tags(int(max_pages))
    return (
        f"전체 태그 수집 완료: {result['pages']}페이지에서 {result['saved']}개 저장",
        quotes_dataframe(),
    )


def toggle_favorite_ui(quote_id):
    if not quote_id:
        return "즐겨찾기에 추가하거나 해제할 명언 ID를 입력해 주세요.", quotes_dataframe(), favorites_dataframe()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT favorite FROM quotes WHERE id = ?", (int(quote_id),))
    row = cur.fetchone()

    if row is None:
        conn.close()
        return f"ID {int(quote_id)}에 해당하는 명언을 찾을 수 없습니다.", quotes_dataframe(), favorites_dataframe()

    next_value = 0 if row[0] else 1
    cur.execute("UPDATE quotes SET favorite = ? WHERE id = ?", (next_value, int(quote_id)))
    conn.commit()
    conn.close()

    message = "즐겨찾기에 추가했습니다." if next_value else "즐겨찾기에서 해제했습니다."
    return message, quotes_dataframe(), favorites_dataframe()


def favorites_dataframe():
    return quotes_dataframe(favorites_only=True)


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


def today_quote_text():
    return random_quote_text()


def quiz_question(selected_category=ALL_CATEGORIES):
    category = None if selected_category in ("All", ALL_CATEGORIES) else selected_category
    conn = get_connection()
    cur = conn.cursor()

    if category:
        cur.execute("SELECT text, author, category FROM quotes WHERE category = ?", (category,))
    else:
        cur.execute("SELECT text, author, category FROM quotes")
    quotes = cur.fetchall()

    cur.execute("SELECT DISTINCT author FROM quotes ORDER BY author")
    authors = [row[0] for row in cur.fetchall()]
    conn.close()

    if not quotes:
        return "퀴즈를 만들 명언이 없습니다.", gr.Dropdown(choices=[], value=None), "", ""

    correct_text, correct_author, quote_category = random.choice(quotes)
    wrong_authors = [author for author in authors if author != correct_author]
    options = random.sample(wrong_authors, min(3, len(wrong_authors))) + [correct_author]
    random.shuffle(options)

    question = f'"{correct_text}"\n\n이 명언을 남긴 사람은 누구일까요? ({quote_category})'
    return question, gr.Dropdown(choices=options, value=None), correct_author, ""


def check_quiz_answer(selected_author, correct_author):
    if not correct_author:
        return "먼저 새 퀴즈를 만들어 주세요."
    if not selected_author:
        return "정답을 선택해 주세요."
    if selected_author == correct_author:
        return "정답입니다!"
    return f"아쉽지만 오답입니다. 정답은 {correct_author}입니다."


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


def refresh_dashboard(
    search_text="",
    selected_category=ALL_CATEGORIES,
    selected_author=ALL_AUTHORS,
    word_limit=10,
    include_stopwords=False,
):
    return (
        quotes_dataframe(search_text, selected_category, selected_author),
        gr.Dropdown(choices=category_choices(), value=selected_category),
        gr.Dropdown(choices=author_choices(), value=selected_author),
        today_quote_text(),
    )


create_table()


with gr.Blocks(title="명언 프로젝트 대시보드") as gradio_app:
    gr.Markdown("# 명언 프로젝트 대시보드")
    today_quote_box = gr.Textbox(label="오늘의 명언", lines=3, interactive=False)

    with gr.Row():
        search_input = gr.Textbox(label="검색", placeholder="명언, 작성자, 카테고리 검색")
        category_filter = gr.Dropdown(
            label="카테고리",
            choices=category_choices(),
            value=ALL_CATEGORIES,
        )
        author_filter = gr.Dropdown(
            label="작성자",
            choices=author_choices(),
            value=ALL_AUTHORS,
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
        crawl_default_btn = gr.Button("기본 카테고리 20개 수집", variant="primary")
        crawl_all_tags_pages = gr.Slider(label="전체 태그 수집 페이지 수", minimum=1, maximum=10, value=10, step=1)
        crawl_all_tags_btn = gr.Button("전체 사이트 태그 수집", variant="primary")

    with gr.Tab("즐겨찾기"):
        favorite_id = gr.Number(label="명언 ID", precision=0)
        favorite_btn = gr.Button("즐겨찾기 추가/해제", variant="primary")
        favorites_table = gr.Dataframe(label="즐겨찾기 목록", interactive=False)

    with gr.Tab("퀴즈"):
        quiz_category = gr.Dropdown(
            label="퀴즈 카테고리",
            choices=category_choices(),
            value=ALL_CATEGORIES,
        )
        quiz_btn = gr.Button("새 퀴즈 만들기", variant="primary")
        quiz_question_box = gr.Textbox(label="문제", lines=5, interactive=False)
        quiz_answer = gr.Dropdown(label="작성자 선택", choices=[])
        quiz_check_btn = gr.Button("정답 확인", variant="primary")
        quiz_result = gr.Textbox(label="결과", interactive=False)
        quiz_correct_author = gr.State("")

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
        category_filter,
        author_filter,
        today_quote_box,
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
        inputs=[search_input, category_filter, author_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )
    search_input.submit(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, author_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )
    category_filter.change(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, author_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )
    author_filter.change(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, author_filter, word_limit, include_stopwords],
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
    crawl_default_btn.click(
        fn=crawl_default_categories_ui,
        inputs=[crawl_limit],
        outputs=[status_output, quotes_table],
    )
    crawl_all_tags_btn.click(
        fn=crawl_all_tags_ui,
        inputs=[crawl_all_tags_pages],
        outputs=[status_output, quotes_table],
    )
    favorite_btn.click(
        fn=toggle_favorite_ui,
        inputs=[favorite_id],
        outputs=[status_output, quotes_table, favorites_table],
    )
    quiz_btn.click(
        fn=quiz_question,
        inputs=[quiz_category],
        outputs=[quiz_question_box, quiz_answer, quiz_correct_author, quiz_result],
    )
    quiz_check_btn.click(
        fn=check_quiz_answer,
        inputs=[quiz_answer, quiz_correct_author],
        outputs=[quiz_result],
    )
    gradio_app.load(
        fn=refresh_dashboard,
        inputs=[search_input, category_filter, author_filter, word_limit, include_stopwords],
        outputs=refresh_outputs,
    )


app = gr.mount_gradio_app(app, gradio_app, path="/gradio")
