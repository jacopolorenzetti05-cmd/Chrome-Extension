"""Records that flow from the parser to the database, mirroring db/schema.sql."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Category:
    slug: str
    name: str

    def to_row(self) -> dict:
        return {"slug": self.slug, "name": self.name}


@dataclass
class Book:
    upc: str
    title: str
    category: Category
    price: Decimal
    stock: int
    rating: int
    url: str
    description: str | None = None
    image_url: str | None = None

    def validate(self) -> list[str]:
        """Return a list of problems; empty means the record is safe to store."""
        problems = []
        if not self.upc:
            problems.append("missing upc")
        if not self.title:
            problems.append("missing title")
        if not 1 <= self.rating <= 5:
            problems.append(f"rating out of range: {self.rating}")
        if self.stock < 0:
            problems.append(f"negative stock: {self.stock}")
        if self.price < 0:
            problems.append(f"negative price: {self.price}")
        return problems

    def to_row(self) -> dict:
        """Row for the `books` table (price as a string so no float rounding)."""
        return {
            "upc": self.upc,
            "title": self.title,
            "category_slug": self.category.slug,
            "price": str(self.price),
            "stock": self.stock,
            "rating": self.rating,
            "description": self.description,
            "image_url": self.image_url,
            "url": self.url,
        }

    def snapshot_row(self, run_id: int) -> dict:
        return {"run_id": run_id, "upc": self.upc, "price": str(self.price), "stock": self.stock}


@dataclass
class ScrapeRun:
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    status: str = "running"
    pages_scraped: int = 0
    errors: int = 0
    books_scraped: int = 0  # for logging only; the database counts snapshots instead

    def to_row(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "pages_scraped": self.pages_scraped,
            "errors": self.errors,
        }
