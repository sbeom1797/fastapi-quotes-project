import requests
from bs4 import BeautifulSoup
from database import get_connection

def crawl_quotes(category="life", limit=20):
    url = f"https://quotes.toscrape.com/tag/{category}/"
    response = requests.get(url)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    quotes = soup.select(".quote")[:limit]

    conn = get_connection()
    cur = conn.cursor()

    saved = 0

    for q in quotes:
        text = q.select_one(".text").get_text(strip=True)
        author = q.select_one(".author").get_text(strip=True)

        cur.execute(
            "INSERT INTO quotes (text, author, category) VALUES (?, ?, ?)",
            (text, author, category)
        )
        saved += 1

    conn.commit()
    conn.close()

    return saved
