"""Library app: browse the scraped books in Supabase.

    python app/server.py            # then open http://localhost:8000

The tables are locked by RLS, so the browser never talks to Supabase directly: this small
server holds the service_role key and exposes a read-only JSON API to the page.

    GET /api/categories                   all categories with their book counts
    GET /api/books?q=&category=&min_price=&max_price=&min_rating=&sort=&page=
    GET /api/books/<upc>                  one book plus its price/stock per scrape run
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.supabase_client import SupabaseClient, SupabaseError  # noqa: E402

STATIC = Path(__file__).parent / "static"
PAGE_SIZE = 24
SORTS = {
    "title": "title.asc",
    "price_asc": "price.asc,title.asc",
    "price_desc": "price.desc,title.asc",
    "rating": "rating.desc,title.asc",
    "stock": "stock.desc,title.asc",
}
LIST_COLUMNS = "upc,title,price,stock,rating,image_url,category_slug,category_name"
SLUG_RE = re.compile(r"^[a-z0-9-]+_\d+$")
UPC_RE = re.compile(r"^[A-Za-z0-9]+$")


class BadRequest(ValueError):
    pass


def book_filters(params: dict[str, str]) -> dict[str, str]:
    """Turn the page's query string into PostgREST params for books_with_category.

    Everything is validated or whitelisted here, so user input never shapes the query
    beyond a literal value.
    """
    out: dict[str, str] = {"order": SORTS.get(params.get("sort", ""), SORTS["title"])}

    q = params.get("q", "").strip()
    if q:
        # * and % are wildcards to PostgREST/Postgres; strip them so the search is literal.
        q = re.sub(r"[*%]", " ", q)[:100].strip()
        if q:
            out["title"] = f"ilike.*{q}*"

    category = params.get("category", "")
    if category:
        if not SLUG_RE.match(category):
            raise BadRequest("bad category")
        out["category_slug"] = f"eq.{category}"

    prices = []
    if params.get("min_price"):
        prices.append(f"price.gte.{_number(params['min_price'])}")
    if params.get("max_price"):
        prices.append(f"price.lte.{_number(params['max_price'])}")
    if len(prices) == 2:
        out["and"] = f"({','.join(prices)})"
    elif prices:
        _, op, value = prices[0].split(".", 2)
        out["price"] = f"{op}.{value}"

    if params.get("min_rating"):
        rating = int(_number(params["min_rating"]))
        if not 1 <= rating <= 5:
            raise BadRequest("min_rating must be 1-5")
        out["rating"] = f"gte.{rating}"

    page = int(_number(params.get("page") or "1"))
    if page < 1:
        raise BadRequest("page must be >= 1")
    out["limit"] = str(PAGE_SIZE)
    out["offset"] = str((page - 1) * PAGE_SIZE)
    return out


def _number(value: str) -> float:
    try:
        n = float(value)
    except ValueError:
        raise BadRequest(f"not a number: {value!r}") from None
    if n != n or n < 0 or n > 1e6:
        raise BadRequest(f"out of range: {value!r}")
    return n


class Library:
    """Read-only queries the page needs."""

    def __init__(self, client: SupabaseClient):
        self.client = client

    def categories(self) -> list[dict]:
        rows = self.client.select("categories", "slug,name,books(count)", order="name.asc")
        return [{"slug": r["slug"], "name": r["name"], "count": r["books"][0]["count"]} for r in rows]

    def books(self, params: dict[str, str]) -> dict:
        query = {"select": LIST_COLUMNS, **book_filters(params)}
        resp = self.client.session.get(
            f"{self.client.base}/books_with_category", params=query,
            headers={"Prefer": "count=exact"}, timeout=self.client.timeout,
        )
        rows = self.client._check(resp)
        total = int(resp.headers.get("Content-Range", "*/0").rsplit("/", 1)[1])
        return {"books": rows, "total": total, "page_size": PAGE_SIZE}

    def book(self, upc: str) -> dict | None:
        if not UPC_RE.match(upc):
            raise BadRequest("bad upc")
        rows = self.client.select("books_with_category", upc=f"eq.{upc}")
        if not rows:
            return None
        history = self.client.select(
            "book_snapshots", "run_id,price,stock,scrape_runs(finished_at)",
            upc=f"eq.{upc}", order="run_id.asc",
        )
        book = rows[0]
        book["history"] = [
            {"run_id": h["run_id"], "price": h["price"], "stock": h["stock"],
             "date": (h["scrape_runs"] or {}).get("finished_at")}
            for h in history
        ]
        return book


def make_handler(library: Library):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/categories":
                    return self._json(library.categories())
                if url.path == "/api/books":
                    return self._json(library.books(params))
                if url.path.startswith("/api/books/"):
                    book = library.book(url.path.rsplit("/", 1)[1])
                    return self._json(book) if book else self._json({"error": "not found"}, 404)
                if url.path in ("/", "/index.html"):
                    return self._file(STATIC / "index.html", "text/html; charset=utf-8")
                self._json({"error": "not found"}, 404)
            except BadRequest as exc:
                self._json({"error": str(exc)}, 400)
            except SupabaseError as exc:
                self.log_error("supabase: %s", exc)
                self._json({"error": "database error"}, 502)

        def _json(self, data, status=200):
            self._send(json.dumps(data).encode(), "application/json", status)

        def _file(self, path: Path, ctype: str):
            self._send(path.read_bytes(), ctype)

        def _send(self, body: bytes, ctype: str, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Serve the library app.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    try:
        client = SupabaseClient.from_env()
    except SupabaseError as exc:
        print(exc)
        return 1
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Library(client)))
    print(f"Library open at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
