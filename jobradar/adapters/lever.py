"""Lever postings API: api.lever.co/v0/postings/{company}?mode=json (EU: api.eu.lever.co)"""
from .. import http
from ..models import Posting, iso_date


def fetch(src):
    company = src["params"]["company"]
    hosts = [src["params"]["host"]] if src["params"].get("host") else ["api.lever.co", "api.eu.lever.co"]
    for h in hosts:
        r = http.get(f"https://{h}/v0/postings/{company}", params={"mode": "json"})
        if r.status_code == 200 and r.text.strip().startswith("["):
            break
    else:
        raise RuntimeError(f"lever company '{company}' not found")
    out = []
    for j in r.json():
        cats = j.get("categories") or {}
        loc = " | ".join(dict.fromkeys([cats.get("location") or ""] + (cats.get("allLocations") or [])))
        sal = ""
        sr = j.get("salaryRange") or {}
        if sr.get("min"):
            sal = f"{sr.get('currency','')} {sr['min']:,}–{sr.get('max', sr['min']):,} / {sr.get('interval','')}"
        desc = (j.get("descriptionPlain") or "") + " " + " ".join(
            (l.get("text", "") + " " + __import__("re").sub("<[^>]+>", " ", l.get("content", ""))) for l in j.get("lists", []))
        out.append(Posting(
            id=f"{src['key']}:{j['id']}", company=src["name"], title=j["text"], location=loc.strip(" |"),
            url=j["hostedUrl"], apply_url=j.get("applyUrl") or j["hostedUrl"],
            posted_at=iso_date(j.get("createdAt")), description_text=desc + " " + (j.get("additionalPlain") or ""),
            salary_text=sal, source_adapter="lever", source_key=src["key"]))
    return out
