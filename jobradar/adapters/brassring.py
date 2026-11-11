"""IBM/Infinite BrassRing (Talent Gateway) career sites, e.g. jobs.ubs.com.

params: host (jobs.ubs.com), partner_id, site_id, keyword_fields, location_fields (as configured on the site)
"""
import re

from .. import http
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    p = src["params"]
    host, pid, sid = p["host"], str(p["partner_id"]), str(p["site_id"])
    s = http.make_session()
    home = s.get(f"https://{host}/TGnewUI/Search/Home/Home?partnerid={pid}&siteid={sid}", timeout=40)
    home.raise_for_status()
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', home.text)
    if not m:
        raise RuntimeError("BrassRing verification token not found (page layout changed?)")
    headers = {"RFT": m.group(1), "X-Requested-With": "XMLHttpRequest", "Referer": home.url}
    out, page, total = {}, 1, None
    while True:
        body = {"partnerId": pid, "siteId": sid, "keyword": "", "location": "",
                "keywordCustomSolrFields": p.get("keyword_fields", "FORMTEXT2,FORMTEXT21,AutoReq,Department,JobTitle"),
                "locationCustomSolrFields": p.get("location_fields", "FORMTEXT2,FORMTEXT23,Location"),
                "linkId": "", "Latitude": 0, "Longitude": 0, "facetfilterfields": {"Facet": []},
                "powersearchoptions": {"PowerSearchOption": []}, "SortType": "LastUpdated", "pageNumber": page,
                "encryptedSessionValue": ""}
        ep = "MatchedJobs" if page == 1 else "ProcessSortAndShowMoreJobs"
        r = s.post(f"https://{host}/TgNewUI/Search/Ajax/{ep}", json=body, headers=headers, timeout=40)
        r.raise_for_status()
        d = r.json()
        total = d.get("JobsCount", 0) if total is None else total
        jobs = (d.get("Jobs") or {}).get("Job") or []
        for j in jobs:
            q = {x["QuestionName"]: (x.get("Value") or "") for x in j.get("Questions", [])}
            rid = q.get("reqid") or re.search(r"jobid=(\d+)", j.get("Link", "")).group(1)
            loc = ", ".join(x for x in [q.get(p.get("city_field", "formtext2"), ""), q.get(p.get("country_field", "formtext23"), "")] if x)
            out[rid] = Posting(
                id=f"{src['key']}:{rid}", company=src["name"], title=html_to_text(q.get("jobtitle", "")),
                location=loc, url=j.get("Link") or f"https://{host}/TGnewUI/Search/home/HomeWithPreLoad?partnerid={pid}&siteid={sid}&PageType=JobDetails&jobid={rid}",
                posted_at=iso_date(_d(q.get("lastupdated", ""))), description_text="",
                source_adapter="brassring", source_key=src["key"],
                extra={"department": q.get("department", ""), "teaser": q.get("jobdescription", "")})
        page += 1
        if not jobs or len(out) >= total or page > 60:
            break
    return list(out.values())


def _d(s):
    import datetime as dt
    try:
        return dt.datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except ValueError:
        return ""


def detail(src, post):
    """Job details are rendered by Angular – read the rendered page text."""
    from ..http import Browser
    res = Browser.get().render(post.url, wait_ms=5000)
    txt = res["text"]
    i = txt.find(post.title[:30])
    post.description_text = txt[i if i > 0 else 0:][:15000]
