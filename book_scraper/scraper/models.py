"""Records that flow from the parser to the database, mirroring db/schema.sql."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Category:
    name: str
    slug: str
    url: str


@dataclass
class Book:
    upc: str
    title: str
    category: Category
    price_excl_tax: Decimal
    price_incl_tax: Decimal
    tax: Decimal
    stock: int
    rating: int
    num_reviews: int
    url: str
    product_type: str | None = None
    description: str | None = None
    image_url: str | None = None
    currency: str = "GBP"

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
        if self.num_reviews < 0:
            problems.append(f"negative num_reviews: {self.num_reviews}")
        for name in ("price_excl_tax", "price_incl_tax", "tax"):
            if getattr(self, name) < 0:
                problems.append(f"negative {name}")
        if self.price_excl_tax + self.tax != self.price_incl_tax:
            problems.append(
                f"price mismatch: {self.price_excl_tax} + {self.tax} != {self.price_incl_tax}"
            )
        return problems

    def to_row(self, category_id: int) -> dict:
        """Row for the `books` table (money as strings so no float rounding)."""
        return {
            "upc": self.upc,
            "title": self.title,
            "category_id": category_id,
            "price_excl_tax": str(self.price_excl_tax),
            "price_incl_tax": str(self.price_incl_tax),
            "tax": str(self.tax),
            "currency": self.currency,
            "stock": self.stock,
            "rating": self.rating,
            "num_reviews": self.num_reviews,
            "product_type": self.product_type,
            "description": self.description,
            "image_url": self.image_url,
            "url": self.url,
        }


@dataclass
class ScrapeRun:
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    status: str = "running"
    pages_scraped: int = 0
    books_scraped: int = 0
    errors: int = 0

    def to_row(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "pages_scraped": self.pages_scraped,
            "books_scraped": self.books_scraped,
            "errors": self.errors,
        }
