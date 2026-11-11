"""PUMA's own job search on about.puma.com (Drupal + Elasticsearch): POST https://about.puma.com/dd_job_search

params: corporate_only (default true – skips store/retail jobs), regions (e.g. [EMEA])
"""
from .. import http
from ..models import Posting, html_to_text, iso_date

API = "https://about.puma.com/dd_job_search"


def fetch(src):
    p = src["params"]
    out, frm, total = {}, 0, None
    while True:
        r = http.post(API, json={"q": "", "area": "all", "location": [], "from": frm})
        r.raise_for_status()
        hits = r.json()["hits"]
        total = hits["total"]["value"] if total is None else total
        rows = hits.get("hits", [])
        for h in rows:
            s = h["_source"]
            if p.get("corporate_only", True) and str(s.get("is_retail")) == "1":
                continue
            if p.get("regions") and s.get("region") not in p["regions"]:
                continue
            jid = s.get("entity_id")
            out[jid] = Posting(
                id=f"{src['key']}:{jid}", company=src["name"], title=html_to_text(s.get("title", "")),
                location=", ".join(x for x in [s.get("city"), s.get("country")] if x),
                url="https://about.puma.com" + s["url"], posted_at=iso_date(int(s["created"])) if s.get("created") else "",
                description_text=html_to_text(s.get("body", "")), source_adapter="puma", source_key=src["key"],
                extra={"category": s.get("category", ""), "jobFamily": s.get("job_family", "")})
        frm += len(rows)
        if not rows or frm >= total or frm > 3000:
            break
    return list(out.values())
