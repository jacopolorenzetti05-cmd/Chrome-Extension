"""Fallback adapter: read the employer's official careers page, extract job links, follow them.

params:
  list_urls:      [url, ...]            official careers/vacancy list page(s)
  link_pattern:   regex                 absolute job URLs to keep (required)
  exclude_pattern: regex                URLs to skip
  render:         bool                  render list pages with headless Chromium (JS sites)
  follow:         bool (default true)   open each job page for title/description (JSON-LD when present)
  follow_render:  bool                  render job pages with Chromium too
  title_from:     page|link             where the title comes from (default page, falls back to link text)
  id_pattern:     regex                 group(1) of the URL = stable id (default: whole URL)
  default_location: str                 used when the page has no location
  paginate:       {param: startrow, step: 25, max: 500}   appended to the first list URL
  max_jobs:       int (default 150)
  wait_selector:  CSS selector to wait for when rendering
The SHA-1 of the sorted job-link list is stored as a snapshot so layout/content changes are visible.
"""
from __future__ import annotations

import hashlib
import io
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

from .. import http
from ..http import Browser
from ..models import (Posting, clean_ws, extract_jsonld_jobposting, html_to_text, iso_date, jsonld_location,
                      jsonld_salary)

BAD_TITLES = re.compile(r"^(apply|apply now|bewerben|jetzt bewerben|candidati|candidatura|more|mehr|read more|details|"
                        r"view job|view|learn more|scopri di più|weiterlesen|zur stelle|postuler|see more|show more|"
                        r"\s*)$", re.I)


def list_links(src) -> list[tuple[str, str]]:
    p = src["params"]
    urls = list(p.get("list_urls") or [src.get("careers_url")])
    pg = p.get("paginate")
    links: list[tuple[str, str]] = []
    pat = re.compile(p["link_pattern"], re.I)
    excl = re.compile(p["exclude_pattern"], re.I) if p.get("exclude_pattern") else None

    def harvest(page_url, html=None, rendered_links=None):
        found = []
        if rendered_links is not None:
            pairs = rendered_links
        else:
            soup = BeautifulSoup(html, "lxml")
            pairs = [(urljoin(page_url, a["href"]), a.get_text(" ")) for a in soup.find_all("a", href=True)]
        for href, text in pairs:
            href = urldefrag(href.replace("&amp;", "&"))[0]
            if pat.search(href) and not (excl and excl.search(href)):
                found.append((href, clean_ws(text)))
        return found

    def load(u):
        if p.get("render"):
            res = Browser.get().render(u, wait_ms=p.get("wait_ms", 4000), wait_selector=p.get("wait_selector"),
                                       scroll=p.get("scroll", False))
            if res["status"] and res["status"] >= 400:
                raise RuntimeError(f"HTTP {res['status']} on {u}")
            return harvest(res["url"], rendered_links=res["links"])
        r = http.get(u, timeout=p.get("timeout", 45))
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} on {u}")
        body = r.text
        if body.lstrip().startswith("{") and "json" in r.headers.get("content-type", ""):
            # some career sites (e.g. Radancy) return the result list as HTML inside JSON
            import json as _json

            def strings(o):
                if isinstance(o, str):
                    yield o
                elif isinstance(o, dict):
                    for v in o.values():
                        yield from strings(v)
                elif isinstance(o, list):
                    for v in o:
                        yield from strings(v)
            body = " ".join(strings(_json.loads(body)))
        found = harvest(r.url, html=body)
        if not found and p.get("rows_selector"):
            # rows exist but no job link matched: the page layout changed – report it instead of "0 jobs"
            if BeautifulSoup(body, "lxml").select(p["rows_selector"]):
                raise RuntimeError(f"list rows present on {u} but no job links matched (layout changed?)")
        return found

    if pg:
        for base in urls:
            sep = "&" if "?" in base else "?"
            start = pg.get("start", 0)
            while start <= pg.get("max", 500):
                got = load(f"{base}{sep}{pg['param']}={pg.get('prefix', '')}{start}")
                new = [g for g in got if g[0] not in {l[0] for l in links}]
                if not new:
                    break
                links.extend(new)
                start += pg.get("step", 1)
    else:
        for u in urls:
            links.extend(load(u))
    # merge duplicates, keep the most informative link text
    best: dict[str, str] = {}
    for href, text in links:
        if href not in best or (len(text) > len(best[href]) and not BAD_TITLES.match(text)):
            best[href] = "" if BAD_TITLES.match(text or "") else text
    return list(best.items())


