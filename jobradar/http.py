"""Shared HTTP client (requests) and lazily started headless browser (Playwright)."""
from __future__ import annotations

import os
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 30


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET", "POST", "HEAD"]), raise_on_status=False)
    ad = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
    s.mount("https://", ad)
    s.mount("http://", ad)
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9,de;q=0.8,it;q=0.7"})
    return s


_local = threading.local()


def session() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = make_session()
    return _local.s


def get(url, **kw) -> requests.Response:
    kw.setdefault("timeout", TIMEOUT)
    return session().get(url, **kw)


def post(url, **kw) -> requests.Response:
    kw.setdefault("timeout", TIMEOUT)
    return session().post(url, **kw)


def get_json(url, **kw):
    r = get(url, **kw)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- browser
class Browser:
    """Single shared Playwright Chromium used for JavaScript-rendered pages.

    Playwright's sync API is bound to one thread, so all calls are serialised
    through a dedicated worker thread.
    """

    _inst = None
    _lock = threading.Lock()

    def __init__(self):
        import queue
        self._q: "queue.Queue" = queue.Queue()
        self._t = threading.Thread(target=self._worker, daemon=True)
        self._ready = threading.Event()
        self._err = None
        self._t.start()
        self._ready.wait(120)
        if self._err:
            raise self._err

    @classmethod
    def get(cls) -> "Browser":
        with cls._lock:
            if cls._inst is None:
                cls._inst = Browser()
            return cls._inst

    @classmethod
    def close_all(cls):
        with cls._lock:
            if cls._inst is not None:
                cls._inst._q.put(None)
                cls._inst = None

    def _worker(self):
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            kw = {"args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}
            exe = os.environ.get("JOBRADAR_CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)
            if exe:
                kw["executable_path"] = exe
            browser = pw.chromium.launch(**kw)
            ctx = browser.new_context(user_agent=UA, locale="en-GB", viewport={"width": 1366, "height": 900})
        except Exception as e:  # pragma: no cover
            self._err = e
            self._ready.set()
            return
        self._ready.set()
        while True:
            item = self._q.get()
            if item is None:
                break
            fn, args, box, ev = item
            try:
                box["result"] = fn(ctx, *args)
            except Exception as e:
                box["error"] = e
            ev.set()
        try:
            browser.close()
            pw.stop()
        except Exception:
            pass

    def call(self, fn, *args, timeout=180):
        box, ev = {}, threading.Event()
        self._q.put((fn, args, box, ev))
        if not ev.wait(timeout):
            raise TimeoutError("browser call timed out")
        if "error" in box:
            raise box["error"]
        return box["result"]

    # helpers -----------------------------------------------------------
    def render(self, url: str, wait_ms: int = 4000, wait_selector: str | None = None,
               scroll: bool = False) -> dict:
        def _do(ctx, url, wait_ms, wait_selector, scroll):
            page = ctx.new_page()
            try:
                resp = page.goto(url, timeout=60000, wait_until="domcontentloaded")
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=20000)
                    except Exception:
                        pass
                page.wait_for_timeout(wait_ms)
                if scroll:
                    for _ in range(6):
                        page.mouse.wheel(0, 4000)
                        page.wait_for_timeout(700)
                html = page.content()
                text = page.inner_text("body") if page.query_selector("body") else ""
                links = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => [e.href, (e.innerText||e.textContent||'').trim()])")
                return {"status": resp.status if resp else 0, "url": page.url, "html": html,
                        "text": text, "links": links, "title": page.title()}
            finally:
                page.close()
        return self.call(_do, url, wait_ms, wait_selector, scroll)

    def fetch_json_via_page(self, page_url: str, api_url: str, method="GET", body=None,
                            headers=None) -> object:
        """Open page_url (to get cookies / pass bot checks) then call api_url with fetch()."""
        def _do(ctx, page_url, api_url, method, body, headers):
            page = ctx.new_page()
            try:
                page.goto(page_url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                return page.evaluate(
                    """async ([u, m, b, h]) => {
                        const r = await fetch(u, {method: m, headers: Object.assign({'Content-Type':'application/json','Accept':'application/json'}, h||{}), body: b ? JSON.stringify(b) : undefined, credentials: 'include'});
                        return await r.json();
                    }""", [api_url, method, body, headers])
            finally:
                page.close()
        return self.call(_do, page_url, api_url, method, body, headers)


def polite_sleep(sec: float = 0.3):
    time.sleep(sec)
