"""SmartRecruiters public postings API: api.smartrecruiters.com/v1/companies/{company}/postings"""
from .. import http
from ..models import Posting, html_to_text, iso_date

API = "https://api.smartrecruiters.com/v1/companies/{c}/postings"


def fetch(src):
    p = src["params"]
    company = p["company"]
    out, offset = [], 0
    filt = [f.lower() for f in p.get("company_name_contains", [])]
    while True:
        q = {"limit": 100, "offset": offset}
        if p.get("country"):
            q["country"] = p["country"]
        data = http.get_json(API.format(c=company), params=q)
        content = data.get("content", [])
        for j in content:
            if filt and not any(f in (j.get("company", {}).get("name", "") + " " + j.get("name", "")).lower() for f in filt):
                continue
            loc = j.get("location") or {}
            loc_s = ", ".join(x for x in [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()] if x)
            if loc.get("remote"):
                loc_s += " (remote)"
            out.append(Posting(
                id=f"{src['key']}:{j['id']}", company=src["name"], title=j["name"], location=loc_s,
                url=f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
                apply_url=f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
                posted_at=iso_date(j.get("releasedDate")), source_adapter="smartrecruiters",
                source_key=src["key"], extra={"department": (j.get("department") or {}).get("label", ""),
                                               "function": (j.get("function") or {}).get("label", ""),
                                               "experience": (j.get("experienceLevel") or {}).get("label", ""),
                                               "employer": (j.get("company") or {}).get("name", "")}))
        offset += len(content)
        if not content or offset >= data.get("totalFound", 0) or offset > 5000:
            break
    return out


def detail(src, p):
    nid = p.id.split(":", 1)[1]
    d = http.get_json(API.format(c=src["params"]["company"]) + f"/{nid}")
    secs = (d.get("jobAd") or {}).get("sections") or {}
    p.description_text = " ".join(html_to_text((secs.get(k) or {}).get("text", ""))
                                  for k in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))
    if d.get("postingUrl"):
        p.url = d["postingUrl"]
    if d.get("applyUrl"):
        p.apply_url = d["applyUrl"]
