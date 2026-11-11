"""Cegid / DigitalRecruiters career sites: POST api.digitalrecruiters.com/public/v1/careers-site/job-ads"""
from .. import http
from ..models import Posting, extract_jsonld_jobposting, html_to_text, jsonld_location

API = "https://api.digitalrecruiters.com/public/v1/careers-site/job-ads"


def fetch(src):
    p = src["params"]
    domain = p["domain"]
    out, page = {}, 1
    while True:
        r = http.post(API, params={"domainName": domain, "limit": 100, "page": page, "locale": p.get("locale", "en_GB")},
                      json={"filters": p.get("filters", {}), "coordinates": {"lat": 0, "lng": 0}})
        r.raise_for_status()
        d = r.json()
        items = d.get("items", [])
        for j in items:
            if j.get("is_aggregated"):
                continue
            out[j["id"]] = Posting(
                id=f"{src['key']}:{j['job_ad_id']}", company=src["name"], title=j["title"], location=j.get("location", ""),
                url=f"https://{domain}/{p.get('lang', 'en')}/annonce/{j['url']}", source_adapter="digitalrecruiters",
                source_key=src["key"], extra={"contract": j.get("contract", ""), "job": j.get("job", "")})
        page += 1
        if not items or len(out) >= d.get("count", 0) or page > 60:
            break
    return list(out.values())


def detail(src, post):
    r = http.get(post.url)
    if r.status_code == 200:
        jp = extract_jsonld_jobposting(r.text)
        if jp:
            post.description_text = html_to_text(jp.get("description", ""))
            post.location = jsonld_location(jp) or post.location
        else:
            post.description_text = html_to_text(r.text)[:20000]
