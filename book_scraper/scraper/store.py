"""Sinks: where scraped records end up. Both write the schema in db/schema.sql.

Write order follows the foreign keys: scrape_runs -> categories -> books -> book_snapshots.
Upserts on the primary keys (categories.slug, books.upc) make re-runs idempotent.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod

from .models import Book, Category, ScrapeRun
from .supabase_client import SupabaseClient

BATCH_SIZE = 500


class Sink(ABC):
    @abstractmethod
    def start_run(self, run: ScrapeRun) -> int: ...

    @abstractmethod
    def upsert_categories(self, categories: list[Category]) -> None: ...

    @abstractmethod
    def upsert_books(self, books: list[Book]) -> None: ...

    @abstractmethod
    def insert_snapshots(self, run_id: int, books: list[Book]) -> None: ...

    @abstractmethod
    def finish_run(self, run_id: int, run: ScrapeRun) -> None: ...

    def save(self, run_id: int, books: list[Book]) -> None:
        self.upsert_categories(list({b.category for b in books}))
        self.upsert_books(books)
        self.insert_snapshots(run_id, books)


def _chunks(items: list, size: int = BATCH_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# --------------------------------------------------------------------------- SQLite

SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS categories (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
    upc TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category_slug TEXT NOT NULL REFERENCES categories(slug) ON DELETE RESTRICT,
    price TEXT NOT NULL,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    description TEXT,
    image_url TEXT,
    url TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS books_category_slug_idx ON books(category_slug);
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'partial', 'failed')),
    pages_scraped INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS book_snapshots (
    run_id INTEGER NOT NULL REFERENCES scrape_runs(id) ON DELETE CASCADE,
    upc TEXT NOT NULL REFERENCES books(upc) ON DELETE CASCADE,
    price TEXT NOT NULL,
    stock INTEGER NOT NULL,
    PRIMARY KEY (run_id, upc)
);
CREATE INDEX IF NOT EXISTS book_snapshots_upc_idx ON book_snapshots(upc);
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

    def upsert_categories(self, categories: list[Category]) -> None:
        self._upsert("categories", [c.to_row() for c in categories], key="slug")

    def upsert_books(self, books: list[Book]) -> None:
        self._upsert("books", [b.to_row() for b in books], key="upc")

    def insert_snapshots(self, run_id: int, books: list[Book]) -> None:
        self._upsert("book_snapshots", [b.snapshot_row(run_id) for b in books], key="run_id, upc")

    def finish_run(self, run_id: int, run: ScrapeRun) -> None:
        row = run.to_row()
        self.conn.execute(
            "UPDATE scrape_runs SET finished_at = ?, status = ?, pages_scraped = ?, errors = ? "
            "WHERE id = ?",
            (row["finished_at"], row["status"], row["pages_scraped"], row["errors"], run_id),
        )
        self.conn.commit()

    def _upsert(self, table: str, rows: list[dict], key: str) -> None:
        if not rows:
            return
        cols = list(rows[0])
        keys = {k.strip() for k in key.split(",")}
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in keys)
        self.conn.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT({key}) DO UPDATE SET {updates}",
            [tuple(r[c] for c in cols) for r in rows],
        )
        self.conn.commit()


# --------------------------------------------------------------------------- Supabase

class SupabaseSink(Sink):
    def __init__(self, client: SupabaseClient | None = None):
        self.client = client or SupabaseClient.from_env()

    def start_run(self, run: ScrapeRun) -> int:
        row = run.to_row()
        stored = self.client.insert("scrape_runs", [{"started_at": row["started_at"], "status": row["status"]}])
        return stored[0]["id"]

    def upsert_categories(self, categories: list[Category]) -> None:
        self._upsert("categories", [c.to_row() for c in categories], on_conflict="slug")

    def upsert_books(self, books: list[Book]) -> None:
        self._upsert("books", [b.to_row() for b in books], on_conflict="upc")

    def insert_snapshots(self, run_id: int, books: list[Book]) -> None:
        self._upsert("book_snapshots", [b.snapshot_row(run_id) for b in books], on_conflict="run_id,upc")

    def finish_run(self, run_id: int, run: ScrapeRun) -> None:
        row = run.to_row()
        row.pop("started_at")
        self.client.update("scrape_runs", row, id=f"eq.{run_id}")

    def _upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        for chunk in _chunks(rows):
            self.client.insert(table, chunk, on_conflict=on_conflict)


def make_sink(kind: str, sqlite_path: str = "books.db") -> Sink:
    if kind == "sqlite":
        return SqliteSink(sqlite_path)
    if kind == "supabase":
        return SupabaseSink()
    raise ValueError(f"unknown sink: {kind}")
