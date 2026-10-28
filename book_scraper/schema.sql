PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    url         TEXT
);

CREATE TABLE IF NOT EXISTS ratings (
    rating_id INTEGER PRIMARY KEY CHECK (rating_id BETWEEN 1 AND 5),
    label     TEXT NOT NULL UNIQUE
);

INSERT OR IGNORE INTO ratings (rating_id, label) VALUES
    (1, 'One'), (2, 'Two'), (3, 'Three'), (4, 'Four'), (5, 'Five');

CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'ok', 'failed')),
    pages_scraped INTEGER NOT NULL DEFAULT 0,
    books_scraped INTEGER NOT NULL DEFAULT 0,
    errors        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS books (
    book_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upc                  TEXT NOT NULL UNIQUE,
    title                TEXT NOT NULL,
    category_id          INTEGER REFERENCES categories (category_id),
    rating_id            INTEGER REFERENCES ratings (rating_id),
    price_excl_tax_pence INTEGER NOT NULL CHECK (price_excl_tax_pence >= 0),
    price_incl_tax_pence INTEGER NOT NULL CHECK (price_incl_tax_pence >= 0),
    tax_pence            INTEGER NOT NULL DEFAULT 0,
    currency             TEXT NOT NULL DEFAULT 'GBP',
    availability         INTEGER NOT NULL DEFAULT 0,
    in_stock             INTEGER NOT NULL DEFAULT 0 CHECK (in_stock IN (0, 1)),
    num_reviews          INTEGER NOT NULL DEFAULT 0,
    product_type         TEXT,
    description          TEXT,
    url                  TEXT NOT NULL UNIQUE,
    image_url            TEXT,
    first_seen_run_id    INTEGER REFERENCES scrape_runs (run_id),
    last_seen_run_id     INTEGER REFERENCES scrape_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_books_category ON books (category_id);
CREATE INDEX IF NOT EXISTS idx_books_rating   ON books (rating_id);

CREATE TABLE IF NOT EXISTS book_snapshots (
    snapshot_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id              INTEGER NOT NULL REFERENCES books (book_id) ON DELETE CASCADE,
    run_id               INTEGER NOT NULL REFERENCES scrape_runs (run_id),
    price_incl_tax_pence INTEGER NOT NULL,
    availability         INTEGER NOT NULL,
    in_stock             INTEGER NOT NULL,
    scraped_at           TEXT NOT NULL,
    UNIQUE (book_id, run_id)
);

-- Convenience view: one denormalised row per book.
CREATE VIEW IF NOT EXISTS v_books AS
SELECT b.book_id, b.upc, b.title, c.name AS category, r.rating_id AS rating,
       b.price_incl_tax_pence / 100.0 AS price_gbp, b.availability, b.in_stock,
       b.num_reviews, b.url
FROM books b
LEFT JOIN categories c ON c.category_id = b.category_id
LEFT JOIN ratings r    ON r.rating_id   = b.rating_id;
