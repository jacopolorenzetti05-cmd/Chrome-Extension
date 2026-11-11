"""Phenom People career sites: POST {site}/widgets  (ddoKey=refineSearch)

params: base_url (e.g. https://careers.wbd.com), lang (en_global), country (global), path (global/en),
        page_id (search-results page id), optional countries (list of country names to restrict to)
"""
import re

from .. import http
from ..models import Posting, html_to_text, iso_date


def _slug(t):
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-")


def fetch(src):
    p = src["params"]
    base = p["base_url"].rstrip("/")
    out, frm, size = {}, 0, 100
    while True:
        body = {"lang": p.get("lang", "en_global"), "deviceType": "desktop", "country": p.get("country", "global"),
                "pageName": "search-results", "ddoKey": "refineSearch", "sortBy": "", "subsearch": "", "from": frm,
                "jobs": True, "counts": True, "all_fields": ["country"], "size": size, "clearAll": False,
                "jdsource": "facets", "isSliderEnable": False, "pageId": p.get("page_id", "page18-ds"),
                "siteType": "external", "keywords": "", "global": True,
                "selected_fields": {"country": p["countries"]} if p.get("countries") else {}}
        r = http.post(base + "/widgets", json=body)
        r.raise_for_status()
        rs = r.json()["refineSearch"]
        jobs = rs.get("data", {}).get("jobs", [])
        for j in jobs:
            jid = j.get("jobId") or j.get("reqId")
            locs = j.get("multi_location") or [j.get("location") or j.get("cityStateCountry", "")]
            out[jid] = Posting(
                id=f"{src['key']}:{jid}", company=src["name"], title=j.get("title", ""), location=" | ".join(locs),
                url=f"{base}/{p.get('path', 'global/en')}/job/{jid}/{_slug(j.get('title', ''))}",
                apply_url=j.get("applyUrl") or "", posted_at=iso_date(j.get("postedDate")),
                description_text=html_to_text(j.get("descriptionTeaser", "")),
                source_adapter="phenom", source_key=src["key"],
                extra={"type": j.get("type", ""), "category": j.get("category", "")})
        frm += size
        if not jobs or frm >= rs.get("totalHits", 0) or frm >= 5000:
            break
    return list(out.values())


def detail(src, post):
    r = http.get(post.url)
    if r.status_code == 200:
        m = re.search(r'"description"\s*:\s*"(.*?)(?<!\\)"', r.text)
        if m:
            import html as _h, json as _j
            try:
                raw = _j.loads('"' + m.group(1) + '"')
            except Exception:
                raw = m.group(1)
            post.description_text = html_to_text(_h.unescape(raw))
