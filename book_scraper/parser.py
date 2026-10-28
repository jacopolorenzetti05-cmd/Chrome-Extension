"""Pure HTML -> record parsing for books.toscrape.com. No network, no DB."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import BookRecord, Category

BASE_URL = "https://books.toscrape.com/"

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
CURRENCY_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR"}

_MONEY_RE = re.compile(r"([£$€])?\s*(\d+(?:\.\d{1,2})?)")
_COUNT_RE = re.compile(r"\((\d+) available\)")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_money(text: str) -> tuple[int, str]:
    """'£51.77' -> (5177, 'GBP'). Integer pence avoids float rounding."""
    match = _MONEY_RE.search(text or "")
    if not match:
        raise ValueError(f"no price in {text!r}")
    symbol, amount = match.groups()
    pounds, _, pence = amount.partition(".")
    return int(pounds) * 100 + int(pence.ljust(2, "0")), CURRENCY_SYMBOLS.get(symbol, "GBP")


def parse_rating(tag) -> int | None:
    if tag is None:
        return None
    for cls in tag.get("class", []):
        if cls in RATING_WORDS:
            return RATING_WORDS[cls]
    return None


def parse_availability(text: str) -> tuple[bool, int]:
    """'In stock (22 available)' -> (True, 22)."""
    text = " ".join((text or "").split())
    in_stock = text.lower().startswith("in stock")
    match = _COUNT_RE.search(text)
    return in_stock, int(match.group(1)) if match else 0


def parse_categories(html: str, page_url: str = BASE_URL) -> list[Category]:
    """Category list from the sidebar of the index page."""
    soup = _soup(html)
    links = soup.select("div.side_categories ul li ul li a")
    return [Category(" ".join(a.get_text().split()), urljoin(page_url, a["href"])) for a in links]


def parse_listing_page(html: str, page_url: str) -> tuple[list[str], str | None]:
    """Return (absolute product URLs, absolute next-page URL or None)."""
    soup = _soup(html)
    products = [
        urljoin(page_url, a["href"])
        for a in soup.select("article.product_pod h3 a[href]")
    ]
    next_link = soup.select_one("li.next a[href]")
    return products, urljoin(page_url, next_link["href"]) if next_link else None


def parse_product_page(html: str, page_url: str) -> BookRecord:
    soup = _soup(html)
    main = soup.select_one("div.product_main")
    if main is None:
        raise ValueError(f"not a product page: {page_url}")

    table = {
        row.th.get_text(strip=True): row.td.get_text(strip=True)
        for row in soup.select("table.table-striped tr")
        if row.th and row.td
    }

    excl, currency = parse_money(table.get("Price (excl. tax)", ""))
    incl, _ = parse_money(table.get("Price (incl. tax)", ""))
    tax, _ = parse_money(table.get("Tax", "0"))
    in_stock, count = parse_availability(table.get("Availability", ""))

    # Breadcrumb: Home > Books > <Category> > <Title>
    crumbs = soup.select("ul.breadcrumb li a")
    category = category_url = None
    if len(crumbs) >= 3:
        category = " ".join(crumbs[2].get_text().split())
        category_url = urljoin(page_url, crumbs[2]["href"])

    desc_anchor = soup.select_one("#product_description")
    desc_tag = desc_anchor.find_next_sibling("p") if desc_anchor else None
    image = soup.select_one("#product_gallery img[src]")

    return BookRecord(
        upc=table.get("UPC", ""),
        title=main.h1.get_text(strip=True),
        url=page_url,
        price_excl_tax_pence=excl,
        price_incl_tax_pence=incl,
        tax_pence=tax,
        currency=currency,
        category=category,
        category_url=category_url,
        rating=parse_rating(main.select_one("p.star-rating")),
        availability=count,
        in_stock=in_stock,
        num_reviews=int(table.get("Number of reviews", "0") or 0),
        product_type=table.get("Product Type"),
        description=desc_tag.get_text(strip=True) if desc_tag else None,
        image_url=urljoin(page_url, image["src"]) if image else None,
    )
