"""Deutsche Bank careers (careers.db.com) – beesite search API; postings live on db.recsolu.com."""
import json

from .. import http
from ..models import Posting, html_to_text, iso_date

FIELDS = ["PositionID", "PositionTitle", "PositionURI", "PositionLocation.CountryName", "PositionLocation.CityName",
          "PublicationStartDate", "ApplicationDeadline", "CareerLevel.Name"]


def fetch(src):
    p = src["params"]
    out = {}
    for endpoint in p.get("endpoints", ["graduatesearch", "search"]):
        first = 1
        while True:
            data = {"LanguageCode": "en", "SearchParameters": {"FirstItem": first, "CountItem": 100,
                    "MatchedObjectDescriptor": FIELDS, "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}]},
                    "SearchCriteria": p.get("criteria", [])}
            d = http.get_json(f"https://api-deutschebank.beesite.de/{endpoint}/", params={"data": json.dumps(data)})
            res = d.get("SearchResult", {})
            items = res.get("SearchResultItems", [])
            for it in items:
                m = it["MatchedObjectDescriptor"]
                locs = [", ".join(x for x in [l.get("CityName"), l.get("CountryName")] if x) for l in m.get("PositionLocation", [])]
                pid = m.get("PositionID") or it["MatchedObjectId"]
                out[pid] = Posting(
                    id=f"{src['key']}:{pid}", company=src["name"], title=m.get("PositionTitle", ""),
                    location=" | ".join(locs), url=m.get("PositionURI") or f"https://careers.db.com/professionals/search-roles/#/professional/job/{pid}",
                    posted_at=iso_date(m.get("PublicationStartDate")), deadline=iso_date(m.get("ApplicationDeadline")),
                    source_adapter="beesite", source_key=src["key"],
                    extra={"career_level": ", ".join(c.get("Name", "") for c in m.get("CareerLevel", []))})
            first += len(items)
            if not items or first > res.get("SearchResultCountAll", 0) or first > p.get("max_results", 4000):
                break
    return list(out.values())


def detail(src, post):
    r = http.get(post.url)
    if r.status_code == 200:
        post.description_text = html_to_text(r.text)[:20000]
