"""Teamtailor career site RSS feed: {careers domain}/jobs.rss"""
import xml.etree.ElementTree as ET

from .. import http
from ..models import Posting, html_to_text, iso_date

NS = {"tt": "https://teamtailor.com/locations"}


def fetch(src):
    p = src["params"]
    base = (p.get("base_url") or f"https://{p['company']}.teamtailor.com").rstrip("/")
    r = http.get(base + "/jobs.rss")
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        locs = []
        for loc in it.findall("tt:locations/tt:location", NS):
            city = loc.findtext("tt:city", default="", namespaces=NS)
            country = loc.findtext("tt:country", default="", namespaces=NS)
            locs.append(", ".join(x for x in [city, country] if x))
        jid = link.rstrip("/").split("/")[-1].split("-")[0]
        out.append(Posting(
            id=f"{src['key']}:{jid}", company=src["name"], title=it.findtext("title") or "",
            location=" | ".join(l for l in locs if l) or (it.findtext("remoteStatus") or ""),
            url=link, posted_at=iso_date(__import__("email.utils").utils.parsedate_to_datetime(it.findtext("pubDate")).isoformat()) if it.findtext("pubDate") else "",
            description_text=html_to_text(it.findtext("description") or ""),
            source_adapter="teamtailor", source_key=src["key"]))
    return out
