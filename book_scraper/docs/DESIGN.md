# Book Scraper — Design

Source: **https://books.toscrape.com** only (a sandbox site built for scraping practice).
Target: a relational database (Supabase / Postgres) with linked tables.

## 1. What the site actually exposes

| Where | Field | Notes |
|---|---|---|
| Listing page `/catalogue/page-N.html` | link to each book | 20 books/page, 50 pages, 1000 books. `li.next` tells us if there's another page. |
| Detail page `h1` | title | full title (listing titles are truncated with `...`) |
| Detail page `p.star-rating <Word>` | rating | `One`..`Five` → 1..5 |
| Detail page `#product_description + p` | description | missing on a few books → `NULL` |
| Detail page breadcrumb, 3rd item | category | e.g. `Poetry`, link `../category/books/poetry_23/index.html` |
| Detail page `table` | UPC, Product Type, Price excl/incl tax, Tax, Availability, Number of reviews | prices in `£` |
| Detail page `#product_gallery img` | cover image URL | relative → made absolute |

**There is no author on books.toscrape.com.** The schema leaves out an `authors` table
on purpose: filling it would mean making data up. If authors are needed later they
must come from another source (e.g. an ISBN lookup), and the place for them is an
`authors` + `book_authors` pair of tables (many-to-many).

## 2. Database schema

```
categories 1 ──< books 1 ──< book_snapshots >── 1 scrape_runs
```

* **categories** — one row per genre. Natural key: `slug`.
* **books** — one row per book. Natural key: `upc` (unique on the site). Holds the
  *current* state (latest price/stock) plus `first_seen_at` / `last_seen_at`.
* **scrape_runs** — one row per execution of the scraper (when it ran, how many books, status).
* **book_snapshots** — what a book looked like during one run (price, stock, rating).
  This is the link between books and runs and gives price/stock history across runs.
  Unique on `(run_id, book_id)`.
* **connection_test** — a scratch table used only by the Supabase smoke test.

Full DDL: `db/schema.sql` (Postgres/Supabase). `scraper/store.py` creates the same
tables in SQLite for local runs and tests.

Money is `numeric(10,2)` in Postgres (never float), parsed with `Decimal`.

## 3. Data flow

```
fetch.py            parse.py               models.py            store.py
HTTP GET  ──html──▶ parse_listing()  ──▶   (book URLs)
HTTP GET  ──html──▶ parse_book()     ──▶   Book + Category ──▶  Sink.save_run(...)
                                           (validated)          ├─ SqliteSink   (local)
                                                                └─ SupabaseSink (REST API)
```

1. **Fetch** — one `requests.Session`, retries with backoff on 429/5xx, a timeout,
   and a small delay so we stay polite. Detail pages are fetched with a small thread pool.
2. **Parse** — pure functions: HTML string in, plain dict out. No network, so they
   can be tested against saved HTML in `tests/fixtures/`.
3. **Model + validate** — dicts become `Category` / `Book` dataclasses; `validate()`
   checks the invariants (UPC present, rating 1–5, `price_incl = price_excl + tax`,
   stock ≥ 0). Bad records are logged and skipped, not written.
4. **Store** — a sink writes in dependency order: run → categories → books → snapshots,
   using upserts on the natural keys so re-running never creates duplicates.

## 4. Build path

1. Design (this file + `db/schema.sql`).
2. Scraper + local sink → check the data end to end (`python scrape.py --sink sqlite --limit 40`).
3. Supabase smoke test: write one row into `connection_test`, read it back
   (`python scripts/supabase_smoke_test.py`).
4. Test connection to the real tables (smoke test also checks that `books` etc. exist).
5. Merge: `python scrape.py --sink supabase`.
