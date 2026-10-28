"""Sinks: where scraped records end up. Both write the schema in db/schema.sql.

Write order follows the foreign keys: scrape_runs -> categories -> books -> book_snapshots.
Upserts on natural keys (categories.slug, books.upc) make re-runs idempotent.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod

from .models import Book, Category, ScrapeRun, utcnow
from .supabase_client import SupabaseClient

BATCH_SIZE = 500


class Sink(ABC):
    @abstractmethod
    def start_run(self, run: ScrapeRun) -> int: ...

    @abstractmethod
    def upsert_categories(self, categories: list[Category]) -> dict[str, int]:
        """Return {slug: category id}."""

    @abstractmethod
    def upsert_books(self, books: list[Book], category_ids: dict[str, int]) -> dict[str, int]:
        """Return {upc: book id}."""

    @abstractmethod
    def insert_snapshots(self, run_id: int, books: list[Book], book_ids: dict[str, int]) -> None: ...

    @abstractmethod
    def finish_run(self, run_id: int, run: ScrapeRun) -> None: ...

    def save(self, run_id: int, books: list[Book]) -> None:
        categories = list({b.category.slug: b.category for b in books}.values())
        category_ids = self.upsert_categories(categories)
        book_ids = self.upsert_books(books, category_ids)
        self.insert_snapshots(run_id, books, book_ids)


def _snapshot_row(run_id: int, book: Book, book_id: int) -> dict:
    return {
        "run_id": run_id,
        "book_id": book_id,
        "price_incl_tax": str(book.price_incl_tax),
        "stock": book.stock,
        "rating": book.rating,
    }


def _chunks(items: list, size: int = BATCH_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# --------------------------------------------------------------------------- SQLite

SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upc TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    price_excl_tax TEXT NOT NULL,
    price_incl_tax TEXT NOT NULL,
    tax TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'GBP',
    stock INTEGER NOT NULL CHECK (stock >= 0),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    num_reviews INTEGER NOT NULL DEFAULT 0,
    product_type TEXT,
    description TEXT,
    image_url TEXT,
    url TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS books_category_id_idx ON books(category_id);
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'partial', 'failed')),
    pages_scraped INTEGER NOT NULL DEFAULT 0,
    books_scraped INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS book_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES scrape_runs(id) ON DELETE CASCADE,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    price_incl_tax TEXT NOT NULL,
    stock INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, book_id)
);
CREATE INDEX IF NOT EXISTS book_snapshots_book_id_idx ON book_snapshots(book_id);
CREATE TABLE IF NOT EXISTS connection_test (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class SqliteSink(Sink):
    def __init__(self, path: str = "books.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SQLITE_SCHEMA)

    def start_run(self, run: ScrapeRun) -> int:
        row = run.to_row()
        cur = self.conn.execute(
            "INSERT INTO scrape_runs (started_at, status) VALUES (?, ?)",
            (row["started_at"], row["status"]),
        )
        self.conn.commit()
        return cur.lastrowid

    def upsert_categories(self, categories: list[Category]) -> dict[str, int]:
        self.conn.executemany(
            """INSERT INTO categories (name, slug, url) VALUES (?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET name = excluded.name, url = excluded.url""",
            [(c.name, c.slug, c.url) for c in categories],
        )
        self.conn.commit()
        slugs = [c.slug for c in categories]
        return self._ids("categories", "slug", slugs)

    def upsert_books(self, books: list[Book], category_ids: dict[str, int]) -> dict[str, int]:
        now = utcnow().isoformat()
        rows = [{**b.to_row(category_ids[b.category.slug]), "last_seen_at": now} for b in books]
        cols = list(rows[0]) if rows else []
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "upc")
        self.conn.executemany(
            f"INSERT INTO books ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT(upc) DO UPDATE SET {updates}",
            [tuple(r[c] for c in cols) for r in rows],
        )
        self.conn.commit()
        return self._ids("books", "upc", [b.upc for b in books])

    def insert_snapshots(self, run_id: int, books: list[Book], book_ids: dict[str, int]) -> None:
        rows = [_snapshot_row(run_id, b, book_ids[b.upc]) for b in books]
        self.conn.executemany(
            """INSERT OR REPLACE INTO book_snapshots (run_id, book_id, price_incl_tax, stock, rating)
               VALUES (:run_id, :book_id, :price_incl_tax, :stock, :rating)""",
            rows,
        )
        self.conn.commit()

    def finish_run(self, run_id: int, run: ScrapeRun) -> None:
        row = run.to_row()
        self.conn.execute(
            """UPDATE scrape_runs SET finished_at = ?, status = ?, pages_scraped = ?,
               books_scraped = ?, errors = ? WHERE id = ?""",
            (row["finished_at"], row["status"], row["pages_scraped"],
             row["books_scraped"], row["errors"], run_id),
        )
        self.conn.commit()

    def _ids(self, table: str, key: str, values: list[str]) -> dict[str, int]:
        ids = {}
        for chunk in _chunks(values):
            q = f"SELECT {key}, id FROM {table} WHERE {key} IN ({', '.join('?' * len(chunk))})"
            ids.update({r[0]: r[1] for r in self.conn.execute(q, chunk)})
        return ids


# --------------------------------------------------------------------------- Supabase

class SupabaseSink(Sink):
    def __init__(self, client: SupabaseClient | None = None):
        self.client = client or SupabaseClient.from_env()

    def start_run(self, run: ScrapeRun) -> int:
        row = run.to_row()
        stored = self.client.insert("scrape_runs", [{"started_at": row["started_at"], "status": row["status"]}])
        return stored[0]["id"]

    def upsert_categories(self, categories: list[Category]) -> dict[str, int]:
        rows = [{"name": c.name, "slug": c.slug, "url": c.url} for c in categories]
        ids = {}
        for chunk in _chunks(rows):
            for r in self.client.insert("categories", chunk, on_conflict="slug"):
                ids[r["slug"]] = r["id"]
        return ids

    def upsert_books(self, books: list[Book], category_ids: dict[str, int]) -> dict[str, int]:
        now = utcnow().isoformat()
        rows = [{**b.to_row(category_ids[b.category.slug]), "last_seen_at": now} for b in books]
        ids = {}
        for chunk in _chunks(rows):
            for r in self.client.insert("books", chunk, on_conflict="upc"):
                ids[r["upc"]] = r["id"]
        return ids

    def insert_snapshots(self, run_id: int, books: list[Book], book_ids: dict[str, int]) -> None:
        rows = [_snapshot_row(run_id, b, book_ids[b.upc]) for b in books]
        for chunk in _chunks(rows):
            self.client.insert("book_snapshots", chunk, on_conflict="run_id,book_id")

    def finish_run(self, run_id: int, run: ScrapeRun) -> None:
        row = run.to_row()
        row.pop("started_at")
        self.client.update("scrape_runs", row, id=f"eq.{run_id}")


def make_sink(kind: str, sqlite_path: str = "books.db") -> Sink:
    if kind == "sqlite":
        return SqliteSink(sqlite_path)
    if kind == "supabase":
        return SupabaseSink()
    raise ValueError(f"unknown sink: {kind}")
