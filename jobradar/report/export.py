"""Export the full history to jobs.xlsx and jobs.csv."""
from __future__ import annotations

import csv

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from .. import config
from ..store import Store
from . import data

FIELDS = ["id", "score", "company", "sector", "segment", "title", "location", "country", "pay", "languages", "type",
          "timing", "deadline", "display_status", "status", "relevance", "reason", "why", "my_status", "my_note",
          "url", "apply_url", "verified", "verify_note", "first_seen", "last_seen", "removed_at", "posted_at",
          "source_key", "source_adapter"]


def export(out_dir=None) -> tuple[str, str]:
    out_dir = out_dir or config.ROOT
    store = Store()
    rows = data.postings(store, include_removed=True)
    health = data.source_health(store)
    store.close()
    csv_path = out_dir / "jobs.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    wb = Workbook()
    for title, sector in (("Sports", "sports"), ("Wealth Management", "wealth"), ("General", "general")):
        ws = wb.create_sheet(title)
        ws.append(FIELDS)
        for r in rows:
            if r["sector"] == sector:
                ws.append([r.get(k) for k in FIELDS])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, k in enumerate(FIELDS, 1):
            ws.column_dimensions[get_column_letter(i)].width = {"title": 45, "why": 50, "url": 40, "reason": 35}.get(k, 14)
    hs = wb.create_sheet("Source health")
    hk = ["name", "sector", "adapter", "health", "fetched", "relevant", "maybe", "last_success", "error", "notes", "careers_url"]
    hs.append(hk)
    for h in health:
        hs.append([h.get(k) for k in hk])
    del wb["Sheet"]
    xlsx_path = out_dir / "jobs.xlsx"
    wb.save(xlsx_path)
    return str(xlsx_path), str(csv_path)
