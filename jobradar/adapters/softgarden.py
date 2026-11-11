"""softgarden career site: schema.org DataFeed at {career site}/jobs.feed.json"""
from .. import http
from ..models import Posting, html_to_text, iso_date, jsonld_location, jsonld_salary


def fetch(src):
    base = src["params"]["base_url"].rstrip("/")
    d = http.get_json(base + "/jobs.feed.json")
    out = []
    for el in d.get("dataFeedElement", []):
        j = el.get("item", el)
        url = j.get("url") or ""
        jid = j.get("identifier")
        if isinstance(jid, dict):
            jid = jid.get("value")
        jid = jid or url.rstrip("/").split("/")[-2]
        out.append(Posting(
            id=f"{src['key']}:{jid}", company=src["name"], title=j.get("title", ""), location=jsonld_location(j),
            url=url, posted_at=iso_date(j.get("datePosted")), deadline=iso_date(j.get("validThrough")),
            description_text=html_to_text(j.get("description", "")), salary_text=jsonld_salary(j),
            source_adapter="softgarden", source_key=src["key"],
            extra={"employmentType": j.get("employmentType", "")}))
    return out
