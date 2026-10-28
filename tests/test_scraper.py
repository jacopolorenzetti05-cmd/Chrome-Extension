"""Offline tests: parser, validation, database and the full pipeline."""
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path

from book_scraper import db, pipeline
from book_scraper.models import ValidationError, validate
from book_scraper.parser import (BASE_URL, parse_availability, parse_categories,
                                 parse_listing_page, parse_money, parse_product_page)

FIXTURES = Path(__file__).with_name("fixtures")
PRODUCT_HTML = (FIXTURES / "product_page.html").read_text(encoding="utf-8")
LISTING_HTML = (FIXTURES / "listing_page.html").read_text(encoding="utf-8")
PAGE_1 = BASE_URL + "catalogue/page-1.html"
PRODUCT_URL = BASE_URL + "catalogue/a-light-in-the-attic_1000/index.html"


def product_html(upc, title, price):
    return (PRODUCT_HTML.replace("a897fe39b1053632", upc)
            .replace("A Light in the Attic", title).replace("£51.77", price))


class FakeFetcher:
    """Serves canned HTML by URL, so the pipeline runs without network."""

    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        return self.pages[url]


def fake_site(velvet_price="£53.74"):
    page_2 = (LISTING_HTML.replace('<li class="next"><a href="page-2.html">next</a></li>', "")
              .replace("a-light-in-the-attic_1000", "soumission_998")
              .replace("tipping-the-velvet_999", "broken-book_997"))
    cat = lambda slug: BASE_URL + f"catalogue/{slug}/index.html"
    return {
        BASE_URL + "index.html": LISTING_HTML.replace('href="category', 'href="catalogue/category'),
        PAGE_1: LISTING_HTML,
        BASE_URL + "catalogue/page-2.html": page_2,
        cat("a-light-in-the-attic_1000"): PRODUCT_HTML,
        cat("tipping-the-velvet_999"): product_html("90fa61229261140a", "Tipping the Velvet", velvet_price),
        cat("soumission_998"): product_html("6957f44c3847a760", "Soumission", "£50.10"),
        cat("broken-book_997"): "<html><body>not a product</body></html>",
    }


