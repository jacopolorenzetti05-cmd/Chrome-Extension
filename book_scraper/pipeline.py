"""The merge: fetcher -> parser -> validate -> db, inside one scrape run."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from . import db
from .models import BookRecord, validate
from .parser import BASE_URL, parse_categories, parse_listing_page, parse_product_page

log = logging.getLogger(__name__)

START_URL = BASE_URL + "catalogue/page-1.html"


class Fetches(Protocol):
    def get(self, url: str) -> str: ...


def scrape_book(fetcher: Fetches, url: str) -> BookRecord:
    return validate(parse_product_page(fetcher.get(url), url))


def run(conn, fetcher: Fetches, start_url: str = START_URL,
        max_pages: int | None = None, workers: int = 4) -> dict:
    run_id = db.start_run(conn)
    pages = books = errors = 0
    try:
        for category in parse_categories(fetcher.get(BASE_URL + "index.html")):
            db.upsert_category(conn, category.name, category.url)
        conn.commit()

        url: str | None = start_url
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while url and (max_pages is None or pages < max_pages):
                product_urls, url = parse_listing_page(fetcher.get(url), url)
                pages += 1
                # Fetch/parse in threads; write to SQLite from this thread only.
                futures = {u: pool.submit(scrape_book, fetcher, u) for u in product_urls}
                for product_url, future in futures.items():
                    try:
                        db.upsert_book(conn, future.result(), run_id)
                        books += 1
                    except Exception as exc:  # one bad book must not kill the run
                        errors += 1
                        log.warning("skipped %s: %s", product_url, exc)
                conn.commit()
                log.info("page %d: %d books total, %d errors", pages, books, errors)
    except Exception:
        conn.rollback()
        db.finish_run(conn, run_id, "failed", pages, books, errors + 1)
        raise
    db.finish_run(conn, run_id, "ok", pages, books, errors)
    return {"run_id": run_id, "pages": pages, "books": books, "errors": errors}