def parse_job_page(html: str, url: str) -> dict:
    out = {"title": "", "location": "", "description": "", "posted_at": "", "deadline": "", "salary": ""}
    jp = extract_jsonld_jobposting(html)
    if jp:
        out["title"] = clean_ws(str(jp.get("title") or ""))
        out["location"] = jsonld_location(jp)
        out["description"] = html_to_text(str(jp.get("description") or ""))
        out["posted_at"] = iso_date(jp.get("datePosted"))
        out["deadline"] = iso_date(jp.get("validThrough"))
        out["salary"] = jsonld_salary(jp)
    soup = BeautifulSoup(html, "lxml")
    if not out["title"]:
        og = soup.find("meta", property="og:title")
        h1 = soup.find("h1")
        cand = [clean_ws(h1.get_text(" ")) if h1 else "", og.get("content", "") if og else "",
                clean_ws(soup.title.get_text()) if soup.title else ""]
        out["title"] = next((c for c in cand if c and len(c) < 200), "")
    if not out["description"]:
        for t in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            t.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        out["description"] = clean_ws(main.get_text(" "))[:20000]
    return out


def _pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        return clean_ws(" ".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(content)).pages))
    except Exception:
        return ""


def fetch(src):
    p = src["params"]
    links = list_links(src)
    src["_snapshot"] = hashlib.sha1("\n".join(sorted(h for h, _ in links)).encode()).hexdigest()[:16]
    links = links[: p.get("max_jobs", 150)]
    idpat = re.compile(p["id_pattern"]) if p.get("id_pattern") else None

    import time as _time
    deadline = _time.time() + p.get("time_budget", 300)

    def build(item):
        href, text = item
        m = idpat.search(href) if idpat else None
        jid = m.group(1) if m else re.sub(r"^https?://", "", href)
        loc = p.get("default_location", "")
        if p.get("location_from_url"):
            mm = re.search(p["location_from_url"], href)
            if mm:
                loc = mm.group(1).replace("-", " ").title()
        post = Posting(id=f"{src['key']}:{jid}", company=src["name"], title=text, location=loc,
                       url=href, source_adapter="html", source_key=src["key"])
        if p.get("follow", True) and _time.time() < deadline:
            try:
                _fill(src, post, text)
            except Exception as e:  # keep the link-level info, mark the problem
                post.extra["detail_error"] = str(e)[:200]
        return post

    with ThreadPoolExecutor(1 if p.get("follow_render") else 6) as ex:
        posts = list(ex.map(build, links))
    return [x for x in posts if x.title]


def _fill(src, post, link_text):
    p = src["params"]
    if post.url.lower().split("?")[0].endswith(".pdf"):
        r = http.get(post.url)
        r.raise_for_status()
        post.description_text = _pdf_text(r.content)
        return
    if p.get("follow_render"):
        res = Browser.get().render(post.url, wait_ms=p.get("wait_ms", 3000), wait_selector=p.get("detail_wait_selector"))
        html_, final = res["html"], res["url"]
    else:
        r = http.get(post.url)
        r.raise_for_status()
        html_, final = r.text, r.url
    info = parse_job_page(html_, final)
    if p.get("title_from", "page") == "page" and info["title"] and not re.search(p.get("bad_page_title", r"^$"), info["title"], re.I):
        post.title = info["title"]
    elif not post.title:
        post.title = info["title"]
    post.location = info["location"] or post.location
    post.description_text = info["description"]
    post.posted_at = info["posted_at"]
    post.deadline = info["deadline"]
    post.salary_text = info["salary"]