class ParserTests(unittest.TestCase):
    def test_parse_money_uses_integer_pence(self):
        self.assertEqual(parse_money("£51.77"), (5177, "GBP"))
        self.assertEqual(parse_money("£0.00"), (0, "GBP"))
        self.assertEqual(parse_money("£7.5"), (750, "GBP"))
        with self.assertRaises(ValueError):
            parse_money("free")

    def test_parse_availability(self):
        self.assertEqual(parse_availability("\n In stock (22 available)\n"), (True, 22))
        self.assertEqual(parse_availability("In stock"), (True, 0))
        self.assertEqual(parse_availability("Out of stock"), (False, 0))

    def test_listing_page(self):
        urls, next_url = parse_listing_page(LISTING_HTML, PAGE_1)
        self.assertEqual(urls, [PRODUCT_URL, BASE_URL + "catalogue/tipping-the-velvet_999/index.html"])
        self.assertEqual(next_url, BASE_URL + "catalogue/page-2.html")

    def test_categories(self):
        cats = parse_categories(LISTING_HTML, PAGE_1)
        self.assertEqual([c.name for c in cats], ["Travel", "Poetry"])
        self.assertEqual(cats[1].url, BASE_URL + "catalogue/category/books/poetry_23/index.html")

    def test_product_page(self):
        book = parse_product_page(PRODUCT_HTML, PRODUCT_URL)
        self.assertEqual(book.upc, "a897fe39b1053632")
        self.assertEqual(book.title, "A Light in the Attic")
        self.assertEqual((book.price_excl_tax_pence, book.price_incl_tax_pence, book.tax_pence), (5177, 5177, 0))
        self.assertEqual(book.currency, "GBP")
        self.assertEqual(book.category, "Poetry")
        self.assertEqual(book.category_url, BASE_URL + "catalogue/category/books/poetry_23/index.html")
        self.assertEqual(book.rating, 3)
        self.assertEqual((book.in_stock, book.availability), (True, 22))
        self.assertEqual(book.num_reviews, 0)
        self.assertEqual(book.product_type, "Books")
        self.assertTrue(book.description.startswith("It's hard to imagine"))
        self.assertEqual(book.image_url, BASE_URL + "media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg")
        validate(book)

    def test_non_product_page_raises(self):
        with self.assertRaises(ValueError):
            parse_product_page("<html></html>", PRODUCT_URL)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.book = parse_product_page(PRODUCT_HTML, PRODUCT_URL)

    def test_rejects_inconsistent_records(self):
        for bad in (replace(self.book, upc=""),
                    replace(self.book, tax_pence=100),
                    replace(self.book, rating=6),
                    replace(self.book, in_stock=False),
                    replace(self.book, url="/relative")):
            with self.assertRaises(ValidationError):
                validate(bad)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.book = parse_product_page(PRODUCT_HTML, PRODUCT_URL)

    def test_write_one_row_read_it_back(self):
        run_id = db.start_run(self.conn)
        book_id = db.upsert_book(self.conn, self.book, run_id)
        row = db.get_book(self.conn, self.book.upc)
        self.assertEqual(row["book_id"], book_id)
        self.assertEqual(row["title"], "A Light in the Attic")
        self.assertEqual(row["category"], "Poetry")
        self.assertEqual(row["price_gbp"], 51.77)

    def test_upsert_is_idempotent_and_keeps_history(self):
        run_1 = db.start_run(self.conn)
        first = db.upsert_book(self.conn, self.book, run_1)
        run_2 = db.start_run(self.conn)
        cheaper = replace(self.book, price_excl_tax_pence=4000, price_incl_tax_pence=4000)
        second = db.upsert_book(self.conn, cheaper, run_2)
        self.assertEqual(first, second)
        s = db.summary(self.conn)
        self.assertEqual((s["books"], s["categories"], s["snapshots"]), (1, 1, 2))
        row = self.conn.execute("SELECT * FROM books").fetchone()
        self.assertEqual((row["first_seen_run_id"], row["last_seen_run_id"]), (run_1, run_2))
        self.assertEqual(row["price_incl_tax_pence"], 4000)

    def test_foreign_keys_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO book_snapshots (book_id, run_id, price_incl_tax_pence,"
                              " availability, in_stock, scraped_at) VALUES (999, 999, 1, 1, 1, 'x')")


class PipelineTests(unittest.TestCase):
    def test_full_run_follows_pages_and_skips_bad_books(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        fetcher = FakeFetcher(fake_site())
        result = pipeline.run(conn, fetcher, PAGE_1, workers=2)
        self.assertEqual((result["pages"], result["books"], result["errors"]), (2, 3, 1))
        s = db.summary(conn)
        self.assertEqual((s["books"], s["categories"]), (3, 2))
        run = conn.execute("SELECT * FROM scrape_runs").fetchone()
        self.assertEqual((run["status"], run["books_scraped"], run["errors"]), ("ok", 3, 1))
        # Every book links to an existing category and rating.
        orphans = conn.execute("""SELECT COUNT(*) FROM books b
            LEFT JOIN categories c USING (category_id) LEFT JOIN ratings r USING (rating_id)
            WHERE c.category_id IS NULL OR r.rating_id IS NULL""").fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_rerun_updates_instead_of_duplicating(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        pipeline.run(conn, FakeFetcher(fake_site()), PAGE_1)
        pipeline.run(conn, FakeFetcher(fake_site(velvet_price="£10.00")), PAGE_1)
        s = db.summary(conn)
        self.assertEqual((s["books"], s["snapshots"], s["runs"]), (3, 6, 2))
        prices = [r[0] for r in conn.execute(
            """SELECT s.price_incl_tax_pence FROM book_snapshots s JOIN books b USING (book_id)
               WHERE b.title = 'Tipping the Velvet' ORDER BY s.run_id""")]
        self.assertEqual(prices, [5374, 1000])

    def test_max_pages(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        result = pipeline.run(conn, FakeFetcher(fake_site()), PAGE_1, max_pages=1)
        self.assertEqual((result["pages"], result["books"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
