"""Workday candidate experience JSON API: POST https://{host}/wday/cxs/{tenant}/{site}/jobs

params: host, tenant, site, optional search_terms (list) – used for very large employers so that
only relevant searches are paged (the same terms are used every run, so "missing" stays meaningful).
"""
import re

from .. import http
from ..models import Posting, html_to_text, iso_date

PAGE = 20


def _base(p):
    return f"https://{p['host']}/wday/cxs/{p['tenant']}/{p['site']}"


def _jid(path: str) -> str:
    m = re.search(r"_([A-Za-z]{0,6}[-_]?\d[\w-]*)$", path)
    return m.group(1) if m else path


def _walk(facets):
    for f in facets or []:
        yield f
        for v in f.get("values") or []:
            if v.get("facetParameter"):
                yield from _walk([v])


def resolve_facets(p) -> dict:
    """Turn {facetParameter: [descriptor, ...]} into Workday ids (descriptors are matched case-insensitively)."""
    want = p.get("facet_filter")
    if not want:
        return p.get("facets", {})
    r = http.post(_base(p) + "/jobs", json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                  headers={"Accept": "application/json"})
    r.raise_for_status()
    out = {}
    for f in _walk(r.json().get("facets")):
        param = f.get("facetParameter")
        if param in want:
            names = {n.lower() for n in want[param]}
            ids = [v["id"] for v in f.get("values", []) if v.get("id") and (v.get("descriptor") or "").lower() in names]
            if ids:
                out[param] = ids
    if not out:
        raise RuntimeError(f"workday facet filter matched nothing: {want}")
    return out


def fetch(src):
    p = src["params"]
    terms = p.get("search_terms") or [""]
    facets = resolve_facets(p)
    seen = {}
    for term in terms:
        offset, total = 0, None
        while True:
            body = {"appliedFacets": facets, "limit": PAGE, "offset": offset, "searchText": term}
            r = http.post(_base(p) + "/jobs", json=body, headers={"Accept": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"workday HTTP {r.status_code} for {p['host']}/{p['site']}")
            d = r.json()
            if total is None:
                total = d.get("total", 0)
            posts = d.get("jobPostings", [])
            for j in posts:
                path = j.get("externalPath")
                if not path:
                    continue
                jid = _jid(path)
                if jid in seen:
                    continue
                seen[jid] = Posting(
                    id=f"{src['key']}:{jid}", company=src["name"], title=j.get("title", ""),
                    location=j.get("locationsText", ""),
                    url=f"https://{p['host']}/en-US/{p['site']}{path}",
                    source_adapter="workday", source_key=src["key"], extra={"path": path})
            offset += PAGE
            if not posts or offset >= total or offset >= p.get("max_results", 2000):
                break
    return list(seen.values())


def detail(src, post):
    p = src["params"]
    d = http.get_json(_base(p) + post.extra["path"], headers={"Accept": "application/json"})
    info = d.get("jobPostingInfo", {})
    post.description_text = html_to_text(info.get("jobDescription", ""))
    locs = [info.get("location", "")] + list(info.get("additionalLocations") or [])
    country = (info.get("country") or {}).get("descriptor", "")
    post.location = " | ".join(l for l in dict.fromkeys(locs) if l) + (f", {country}" if country else "")
    post.posted_at = iso_date(info.get("startDate")) or post.posted_at
    if info.get("endDate"):
        post.deadline = iso_date(info["endDate"])
    if info.get("externalUrl"):
        post.url = info["externalUrl"]
    post.extra["timeType"] = info.get("timeType", "")
