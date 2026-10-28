"""Crawl -> parse -> validate -> store. The one place the pieces are wired together."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests

from .fetch import BASE_URL, Fetcher
from .models import Book, ScrapeRun, utcnow
from .parse import ParseError, parse_book, parse_listing
from .store import Sink

log = logging.getLogger(__name__)

START_URL = urljoin(BASE_URL, "catalogue/page-1.html")


def collect_book_urls(fetcher: Fetcher, run: ScrapeRun, limit: int | None = None,
                      max_pages: int | None = None) -> list[str]:
    """Walk the listing pages via the 'next' link until we have enough URLs."""
    urls: list[str] = []
    page_url: str | None = START_URL
    while page_url:
        if max_pages is not None and run.pages_scraped >= max_pages:
            break
        page_urls, page_url = parse_listing(fetcher.get(page_url), page_url)
        run.pages_scraped += 1
        urls.extend(page_urls)
        log.info("listing page %d: %d books (total %d)", run.pages_scraped, len(page_urls), len(urls))
        if limit is not None and len(urls) >= limit:
            return urls[:limit]
    return urls


def scrape_books(fetcher: Fetcher, urls: list[str], run: ScrapeRun, workers: int = 8) -> list[Book]:
    """Fetch and parse detail pages; keep only valid, unique books."""
    books: dict[str, Book] = {}

    def fetch_one(url: str) -> Book:
        return parse_book(fetcher.get(url), url)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, url): url for url in urls}
        for done, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            try:
                book = future.result()
            except (ParseError, requests.RequestException) as exc:
                run.errors += 1
                log.warning("skipping %s: %s", url, exc)
                continue
            problems = book.validate()
            if problems:
                run.errors += 1
                log.warning("invalid book %s: %s", url, "; ".join(problems))
                continue
            if book.upc in books:
                log.warning("duplicate upc %s at %s", book.upc, url)
                continue
            books[book.upc] = book
            if done % 100 == 0:
                log.info("parsed %d/%d detail pages", done, len(urls))
    # Keep the site's listing order so runs are reproducible.
    order = {url: i for i, url in enumerate(urls)}
    return sorted(books.values(), key=lambda b: order[b.url])


def run_scrape(sink: Sink, limit: int | None = None, max_pages: int | None = None,
               workers: int = 8, delay: float = 0.1) -> ScrapeRun:
    fetcher = Fetcher(delay=delay, pool_size=workers)
    run = ScrapeRun()
    run_id = sink.start_run(run)
    log.info("scrape run %s started", run_id)
    try:
        urls = collect_book_urls(fetcher, run, limit=limit, max_pages=max_pages)
        books = scrape_books(fetcher, urls, run, workers=workers)
        sink.save(run_id, books)
        run.books_scraped = len(books)
        run.status = "success" if run.errors == 0 else "partial"
    except Exception:
        run.status = "failed"
        log.exception("scrape run %s failed", run_id)
        raise
    finally:
        run.finished_at = utcnow()
        sink.finish_run(run_id, run)
        log.info("scrape run %s %s: %d pages, %d books, %d errors",
                 run_id, run.status, run.pages_scraped, run.books_scraped, run.errors)
    return run
