"""Normalised posting model and text helpers."""
from __future__ import annotations

import html as htmllib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from bs4 import BeautifulSoup


@dataclass
class Posting:
    id: str                      # "<source_key>:<native id>" – stable across runs
    company: str
    title: str
    location: str
    url: str                     # official posting page
    apply_url: str = ""          # official apply URL (defaults to url)
    posted_at: str = ""          # ISO date if the source gives one
    description_text: str = ""
    source_adapter: str = ""
    source_key: str = ""
    deadline: str = ""           # ISO date if known
    salary_text: str = ""        # salary as stated by the source (structured fields)
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        self.title = clean_ws(htmllib.unescape(self.title or ""))
        self.location = clean_ws(htmllib.unescape(self.location or ""))
        if not self.apply_url:
            self.apply_url = self.url

    def to_dict(self) -> dict:
        return asdict(self)


def clean_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def html_to_text(h: str) -> str:
    if not h:
        return ""
    if "<" not in h and "&" not in h:
        return clean_ws(h)
    soup = BeautifulSoup(h, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return clean_ws(soup.get_text(" "))


def norm(s: str) -> str:
    """Lower-case, strip accents and punctuation – used for title matching."""
    s = htmllib.unescape(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def iso_date(s) -> str:
    if not s:
        return ""
    if isinstance(s, (int, float)):
        import datetime as dt
        v = s / 1000 if s > 10**11 else s
        return dt.datetime.utcfromtimestamp(v).date().isoformat()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", str(s))
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


def extract_jsonld_jobposting(html: str) -> dict | None:
    """Return the first schema.org JobPosting found in JSON-LD blocks."""
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html or "", re.S | re.I):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except Exception:
                continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return d
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
    return None


def jsonld_location(jp: dict) -> str:
    locs = jp.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    parts = []
    for loc in locs:
        a = (loc or {}).get("address") or {}
        if isinstance(a, str):
            parts.append(a)
            continue
        country = a.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        bits = [a.get("addressLocality"), a.get("addressRegion"), country]
        parts.append(", ".join(b for b in bits if b))
    return " | ".join(p for p in parts if p)


def jsonld_salary(jp: dict) -> str:
    bs = jp.get("baseSalary")
    if not isinstance(bs, dict):
        return ""
    cur = bs.get("currency", "")
    v = bs.get("value")
    if isinstance(v, dict):
        lo, hi, unit = v.get("minValue"), v.get("maxValue"), v.get("unitText", "")
        val = v.get("value")
        if lo and hi and lo != hi:
            return f"{cur} {lo:,}–{hi:,} / {unit.lower()}".strip()
        if lo or val:
            return f"{cur} {(lo or val):,} / {unit.lower()}".strip()
    elif isinstance(v, (int, float)):
        return f"{cur} {v:,}"
    return ""
