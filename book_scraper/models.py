"""Internal data contract between the parser and the database."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Category:
    name: str
    url: str | None = None


@dataclass
class BookRecord:
    upc: str
    title: str
    url: str
    price_excl_tax_pence: int
    price_incl_tax_pence: int
    tax_pence: int = 0
    currency: str = "GBP"
    category: str | None = None
    category_url: str | None = None
    rating: int | None = None          # 1..5
    availability: int = 0              # number of copies in stock
    in_stock: bool = False
    num_reviews: int = 0
    product_type: str | None = None
    description: str | None = None
    image_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ValidationError(ValueError):
    pass


def validate(book: BookRecord) -> BookRecord:
    """Check a record makes sense before it reaches the database."""
    problems = []
    if not book.upc:
        problems.append("missing upc")
    if not book.title:
        problems.append("missing title")
    if not book.url.startswith("http"):
        problems.append(f"url not absolute: {book.url!r}")
    if book.price_incl_tax_pence < 0 or book.price_excl_tax_pence < 0:
        problems.append("negative price")
    if book.price_incl_tax_pence - book.price_excl_tax_pence != book.tax_pence:
        problems.append("price_incl_tax != price_excl_tax + tax")
    if book.rating is not None and not 1 <= book.rating <= 5:
        problems.append(f"rating out of range: {book.rating}")
    if book.availability < 0 or book.num_reviews < 0:
        problems.append("negative count")
    if book.availability > 0 and not book.in_stock:
        problems.append("copies available but marked out of stock")
    if problems:
        raise ValidationError(f"{book.upc or book.url}: " + "; ".join(problems))
    return book
