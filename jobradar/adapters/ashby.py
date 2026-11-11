"""Ashby public job board API: api.ashbyhq.com/posting-api/job-board/{org}"""
from .. import http
from ..models import Posting, iso_date


def fetch(src):
    org = src["params"]["org"]
    d = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{org}", params={"includeCompensation": "true"})
    out = []
    for j in d.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", [])]
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append(Posting(
            id=f"{src['key']}:{j['id']}", company=src["name"], title=j["title"],
            location=" | ".join(l for l in locs if l) + (" (remote)" if j.get("isRemote") else ""),
            url=j["jobUrl"], apply_url=j.get("applyUrl") or j["jobUrl"], posted_at=iso_date(j.get("publishedAt")),
            description_text=j.get("descriptionPlain") or "", salary_text=comp,
            source_adapter="ashby", source_key=src["key"]))
    return out
