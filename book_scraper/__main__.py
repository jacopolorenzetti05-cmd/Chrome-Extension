"""CLI: one command per build step (see DESIGN.md)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

from . import db, pipeline
from .fetcher import Fetcher
from .models import BookRecord, validate
from .parser import BASE_URL, parse_listing_page, parse_product_page


def cmd_sample(args) -> int:
    """Step 2: scrape one listing page + one product and show the record."""
    fetcher = Fetcher()
    product_urls, next_url = parse_listing_page(fetcher.get(args.url), args.url)
    print(f"listing: {len(product_urls)} products, next page: {next_url}")
    book = validate(parse_product_page(fetcher.get(product_urls[0]), product_urls[0]))
    print(json.dumps(book.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_smoke(args) -> int:
    """Step 3: write one row to a sub-database and read it back."""
    path = args.db or Path(tempfile.mkdtemp()) / "smoke.db"
    record = BookRecord(
        upc="smoke-test-0001", title="Smoke Test Book",
        url=BASE_URL + "catalogue/smoke-test_0/index.html",
        price_excl_tax_pence=1000, price_incl_tax_pence=1000, tax_pence=0,
        category="Test", rating=3, availability=1, in_stock=True,
    )
    with db.connect(path) as conn:
        run_id = db.start_run(conn)
        db.upsert_book(conn, validate(record), run_id)
        conn.commit()
        row = db.get_book(conn, record.upc)
    print(f"database: {path}")
    print("read back:", dict(row) if row else None)
    ok = row is not None and row["title"] == record.title and row["price_gbp"] == 10.0
    print("SMOKE OK" if ok else "SMOKE FAILED")
    return 0 if ok else 1


def cmd_check(args) -> int:
    """Step 4: test the connection to the site and to the database."""
    ok = True
    try:
        html = Fetcher(delay=0).get(BASE_URL + "index.html")
        print(f"site: OK ({len(html)} bytes from {BASE_URL})")
    except Exception as exc:
        ok = False
        print(f"site: FAILED ({exc})")
    try:
        with db.connect(args.db) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        print(f"database: OK ({args.db}; tables: {', '.join(tables)})")
    except Exception as exc:
        ok = False
        print(f"database: FAILED ({exc})")
    return 0 if ok else 1


def cmd_run(args) -> int:
    """Step 5: the full scrape into the database."""
    with db.connect(args.db) as conn:
        result = pipeline.run(conn, Fetcher(delay=args.delay),
                              max_pages=args.max_pages, workers=args.workers)
        print(json.dumps({**result, **db.summary(conn)}, indent=2))
    return 0 if result["errors"] == 0 else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="book_scraper", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="step 2: scrape one book and print it")
    p.add_argument("--url", default=pipeline.START_URL)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("smoke", help="step 3: write one row, read it back")
    p.add_argument("--db", help="database file (default: a fresh temp file)")
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("check", help="step 4: test site and database connection")
    p.add_argument("--db", default=db.DEFAULT_DB)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("run", help="step 5: full scrape into the database")
    p.add_argument("--db", default=db.DEFAULT_DB)
    p.add_argument("--max-pages", type=int, help="stop after N listing pages (50 = all)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--delay", type=float, default=0.1, help="seconds between requests per worker")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
