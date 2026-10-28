# Book Scraper — Design

Source: **https://books.toscrape.com** only (a sandbox site built for scraping practice).
Target: a relational database (Supabase / Postgres) with linked tables.

## 1. What the site exposes, and what we keep

Every book is read from its detail page (the deepest level the site has; the reviews
page linked from it returns 404).

| Field | Where on the page | Kept? |
|---|---|---|
| title | `h1` | yes |
| price | `p.price_color` | yes, one `price` in GBP |
| stock | "In stock (22 available)" | yes, as a number |
| rating | `p.star-rating Three` | yes, 1–5 |
| category | breadcrumb, 3rd item | yes, as a link to `categories` |
| UPC | product table | yes, the book's key |
| description | `#product_description + p` | yes, with the trailing "...more" removed |
| cover image | `#product_gallery img` | yes, as an absolute URL |
| price excl./incl. tax, tax | product table | **no**: tax is 0.00 on every book, so both prices equal `price` |
| product type | product table | **no**: always "Books" |
| number of reviews | product table | **no**: always 0 |
| author | — | not on the site, and not needed |

## 2. Database schema

One identifier per thing, and nothing stored that can be worked out from something else.

```
categories 1 ──< books 1 ──< book_snapshots >── 1 scrape_runs
   slug          upc            (run_id, upc)          id
```

| Table | Key | Columns | Links |
|---|---|---|---|
| `categories` | `slug` (from the site, e.g. `poetry_23`) | name | — |
| `books` | `upc` (the site's product code) | title, price, stock, rating, description, image_url, url | `category_slug` → categories |
| `scrape_runs` | `id` (generated) | started_at, finished_at, status, pages_scraped, errors | — |
| `book_snapshots` | `(run_id, upc)` | price, stock | `run_id` → scrape_runs, `upc` → books |

Left out because they are derivable:
* a category's URL → `https://books.toscrape.com/catalogue/category/books/<slug>/index.html`
* books scraped in a run → `count(*)` of that run's snapshots
* when a book was first/last seen → `min`/`max` of `started_at` over its snapshots
* a snapshot's time → its run's `started_at`

Full DDL: `db/schema.sql`. `scraper/store.py` creates the same tables in SQLite for local runs.
Money is `numeric(10,2)` (never float), parsed with `Decimal`.

## 3. Data flow

```
fetch.py            parse.py               models.py            store.py
HTTP GET  ──html──▶ parse_listing()  ──▶   (book URLs)
HTTP GET  ──html──▶ parse_book()     ──▶   Book + Category ──▶  Sink.save(...)
                                           (validated)          ├─ SqliteSink   (local)
                                                                └─ SupabaseSink (REST API)
```

1. **Fetch** — one `requests.Session`, retries with backoff on 429/5xx, a timeout,
   a small delay between requests, a small thread pool for detail pages.
2. **Parse** — pure functions, HTML in, records out; tested on saved pages in `tests/fixtures/`.
3. **Validate** — UPC and title present, rating 1–5, price and stock ≥ 0. Bad records are
   logged, counted in `scrape_runs.errors`, and skipped.
4. **Store** — in foreign-key order: run → categories → books → snapshots. Upserts on the
   keys (`slug`, `upc`, `(run_id, upc)`) so re-running never creates duplicates.

## 4. Build path

1. Design (this file + `db/schema.sql`).
2. Scraper + local sink → check the data end to end (`python scrape.py --sink sqlite --limit 40`).
3. Supabase smoke test: write one row into `connection_test`, read it back
   (`python scripts/supabase_smoke_test.py`).
4. Same script checks the scraper tables are reachable.
5. Merge: `python scrape.py --sink supabase`.
