# Book Scraper — Design

Source: **https://books.toscrape.com** only (a sandbox site built for scraping:
1000 books, 50 catalogue pages of 20, 50 categories).

The scraper is designed *backwards from the database*: the schema below is the
contract, and every scraped field exists because a column needs it.

## 1. Database schema (SQLite)

```
 categories                 books                              ratings
 ──────────                 ─────                              ───────
 category_id  PK  ◄──┐      book_id            PK              rating_id  PK (1..5)
 name         UQ     └───── category_id        FK ──┐   ┌────► label      ("One".."Five")
 url                        rating_id          FK ──┼───┘
                            upc                UQ   │
                            title                   │
                            price_excl_tax_pence    │      scrape_runs
                            price_incl_tax_pence    │      ───────────
                            tax_pence               │  ┌─► run_id      PK
                            currency                │  │   started_at
                            availability            │  │   finished_at
                            in_stock                │  │   status       (running|ok|failed)
                            num_reviews             │  │   pages_scraped
                            product_type            │  │   books_scraped
                            description             │  │   errors
                            url                UQ   │  │
                            image_url               │  │
                            first_seen_run_id  FK ──┼──┤
                            last_seen_run_id   FK ──┼──┤
                                                    │  │
 book_snapshots  (one row per book per run — price/stock history)
 ──────────────
 snapshot_id  PK
 book_id      FK ─► books.book_id
 run_id       FK ─► scrape_runs.run_id
 price_incl_tax_pence, availability, in_stock, scraped_at
 UNIQUE (book_id, run_id)
```

Design decisions:

* **`book_id`** is our surrogate key; **`upc`** is the site's natural key and is
  `UNIQUE`, so re-running the scraper *updates* books instead of duplicating.
* **Money is stored as integer pence** (`£51.77` → `5177`) to avoid float
  rounding; `currency` keeps the symbol's ISO code (`GBP`).
* **Ratings** are a 5-row lookup table so `rating_id` is a real foreign key.
* **`scrape_runs` + `book_snapshots`** make every run auditable and give price
  and stock history across runs, while `books` always holds the latest state.
* **No `authors` table.** books.toscrape.com does not publish authors anywhere
  (not on listings nor product pages). Rather than store fabricated or empty
  data, the schema leaves it out; it can be added later from another source.

## 2. Data flow

```
  fetcher.Fetcher            parser (pure functions)             db
  ───────────────            ───────────────────────             ──
  GET index.html ──────────► parse_categories()  ─► [Category] ─► upsert_category
  GET catalogue/page-N ────► parse_listing_page() ─► product URLs + next page URL
  GET product page ────────► parse_product_page() ─► BookRecord ─► validate()
                                                                   └► upsert_book
                                                                   └► insert_snapshot
```

* `fetcher.py` – HTTP only: session, retries with backoff, polite delay,
  forced UTF-8 decoding (the site's headers make `requests` guess Latin-1,
  which turns `£` into `Â£`).
* `parser.py` – HTML → typed records. No network, no DB: fully unit-testable.
* `models.py` – `Category`, `BookRecord` dataclasses + `validate()`; this is the
  internal contract between parser and DB.
* `db.py` – schema creation, connection, upserts, reads.
* `pipeline.py` – the "merge": wires fetcher → parser → db inside one
  `scrape_run`.

## 3. Build path (each step is a CLI command)

| Step | Goal                                   | Command                                  |
|------|----------------------------------------|------------------------------------------|
| 1    | Design                                 | this document + `schema.sql`             |
| 2    | Data flows internally and makes sense  | `python -m book_scraper sample`          |
| 3    | Sub-base: write one row, read it back  | `python -m book_scraper smoke`           |
| 4    | Test connection (site + DB)            | `python -m book_scraper check`           |
| 5    | Merge: full scrape into the database   | `python -m book_scraper run`             |

Tests: `python -m unittest discover -s tests` (offline, HTML fixtures).
