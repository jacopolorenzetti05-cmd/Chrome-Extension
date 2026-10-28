# Book scraper → linked database

Scrapes **books.toscrape.com** (only) into a relational schema in Supabase, or into a
local SQLite file for testing. Design notes: [`docs/DESIGN.md`](docs/DESIGN.md).

```
categories 1 ──< books 1 ──< book_snapshots >── 1 scrape_runs
   slug          upc            (run_id, upc)          id
```

## Layout

| File | Role |
|---|---|
| `db/schema.sql` | Postgres/Supabase tables, keys, constraints |
| `scraper/fetch.py` | HTTP session, retries, throttle, locked to books.toscrape.com |
| `scraper/parse.py` | HTML → `Book` / `Category` (pure, tested on saved pages) |
| `scraper/models.py` | Dataclasses + `validate()` |
| `scraper/store.py` | `SqliteSink` and `SupabaseSink` (same interface, upserts) |
| `scraper/supabase_client.py` | Small Supabase REST client |
| `scraper/pipeline.py` | crawl → parse → validate → store, records a `scrape_runs` row |
| `scrape.py` | CLI |
| `scripts/supabase_smoke_test.py` | write one row, read it back, check tables |
| `app/server.py` | Library app: read-only JSON API + serves the page |
| `app/static/index.html` | Library app UI: title search, subject/price/rating filters, sort, book cards |

## Run it

```bash
cd book_scraper
pip install -r requirements.txt

# Offline tests
python -m unittest discover tests

# Step 2: check the data flow locally (SQLite file books.db)
python scrape.py --sink sqlite --limit 40
python scrape.py --sink sqlite              # whole site, ~2 min

# Steps 3-4: Supabase
#   a) In the Supabase dashboard → SQL editor, run db/schema.sql
#   b) cp .env.example .env and fill in SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
python scripts/supabase_smoke_test.py

# Step 5: merge — scraper writes straight into Supabase
python scrape.py --sink supabase --limit 40   # small first
python scrape.py --sink supabase
```

Re-running is safe: categories upsert on `slug`, books on `upc`, and each run adds one
`scrape_runs` row plus one `book_snapshots` row per book (price/stock history).

If you already ran an earlier `schema.sql` in Supabase, run the `drop` lines at the top of
the file first, then the whole file again.

## Browse it: the library app

```bash
python app/server.py          # then open http://localhost:8000
```

Search by title, filter by subject (category), price range and minimum rating, and sort by
title, price, rating or copies on hand. Click a book for its catalogue card: description,
stock, and its price/stock in each scrape run (`book_snapshots`). The tables are locked by
RLS, so the server keeps the service_role key and the browser only sees the read-only API.

## Notes

* No author (not on the site) and no tax/review/product-type columns (constant on every
  book) — see DESIGN.md.
* Uses the `service_role` key, which bypasses Row Level Security. To use the `anon`
  key instead, add RLS policies that allow inserts/updates on these tables.
