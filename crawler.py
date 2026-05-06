import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from database import get_connection


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
            "INSERT INTO quotes (text, author, category) VALUES (?, ?, ?)",
            (text, author, quote_category)
        )
        saved += 1

    conn.commit()
    conn.close()

    return saved
