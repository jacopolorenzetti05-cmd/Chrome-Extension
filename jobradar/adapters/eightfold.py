"""Eightfold AI career sites: GET https://{host}/api/pcsx/search?domain={domain}

params: host (e.g. morganstanley.eightfold.ai), domain (morganstanley.com)
"""
from .. import http
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    p = src["params"]
    out, start = {}, 0
    while True:
        d = http.get_json(f"https://{p['host']}/api/pcsx/search",
                          params={"domain": p["domain"], "query": "", "location": "", "start": start, "num": 100})["data"]
        pos = d.get("positions", [])
        for j in pos:
            out[j["id"]] = Posting(
                id=f"{src['key']}:{j['id']}", company=src["name"], title=j["name"],
                location=" | ".join(j.get("locations") or j.get("standardizedLocations") or []),
                url=f"https://{p['host']}/careers/job/{j['id']}?domain={p['domain']}",
                posted_at=iso_date(j.get("postedTs")), source_adapter="eightfold", source_key=src["key"],
                extra={"department": j.get("department", ""), "atsJobId": j.get("atsJobId", "")})
        start += len(pos)
        if not pos or start >= d.get("count", 0) or start >= 5000:
            break
    return list(out.values())


def detail(src, post):
    p = src["params"]
    jid = post.id.split(":", 1)[1]
    r = http.get(f"https://{p['host']}/api/pcsx/position_details",
                 params={"position_id": jid, "domain": p["domain"], "hl": "en"})
    if r.status_code == 200:
        d = r.json().get("data", {})
        post.description_text = html_to_text(d.get("jobDescription") or d.get("job_description") or "")
        if d.get("publicUrl"):
            post.url = d["publicUrl"]
