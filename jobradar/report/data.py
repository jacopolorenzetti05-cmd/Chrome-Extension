"""Shared view-model for dashboard, digest and export."""
from __future__ import annotations

import datetime as dt

from .. import config
from ..store import Store

STATUSES = ["Not applied", "Applied", "Interview", "Offer", "Rejected", "Not interested"]


def my_status() -> dict:
    d = config.load_yaml(config.STATUS_FILE, {}) or {}
    if not isinstance(d, dict):
        return {}
    apps = d.get("applications", d) or {}
    return {str(k): (v if isinstance(v, dict) else {"status": str(v)}) for k, v in apps.items()}


def display_status(rec: dict, today: dt.date) -> str:
    if rec["status"] == "removed":
        return "Removed"
    if rec.get("deadline"):
        try:
            dl = dt.date.fromisoformat(rec["deadline"][:10])
            if dl < today:
                return "Deadline passed"
            if (dl - today).days <= 7:
                return "Closing soon"
        except ValueError:
            pass
    if rec.get("first_seen") == today.isoformat():
        return "New"
    return "Active"


def postings(store: Store, include_removed: bool = True) -> list[dict]:
    today = dt.date.today()
    mine = my_status()
    rows = store.all("relevance IN ('keep','maybe')" + ("" if include_removed else " AND status='active'"))
    out = []
    for r in rows:
        r = dict(r)
        r["display_status"] = display_status(r, today)
        ms = mine.get(r["id"], {})
        r["my_status"] = ms.get("status", "Not applied")
        r["my_note"] = ms.get("note", "")
        r.pop("description", None)
        r.pop("extra", None)
        out.append(r)
    out.sort(key=lambda r: (-(r.get("score") or 0), r["company"]))
    # the same official posting can be reachable from two sources (e.g. Red Bull + RB Salzburg): show it once
    seen, uniq = set(), []
    for r in out:
        k = (r.get("url") or "").split("?")[0].rstrip("/").lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def source_health(store: Store) -> list[dict]:
    srcs = {s["key"]: s for s in config.load_sources()}
    latest = {r["source_key"]: r for r in store.latest_source_runs()}
    rows = []
    for key, s in srcs.items():
        r = latest.get(key, {})
        rows.append({"key": key, "name": s["name"], "sector": s["sector"], "segment": s.get("segment", ""),
                     "adapter": s["adapter"], "careers_url": s.get("careers_url", ""), "notes": s.get("notes", ""),
                     "fetched": r.get("fetched"), "relevant": r.get("relevant"), "maybe": r.get("maybe"),
                     "health": r.get("health", "not run yet" if s.get("enabled", True) else "disabled"),
                     "error": r.get("error", ""), "last_run": r.get("run_at", ""),
                     "last_success": store.last_success(key)})
    rows.sort(key=lambda x: (x["health"].startswith("OK"), x["sector"], x["name"].lower()))
    return rows
