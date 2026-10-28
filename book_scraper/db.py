"""SQLite storage: schema, connection, writes and reads."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import BookRecord

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB = "books.db"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO scrape_runs (started_at) VALUES (?)", (now(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id: int, status: str, pages: int, books: int, errors: int) -> None:
    conn.execute(
        """UPDATE scrape_runs SET finished_at = ?, status = ?, pages_scraped = ?,
           books_scraped = ?, errors = ? WHERE run_id = ?""",
        (now(), status, pages, books, errors, run_id),
    )
    conn.commit()


def upsert_category(conn, name: str, url: str | None = None) -> int:
    conn.execute(
        """INSERT INTO categories (name, url) VALUES (?, ?)
           ON CONFLICT (name) DO UPDATE SET url = COALESCE(excluded.url, categories.url)""",
        (name, url),
    )
    return conn.execute("SELECT category_id FROM categories WHERE name = ?", (name,)).fetchone()[0]


def upsert_book(conn, book: BookRecord, run_id: int | None = None) -> int:
    """Insert or update a book (keyed on UPC) and record a snapshot. Returns book_id."""
    category_id = upsert_category(conn, book.category, book.category_url) if book.category else None
    conn.execute(
        """INSERT INTO books (upc, title, category_id, rating_id, price_excl_tax_pence,
               price_incl_tax_pence, tax_pence, currency, availability, in_stock,
               num_reviews, product_type, description, url, image_url,
               first_seen_run_id, last_seen_run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (upc) DO UPDATE SET
               title = excluded.title, category_id = excluded.category_id,
               rating_id = excluded.rating_id,
               price_excl_tax_pence = excluded.price_excl_tax_pence,
               price_incl_tax_pence = excluded.price_incl_tax_pence,
               tax_pence = excluded.tax_pence, currency = excluded.currency,
               availability = excluded.availability, in_stock = excluded.in_stock,
               num_reviews = excluded.num_reviews, product_type = excluded.product_type,
               description = excluded.description, url = excluded.url,
               image_url = excluded.image_url, last_seen_run_id = excluded.last_seen_run_id""",
        (book.upc, book.title, category_id, book.rating, book.price_excl_tax_pence,
         book.price_incl_tax_pence, book.tax_pence, book.currency, book.availability,
         int(book.in_stock), book.num_reviews, book.product_type, book.description,
         book.url, book.image_url, run_id, run_id),
    )
    book_id = conn.execute("SELECT book_id FROM books WHERE upc = ?", (book.upc,)).fetchone()[0]
    if run_id is not None:
        conn.execute(
            """INSERT OR REPLACE INTO book_snapshots
                   (book_id, run_id, price_incl_tax_pence, availability, in_stock, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (book_id, run_id, book.price_incl_tax_pence, book.availability,
             int(book.in_stock), now()),
        )
    return book_id


def get_book(conn, upc: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM v_books WHERE upc = ?", (upc,)).fetchone()


def summary(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "books": q("SELECT COUNT(*) FROM books"),
        "categories": q("SELECT COUNT(*) FROM categories"),
        "snapshots": q("SELECT COUNT(*) FROM book_snapshots"),
        "runs": q("SELECT COUNT(*) FROM scrape_runs"),
        "avg_price_gbp": q("SELECT ROUND(AVG(price_incl_tax_pence) / 100.0, 2) FROM books"),
    }
