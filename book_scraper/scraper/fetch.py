"""HTTP layer: one session, retries, timeout, polite delay. Restricted to books.toscrape.com."""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://books.toscrape.com/"
ALLOWED_HOST = "books.toscrape.com"


class Fetcher:
    def __init__(self, delay: float = 0.1, timeout: float = 15.0, pool_size: int = 8):
        self.delay = delay
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last_request = 0.0

        retry = Retry(
            total=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=pool_size)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = "book-scraper-experiment/1.0"

    def get(self, url: str) -> str:
        if urlparse(url).hostname != ALLOWED_HOST:
            raise ValueError(f"refusing to fetch outside {ALLOWED_HOST}: {url}")
        self._throttle()
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        # The site serves UTF-8 but doesn't always say so; without this '£' turns into 'Â£'.
        resp.encoding = "utf-8"
        return resp.text

    def _throttle(self) -> None:
        # Space requests out across all threads by at least `delay` seconds.
        with self._lock:
            wait = self._last_request + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
