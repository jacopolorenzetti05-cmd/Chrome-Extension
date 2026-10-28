"""Offline tests: run with `python -m unittest discover tests`."""

import dataclasses
import itertools
import unittest
from decimal import Decimal
from pathlib import Path

from scraper.models import Book, Category, ScrapeRun
from scraper.parse import ParseError, clean_description, parse_book, parse_listing, parse_stock
from scraper.store import SqliteSink, SupabaseSink

FIXTURES = Path(__file__).parent / "fixtures"
BOOK_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_book(upc="u1", slug="poetry_23", price="10.00", stock=3) -> Book:
    return Book(
        upc=upc, title="T",
        category=Category(slug=slug, name=slug.split("_")[0].title()),
        price=Decimal(price), stock=stock, rating=3,
        url=f"https://books.toscrape.com/catalogue/{upc}/index.html",
    )


class ParseTests(unittest.TestCase):
    def test_listing_first_page(self):
        urls, next_url = parse_listing(fixture("listing_page1.html"),
                                       "https://books.toscrape.com/catalogue/page-1.html")
        self.assertEqual(len(urls), 20)
        self.assertEqual(urls[0], BOOK_URL)
        self.assertEqual(next_url, "https://books.toscrape.com/catalogue/page-2.html")

    def test_listing_last_page_has_no_next(self):
        urls, next_url = parse_listing(fixture("listing_page50.html"),
                                       "https://books.toscrape.com/catalogue/page-50.html")
        self.assertEqual(len(urls), 20)
        self.assertIsNone(next_url)

    def test_book_detail(self):
        book = parse_book(fixture("book_detail.html"), BOOK_URL)
        self.assertEqual(book.upc, "a897fe39b1053632")
        self.assertEqual(book.title, "A Light in the Attic")
        self.assertEqual(book.price, Decimal("51.77"))
        self.assertEqual(book.stock, 22)
        self.assertEqual(book.rating, 3)
        self.assertEqual(book.category, Category(slug="poetry_23", name="Poetry"))
        self.assertTrue(book.description.startswith("It's hard to imagine a world without"))
        self.assertFalse(book.description.endswith("more"))
        self.assertTrue(book.image_url.startswith("https://books.toscrape.com/media/cache/"))
        self.assertEqual(book.validate(), [])

    def test_stock_text(self):
        self.assertEqual(parse_stock("In stock (1 available)"), 1)
        self.assertEqual(parse_stock("Out of stock"), 0)
        with self.assertRaises(ParseError):
            parse_stock("Coming soon")

    def test_clean_description(self):
        self.assertEqual(clean_description("Good book. ...more"), "Good book.")
        self.assertEqual(clean_description("No suffix"), "No suffix")
        self.assertIsNone(clean_description("...more"))

    def test_clean_description_drops_cut_off_preview(self):
        full = "A long opening sentence that goes on for a while. Then the rest of it."
        self.assertEqual(clean_description(full[:55] + " " + full + " ...more"), full)
        # the preview may lose a space or invisible character the full text has
        self.assertEqual(clean_description(full[:55].replace("for a", "fora") + " " + full), full)
        # a text that just happens to repeat a phrase later is left alone
        text = "A long opening sentence that goes on for a while. Different. " \
               "A long opening sentence that goes on for a while, again."
        self.assertEqual(clean_description(text), text)

    def test_non_product_page_raises(self):
        with self.assertRaises(ParseError):
            parse_book(fixture("listing_page1.html"), BOOK_URL)


class ValidateTests(unittest.TestCase):
    def test_catches_bad_records(self):
        book = dataclasses.replace(make_book(), rating=7, stock=-1, price=Decimal("-1"))
        problems = book.validate()
        self.assertTrue(any("rating" in p for p in problems))
        self.assertTrue(any("stock" in p for p in problems))
        self.assertTrue(any("price" in p for p in problems))


