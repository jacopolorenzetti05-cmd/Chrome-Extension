"""Accenture's own job search (accenture.com/careers/jobsearch): POST https://www.accenture.com/api/accenture/elastic/findjobs

params: markets – list of [country name as the local site spells it, country site, language], e.g.
        ["Italia", "it-it", "it"], ["Deutschland", "de-de", "de"], ["United Kingdom", "gb-en", "en"].
Every job of each market is read (no keyword), so "missing" stays meaningful from run to run.
"""
from .. import http
from ..models import Posting, html_to_text, iso_date

API = "https://www.accenture.com/api/accenture/elastic/findjobs"
PAGE = 100


def _page(country, site, lang, start):
    form = {"startIndex": str(start), "maxResultSize": str(PAGE), "jobKeyword": "", "jobCountry": country,
            "jobLanguage": lang, "countrySite": site, "sortBy": "1", "searchType": "vectorSearch",
            "enableQueryBoost": "true", "minScore": "0.6", "totalHits": "true"}
    r = http.post(API, files={k: (None, v) for k, v in form.items()}, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def fetch(src):
    out = {}
    for country, site, lang in src["params"]["markets"]:
        start, total = 0, None
        while True:
            d = _page(country, site, lang, start)
            if total is None:
                total = (d.get("totalHits") or {}).get("total", 0)
            rows = d.get("data") or []
            for j in rows:
                rid = j.get("requisitionId") or j.get("guid")
                if not rid or rid in out or not j.get("jobDetailUrl"):
                    continue
                cities = j.get("location") or []
                loc = " | ".join(f"{c}, {j.get('country') or country}" for c in cities) or (j.get("country") or country)
                out[rid] = Posting(
                    id=f"{src['key']}:{rid}", company=src["name"], title=j.get("title", ""), location=loc,
                    url=j["jobDetailUrl"].replace("{0}", site), source_adapter="accenture", source_key=src["key"],
                    description_text=html_to_text((j.get("jobDescription") or "") + " " + (j.get("qualification") or "")),
                    posted_at=iso_date(j.get("updateDate")),
                    extra={"level": j.get("jobTypeDescription", ""), "career": j.get("careerLevel", "")})
            start += PAGE
            if not rows or start >= total or start >= 2000:
                break
    return list(out.values())
