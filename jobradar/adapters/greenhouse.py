"""Greenhouse job board API: boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""
from .. import http
from ..models import Posting, html_to_text, iso_date

HOSTS = ["boards-api.greenhouse.io", "boards-api.eu.greenhouse.io"]


def fetch(src):
    token = src["params"]["token"]
    host = src["params"].get("host")
    last = None
    for h in ([host] if host else HOSTS):
        r = http.get(f"https://{h}/v1/boards/{token}/jobs", params={"content": "true"})
        if r.status_code == 200:
            break
        last = r
    else:
        raise RuntimeError(f"greenhouse board '{token}' not found (HTTP {last.status_code})")
    out = []
    for j in r.json().get("jobs", []):
        locs = [j.get("location", {}).get("name", "")] + [o.get("name", "") for o in j.get("offices", [])]
        loc = " | ".join(dict.fromkeys(l for l in locs if l))
        out.append(Posting(
            id=f"{src['key']}:{j['id']}", company=src["name"], title=j["title"], location=loc,
            url=j.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{j['id']}",
            posted_at=iso_date(j.get("first_published") or j.get("updated_at")),
            description_text=html_to_text(__import__("html").unescape(j.get("content", ""))),
            source_adapter="greenhouse", source_key=src["key"]))
    return out