class SqliteSinkTests(unittest.TestCase):
    def setUp(self):
        self.sink = SqliteSink(":memory:")
        self.db = self.sink.conn

    def run_once(self, books):
        run = ScrapeRun()
        run_id = self.sink.start_run(run)
        self.sink.save(run_id, books)
        run.status = "success"
        self.sink.finish_run(run_id, run)
        return run_id

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_rows_are_linked(self):
        books = [make_book("u1", slug="poetry_23"), make_book("u2", slug="poetry_23"),
                 make_book("u3", slug="travel_2")]
        run_id = self.run_once(books)
        self.assertEqual(self.count("categories"), 2)
        self.assertEqual(self.count("books"), 3)
        self.assertEqual(self.count("book_snapshots"), 3)
        rows = self.db.execute(
            """SELECT b.upc, c.name FROM books b JOIN categories c ON c.slug = b.category_slug
               ORDER BY b.upc""").fetchall()
        self.assertEqual([tuple(r) for r in rows],
                         [("u1", "Poetry"), ("u2", "Poetry"), ("u3", "Travel")])
        status = self.db.execute("SELECT status FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()[0]
        self.assertEqual(status, "success")

    def test_rerun_updates_instead_of_duplicating(self):
        self.run_once([make_book("u1", price="10.00", stock=3)])
        self.run_once([make_book("u1", price="12.50", stock=1)])
        self.assertEqual(self.count("books"), 1)
        self.assertEqual(self.count("categories"), 1)
        self.assertEqual(self.count("scrape_runs"), 2)
        price, stock = self.db.execute("SELECT price, stock FROM books").fetchone()
        self.assertEqual((price, stock), ("12.50", 1))
        history = self.db.execute("SELECT price FROM book_snapshots ORDER BY run_id").fetchall()
        self.assertEqual([r[0] for r in history], ["10.00", "12.50"])

    def test_foreign_keys_are_enforced(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO books (upc, title, category_slug, price, stock, rating, url) "
                            "VALUES ('x', 't', 'no_such_category', '1.00', 1, 3, 'u')")


class FakeSupabase:
    """In-memory stand-in for SupabaseClient that honours on_conflict like PostgREST."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.ids = itertools.count(1)

    def insert(self, table, rows, on_conflict=None):
        stored = self.tables.setdefault(table, [])
        keys = on_conflict.split(",") if on_conflict else None
        out = []
        for row in rows:
            existing = next((r for r in stored if keys and all(r[k] == row[k] for k in keys)), None)
            if existing:
                existing.update(row)
            else:
                existing = dict(row) if keys else {"id": next(self.ids), **row}
                stored.append(existing)
            out.append(dict(existing))
        return out

    def update(self, table, values, **filters):
        target = int(filters["id"].removeprefix("eq."))
        for r in self.tables[table]:
            if r["id"] == target:
                r.update(values)
        return []


class SupabaseSinkTests(unittest.TestCase):
    def test_writes_linked_rows(self):
        fake = FakeSupabase()
        sink = SupabaseSink(client=fake)
        for price in ("10.00", "11.00"):
            run = ScrapeRun()
            run_id = sink.start_run(run)
            sink.save(run_id, [make_book("u1", price=price), make_book("u2", slug="travel_2")])
            run.status = "success"
            sink.finish_run(run_id, run)

        t = fake.tables
        self.assertEqual(len(t["categories"]), 2)
        self.assertEqual(len(t["books"]), 2)
        self.assertEqual(len(t["scrape_runs"]), 2)
        self.assertEqual(len(t["book_snapshots"]), 4)
        slugs = {c["slug"] for c in t["categories"]}
        upcs = {b["upc"] for b in t["books"]}
        run_ids = {r["id"] for r in t["scrape_runs"]}
        self.assertTrue(all(b["category_slug"] in slugs for b in t["books"]))
        self.assertTrue(all(s["upc"] in upcs and s["run_id"] in run_ids for s in t["book_snapshots"]))
        u1 = next(b for b in t["books"] if b["upc"] == "u1")
        self.assertEqual(u1["price"], "11.00")
        self.assertTrue(all(r["status"] == "success" for r in t["scrape_runs"]))


if __name__ == "__main__":
    unittest.main()
