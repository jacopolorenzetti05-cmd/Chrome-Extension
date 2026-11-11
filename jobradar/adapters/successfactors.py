"""SAP SuccessFactors career sites.

mode "rmk" (Recruiting Marketing career sites, server-rendered):
    params: base_url (e.g. https://careers.cityfootballgroup.com), search_path (default /search/), query (default "")
mode "classic" (career{N}.successfactors.eu/career?company=...; JavaScript list):
    params: host, company, locale (optional)
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..http import Browser
from ..models import Posting, clean_ws, html_to_text, iso_date
from . import html as html_adapter


def fetch(src):
    mode = src["params"].get("mode", "rmk")
    if mode == "feed":
        return _feed(src)
    return _rmk(src) if mode == "rmk" else _classic(src)


def _feed(src):
    """RMK 'job2web' XML feed (e.g. careers.adidas-group.com/jobs/feed.xml) – full list incl. descriptions."""
    import xml.etree.ElementTree as ET
    p = src["params"]
    r = http.get(p["feed_url"], timeout=90)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    countries = {c.lower() for c in p.get("countries", [])}
    out = {}
    for j in root.iter("job"):
        g = lambda t: (j.findtext(t) or "").strip()
        if countries and g("country").lower() not in countries:
            continue
        url = re.sub(r"[?&](feedId|utm_source)=[^&]*", "", g("url")).rstrip("?&")
        m = re.search(r"/(\d{6,})/?", url)
        jid = m.group(1) if m else g("referencenumber")
        out[jid] = Posting(id=f"{src['key']}:{jid}", company=src["name"], title=g("title"),
                           location=", ".join(x for x in [g("city"), g("country")] if x), url=url,
                           description_text=html_to_text(g("description")), source_adapter="successfactors",
                           source_key=src["key"], extra={"category": g("category"), "jobtype": g("jobtype")})
    return list(out.values())


def _rmk(src):
    p = src["params"]
    base = p["base_url"].rstrip("/")
    path = p.get("search_path", "/search/")
    out, start = {}, 0
    while True:
        r = http.get(f"{base}{path}", params={"q": p.get("query", ""), "startrow": start, **p.get("extra_query", {})})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        rows = soup.select("tr.data-row") or soup.select("li.job-tile") or soup.select("div.job-tile")
        new = 0
        for row in rows:
            a = row.select_one("a.jobTitle-link") or row.select_one("a[href*='/job/']")
            if not a:
                continue
            url = urljoin(base + "/", a["href"])
            m = re.search(r"/(\d{6,})/?", url)
            jid = m.group(1) if m else url
            if jid in out:
                continue
            loc = row.select_one(".jobLocation") or row.select_one("[id*=location]")
            date = row.select_one(".jobDate") or row.select_one("[id*=date]")
            loc_s = re.sub(r"^(Location|Standort|Sede|Ubicaci[oó]n)\s*", "", clean_ws(loc.get_text(" ")), flags=re.I) if loc else ""
            out[jid] = Posting(id=f"{src['key']}:{jid}", company=src["name"], title=clean_ws(a.get_text(" ")),
                               location=loc_s, url=url,
                               posted_at=iso_date(clean_ws(date.get_text(" ")) if date else ""),
                               source_adapter="successfactors", source_key=src["key"])
            new += 1
        start += max(len(rows), 1)
        if not rows or not new or start > p.get("max_results", 1500):
            break
    return list(out.values())


def _classic(src):
    p = src["params"]
    host, company = p["host"], p["company"]
    url = f"https://{host}/career?company={company}&career_ns=job_listing_summary&navBarLevel=JOB_SEARCH"
    if p.get("locale"):
        url += f"&lang={p['locale']}"
    res = Browser.get().call(_classic_pages, url, p.get("max_pages", 15))
    out = {}
    for href, text in res["links"]:
        m = re.search(r"career_job_req_id=(\d+)", href)
        if not m or not text.strip():
            continue
        jid = m.group(1)
        link = f"https://{host}/career?company={company}&career_ns=job_listing&career_job_req_id={jid}&navBarLevel=JOB_SEARCH"
        if jid not in out or len(text) > len(out[jid].title):
            out[jid] = Posting(id=f"{src['key']}:{jid}", company=src["name"], title=clean_ws(text),
                               location=p.get("default_location", ""), url=link,
                               source_adapter="successfactors", source_key=src["key"])
    # location/date is in the row text after the title
    text = res["text"]
    for post in out.values():
        i = text.find(post.title)
        if i >= 0:
            row = clean_ws(text[i: i + 250])
            post.extra["row"] = row
            m = re.search(r"Posted on (\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(.*?)(?:\s+Select|\s+Requisition|$)", row)
            if m:
                post.posted_at = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
                post.location = post.location or m.group(4).strip()
    return list(out.values())


def _classic_pages(ctx, url, max_pages):
    page = ctx.new_page()
    links, texts = [], []
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("a[href*='career_job_req_id']", timeout=25000)
        except Exception:
            pass
        page.wait_for_timeout(2500)
        seen_first = None
        for _ in range(max_pages):
            got = page.eval_on_selector_all("a[href*='career_job_req_id']",
                                            "els => els.map(e => [e.href, (e.innerText||'').trim()])")
            if not got or (got and got[0][0] == seen_first):
                break
            seen_first = got[0][0]
            links += got
            texts.append(page.inner_text("body"))
            nxt = None
            for sel in ["a.pagination-next:not(.disabled)", "a[title='Next Page']", "a[aria-label='Next Page']",
                        "a[title*='Next']", "a[aria-label*='Next']", "a:has-text('Next')", "a:has-text('Siguiente')"]:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    nxt = el
                    break
            if not nxt:
                break
            nxt.click()
            page.wait_for_timeout(3500)
        return {"links": links, "text": "\n".join(texts)}
    finally:
        page.close()


def detail(src, post):
    if src["params"].get("mode") == "feed":
        return
    if src["params"].get("mode", "rmk") == "rmk":
        r = http.get(post.url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        d = soup.select_one(".jobdescription") or soup.select_one("[itemprop=description]") or soup.select_one(".job")
        post.description_text = html_to_text(str(d)) if d else html_adapter.parse_job_page(r.text, post.url)["description"]
        loc = soup.select_one("[itemprop=jobLocation]") or soup.select_one(".jobGeoLocation")
        if loc and not post.location:
            post.location = clean_ws(loc.get_text(" "))
        dp = soup.select_one("[itemprop=datePosted]")
        if dp and not post.posted_at:
            post.posted_at = iso_date(dp.get("content") or dp.get_text())
    else:
        res = Browser.get().render(post.url, wait_ms=3000)
        post.description_text = clean_ws(res["text"])[:20000]
        m = re.search(r"(?:Location|Ubicaci[oó]n|Lieu|Standort|Sede)\s*:?\s*([^\n]{2,80})", res["text"])
        if m and not post.location:
            post.location = clean_ws(m.group(1))
