"""Workable public API: POST apply.workable.com/api/v3/accounts/{account}/jobs"""
from .. import http
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    acc = src["params"]["account"]
    out, token = [], None
    for _ in range(50):
        body = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}
        if token:
            body["token"] = token
        r = http.post(f"https://apply.workable.com/api/v3/accounts/{acc}/jobs", json=body)
        r.raise_for_status()
        d = r.json()
        for j in d.get("results", []):
            loc = j.get("location") or {}
            locs = [", ".join(x for x in [l.get("city"), l.get("country")] if x) for l in (j.get("locations") or [loc])]
            out.append(Posting(
                id=f"{src['key']}:{j['shortcode']}", company=src["name"], title=j["title"],
                location=" | ".join(l for l in locs if l) + (" (remote)" if j.get("remote") else ""),
                url=f"https://apply.workable.com/{acc}/j/{j['shortcode']}/",
                posted_at=iso_date(j.get("published")), source_adapter="workable", source_key=src["key"]))
        token = d.get("nextPage")
        if not token:
            break
    return out


def detail(src, p):
    acc = src["params"]["account"]
    sc = p.id.split(":", 1)[1]
    d = http.get_json(f"https://apply.workable.com/api/v2/accounts/{acc}/jobs/{sc}")
    p.description_text = html_to_text(" ".join(d.get(k, "") or "" for k in ("description", "requirements", "benefits")))
