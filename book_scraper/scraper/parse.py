"""Pure HTML -> data functions. No network access here, so it's all testable on fixtures."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Book, Category

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class ParseError(ValueError):
    pass


def parse_listing(html: str, page_url: str) -> tuple[list[str], str | None]:
    """Return (absolute book detail URLs, absolute next-page URL or None)."""
    soup = BeautifulSoup(html, "lxml")
    book_urls = [
        urljoin(page_url, a["href"])
        for a in soup.select("article.product_pod h3 a[href]")
    ]
    next_link = soup.select_one("li.next a[href]")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return book_urls, next_url


def parse_money(text: str) -> Decimal:
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ParseError(f"not a price: {text!r}") from None


def parse_stock(text: str) -> int:
    """'In stock (22 available)' -> 22, 'Out of stock' -> 0."""
    match = re.search(r"\((\d+) available\)", text)
    if match:
        return int(match.group(1))
    if "out of stock" in text.lower():
        return 0
    raise ParseError(f"unrecognised availability: {text!r}")


def category_slug(category_url: str) -> str:
    """'.../category/books/poetry_23/index.html' -> 'poetry_23'."""
    parts = [p for p in category_url.split("/") if p and p != "index.html"]
    return parts[-1]


def parse_book(html: str, book_url: str) -> Book:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("div.product_main")
    if main is None:
        raise ParseError(f"no product block on {book_url}")

    title = main.h1.get_text(strip=True)

    rating_tag = main.select_one("p.star-rating")
    rating_word = next((c for c in rating_tag["class"] if c in RATING_WORDS), None) if rating_tag else None
    if rating_word is None:
        raise ParseError(f"no rating on {book_url}")

    # Breadcrumb: Home > Books > <Category> > <Title>
    crumbs = soup.select("ul.breadcrumb li a[href]")
    if len(crumbs) < 3:
        raise ParseError(f"no category breadcrumb on {book_url}")
    cat_link = crumbs[2]
    category = Category(
        slug=category_slug(urljoin(book_url, cat_link["href"])),
        name=cat_link.get_text(strip=True),
    )

    table = {
        row.th.get_text(strip=True): row.td.get_text(strip=True)
        for row in soup.select("table.table tr")
        if row.th and row.td
    }
    price_tag = main.select_one("p.price_color")
    if "UPC" not in table or "Availability" not in table or price_tag is None:
        raise ParseError(f"missing UPC, availability or price on {book_url}")

    desc_header = soup.select_one("#product_description")
    desc_p = desc_header.find_next_sibling("p") if desc_header else None
    description = clean_description(desc_p.get_text(strip=True)) if desc_p else None

    img = soup.select_one("#product_gallery img[src]")
    image_url = urljoin(book_url, img["src"]) if img else None

    return Book(
        upc=table["UPC"],
        title=title,
        category=category,
        price=parse_money(price_tag.get_text(strip=True)),
        stock=parse_stock(table["Availability"]),
        rating=RATING_WORDS[rating_word],
        url=book_url,
        description=description,
        image_url=image_url,
    )


def clean_description(text: str) -> str | None:
    """Drop the site's trailing '...more' link text."""
    text = text.removesuffix("...more").strip()
    return text or None
