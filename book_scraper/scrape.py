"""Entry point.

    python scrape.py --sink sqlite --limit 40      # local check
    python scrape.py --sink supabase               # full site into Supabase
"""

import argparse
import logging

from scraper.pipeline import run_scrape
from scraper.store import make_sink


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape books.toscrape.com into a linked database.")
    ap.add_argument("--sink", choices=("sqlite", "supabase"), default="sqlite")
    ap.add_argument("--db", default="books.db", help="SQLite file (sqlite sink only)")
    ap.add_argument("--limit", type=int, help="stop after this many books")
    ap.add_argument("--max-pages", type=int, help="stop after this many listing pages")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.1, help="min seconds between requests")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sink = make_sink(args.sink, sqlite_path=args.db)
    run = run_scrape(sink, limit=args.limit, max_pages=args.max_pages,
                     workers=args.workers, delay=args.delay)
    return 0 if run.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
