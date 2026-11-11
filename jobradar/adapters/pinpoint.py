"""Pinpoint careers site JSON: https://{company}.pinpointhq.com/postings.json"""
from .. import http
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    p = src["params"]
    base = (p.get("base_url") or f"https://{p['company']}.pinpointhq.com").rstrip("/")
    d = http.get_json(base + "/postings.json")
    out = []
    for j in d.get("data", []):
        loc = j.get("location") or {}
        loc_s = ", ".join(x for x in [loc.get("city"), loc.get("province"), loc.get("name")] if x) if isinstance(loc, dict) else str(loc)
        sal = ""
        if j.get("compensation_visible") and (j.get("compensation_minimum") or j.get("compensation")):
            if j.get("compensation_minimum"):
                sal = f"{j.get('compensation_currency','')} {j['compensation_minimum']:,}–{j.get('compensation_maximum') or j['compensation_minimum']:,} / {j.get('compensation_frequency','')}"
            else:
                sal = str(j.get("compensation"))
        url = j.get("url") or f"{base}/en/postings/{j['id']}"
        out.append(Posting(
            id=f"{src['key']}:{j['id']}", company=src["name"], title=j["title"], location=loc_s, url=url,
            posted_at=iso_date(j.get("created_at") or j.get("published_at")),
            deadline=iso_date(j.get("deadline_at")),
            description_text=html_to_text(" ".join(j.get(k) or "" for k in ("description", "key_responsibilities", "skills_knowledge_expertise", "benefits"))),
            salary_text=sal, source_adapter="pinpoint", source_key=src["key"],
            extra={"employment_type": j.get("employment_type_text") or j.get("employment_type") or "",
                   "workplace": j.get("workplace_type_text") or ""}))
    return out
