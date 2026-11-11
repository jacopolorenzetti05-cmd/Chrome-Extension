"""Personio XML feed: {company}.jobs.personio.de/xml (or .com)"""
import xml.etree.ElementTree as ET

from .. import http
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    c = src["params"]["company"]
    tlds = [src["params"]["tld"]] if src["params"].get("tld") else ["de", "com"]
    for tld in tlds:
        r = http.get(f"https://{c}.jobs.personio.{tld}/xml", params={"language": src["params"].get("language", "en")})
        if r.status_code == 200 and "workzag-jobs" in r.text:
            break
    else:
        raise RuntimeError(f"personio feed for '{c}' not found")
    root = ET.fromstring(r.content)
    out = []
    for pos in root.findall("position"):
        g = lambda t: (pos.findtext(t) or "").strip()
        desc = " ".join(html_to_text((jd.findtext("value") or "")) for jd in pos.iter("jobDescription"))
        offices = [g("office")] + [o.text or "" for o in pos.findall("additionalOffices/office")]
        jid = g("id")
        out.append(Posting(
            id=f"{src['key']}:{jid}", company=src["name"], title=g("name"),
            location=" | ".join(o for o in dict.fromkeys(offices) if o),
            url=f"https://{c}.jobs.personio.{tld}/job/{jid}", posted_at=iso_date(g("createdAt")),
            description_text=desc, source_adapter="personio", source_key=src["key"],
            extra={"schedule": g("schedule"), "seniority": g("seniority"), "employmentType": g("employmentType"),
                   "subcompany": g("subcompany"), "department": g("department")}))
    return out
