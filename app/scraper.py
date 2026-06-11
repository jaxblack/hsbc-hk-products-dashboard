from __future__ import annotations

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def collect_public_products() -> list[dict[str, str]]:
    placeholder_html = """
    <section>
      <article data-status="placeholder">
        <h2>Placeholder product entry</h2>
        <p>Public-page parsing is not implemented yet.</p>
      </article>
    </section>
    """
    soup = BeautifulSoup(placeholder_html, "html.parser")
    article = soup.select_one("article")
    async with async_playwright():
        return [
            {
                "name": article.h2.get_text(strip=True) if article and article.h2 else "Placeholder",
                "status": article.get("data-status", "placeholder") if article else "placeholder",
                "note": article.p.get_text(strip=True) if article and article.p else "",
            }
        ]
