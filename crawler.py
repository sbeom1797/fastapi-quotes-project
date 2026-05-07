import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from database import get_connection


DEFAULT_CATEGORIES = ["life", "love", "books", "inspirational", "humor"]


def crawl_quotes(category="life", limit=20):
    url = f"https://quotes.toscrape.com/tag/{category}/"
    collected = []

    while url and len(collected) < limit:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        for quote in soup.select(".quote"):
            text = quote.select_one(".text").get_text(strip=True)
            author = quote.select_one(".author").get_text(strip=True)
            collected.append((text, author, category))

            if len(collected) >= limit:
                break

        next_link = soup.select_one("li.next a")
        url = urljoin(url, next_link["href"]) if next_link else None

    conn = get_connection()
    cur = conn.cursor()

    saved = 0

    for text, author, quote_category in collected:
        cur.execute(
            "INSERT OR IGNORE INTO quotes (text, author, category) VALUES (?, ?, ?)",
            (text, author, quote_category)
        )
        saved += cur.rowcount

    conn.commit()
    conn.close()

    return saved


def crawl_multiple_categories(categories=None, limit=20):
    categories = categories or DEFAULT_CATEGORIES
    results = {}

    for category in categories:
        normalized = category.strip()
        if not normalized:
            continue
        results[normalized] = crawl_quotes(normalized, limit)

    return results
