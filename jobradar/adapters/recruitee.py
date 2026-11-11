"""Recruitee careers API: {company}.recruitee.com/api/offers/ (or custom domain /api/offers/)"""
from .. import http
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    p = src["params"]
    base = p.get("base_url") or f"https://{p['company']}.recruitee.com"
    d = http.get_json(base.rstrip("/") + "/api/offers/")
    out = []
    for j in d.get("offers", []):
        locs = [", ".join(x for x in [l.get("city"), l.get("country")] if x) for l in j.get("locations", [])] or [j.get("location", "")]
        sal = ""
        s = j.get("salary") or {}
        if s.get("min"):
            sal = f"{s.get('currency','')} {s['min']}–{s.get('max','')} / {s.get('period','')}"
        out.append(Posting(
            id=f"{src['key']}:{j['id']}", company=src["name"], title=j["title"], location=" | ".join(locs),
            url=j.get("careers_url") or j.get("url"), apply_url=j.get("careers_apply_url") or j.get("careers_url"),
            posted_at=iso_date(j.get("published_at") or j.get("created_at")),
            description_text=html_to_text((j.get("description") or "") + " " + (j.get("requirements") or "")),
            salary_text=sal, source_adapter="recruitee", source_key=src["key"]))
    return out
