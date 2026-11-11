"""Live check of an official posting URL: HTTP 200, not redirected to a closed/search page, title on the page."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import http
from .config import is_aggregator
from .http import Browser
from .models import html_to_text, norm

CLOSED = re.compile(r"no longer (?:available|accepting|open|active)|job (?:has been )?closed|position (?:has been )?(?:filled|closed)|"
                    r"posting (?:has )?(?:expired|closed)|this job (?:is )?(?:not|no longer) available|vacancy (?:has )?closed|"
                    r"stelle ist (?:leider )?(?:nicht mehr|bereits)|nicht mehr verfugbar|nicht mehr verfuegbar|"
                    r"non e piu disponibile|annuncio scaduto|offre (?:n est plus|expiree)|oferta (?:no esta disponible|caducada)|"
                    r"page (?:you are looking for|not found)|job not found|404 not found|the job you are looking for")
# Pages rendered with JavaScript – fall back to a headless browser when the title is not in the raw HTML
JS_ADAPTERS = {"oracle", "eightfold", "phenom", "successfactors", "hibob", "gs", "jobylon", "html", "beesite",
               "digitalrecruiters", "workday", "pinpoint", "brassring", "avature", "factorial"}


def title_on_page(title: str, text_n: str) -> tuple[bool, str]:
    t = norm(title)
    if not t:
        return False, "empty title"
    if t in text_n:
        return True, "exact"
    # titles often carry gender tags / suffixes that pages render differently: require 85% of the words in order-free match
    words = [w for w in t.split() if len(w) > 1 and w not in {"m", "w", "d", "f", "x", "gn", "h", "mwd", "fmd", "all"}]
    if not words:
        return False, "no words"
    hit = sum(1 for w in words if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text_n))
    ratio = hit / len(words)
    return (ratio >= 0.85 and len(words) >= 2), f"{ratio:.0%} of title words"


def check(url: str, title: str, adapter: str = "", allow_render: bool = True) -> tuple[bool, str]:
    if not url or not url.startswith("http"):
        return False, "no URL"
    if is_aggregator(url):
        return False, "aggregator domain"
    try:
        r = http.get(url, allow_redirects=True)
    except Exception as e:
        r = None
        err = f"request error: {type(e).__name__}"
    status = r.status_code if r is not None else 0
    note = f"HTTP {status}" if r is not None else err
    if r is not None and status == 200 and ("pdf" in r.headers.get("content-type", "") or r.content[:4] == b"%PDF"):
        from .adapters.html import _pdf_text
        ok, how = title_on_page(title, norm(_pdf_text(r.content)))
        return ok, f"HTTP 200 (PDF), {'title found' if ok else 'title not found'} ({how})"
    if r is not None and status == 200:
        ok, how = _judge(url, r.url, r.text, title, adapter)
        if ok:
            return True, f"HTTP 200, title found ({how})"
        note = f"HTTP 200 but {how}"
    if allow_render and (adapter in JS_ADAPTERS or status in (0, 403, 429, 202) or (r is not None and status == 200)):
        try:
            res = Browser.get().render(url, wait_ms=4000)
        except Exception as e:
            return False, f"{note}; render failed: {type(e).__name__}"
        st = res.get("status") or 0
        if st not in (200, 304):
            return False, f"{note}; rendered HTTP {st}"
        ok, how = _judge(url, res["url"], res["html"] + " " + res["text"], title, adapter, text=res["text"] + " " + res.get("title", ""))
        if ok:
            return True, f"HTTP 200 (rendered), title found ({how})"
        return False, f"{note}; rendered page: {how}"
    return False, note


def _judge(orig: str, final: str, html: str, title: str, adapter: str, text: str | None = None) -> tuple[bool, str]:
    o, f = urlparse(orig), urlparse(final)
    if is_aggregator(final):
        return False, "redirected to aggregator"
    if f.netloc and o.netloc and f.netloc.split(".")[-2:] != o.netloc.split(".")[-2:] and "login" in final.lower():
        return False, f"redirected to {f.netloc}"
    if re.search(r"(/search/?$|/jobs/?$|/careers/?$|[?&](error|expired)=)", f.path + ("?" + f.query if f.query else "")) \
            and f.path.rstrip("/") != o.path.rstrip("/"):
        return False, f"redirected to listing page ({final[:80]})"
    meta = " ".join(re.findall(r'<meta[^>]+content="([^"]*)"', html or ""))[:5000]
    page_title = " ".join(re.findall(r"<title[^>]*>(.*?)</title>", html or "", re.S))[:500]
    body = text if text is not None else html_to_text(html)
    text_n = norm(page_title + " " + meta + " " + body)
    ok, how = title_on_page(title, text_n)
    if not ok:
        return False, f"title not found ({how})"
    head = norm(page_title + " " + body[:3000])
    if CLOSED.search(head):
        return False, "page says the job is closed"
    return True, how
