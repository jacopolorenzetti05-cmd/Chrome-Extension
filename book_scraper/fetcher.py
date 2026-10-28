"""HTTP layer: one place for sessions, retries and politeness."""
from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "book-scraper-experiment/1.0 (+books.toscrape.com sandbox)"
ALLOWED_HOST = "books.toscrape.com"


class Fetcher:
    def __init__(self, delay: float = 0.1, timeout: float = 15.0, retries: int = 3):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        retry = Retry(total=retries, backoff_factor=0.5,
                      status_forcelist=(429, 500, 502, 503, 504))
        self.session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        self.session.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=16))

    def get(self, url: str) -> str:
        if ALLOWED_HOST not in url:
            raise ValueError(f"refusing to fetch outside {ALLOWED_HOST}: {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        # The site serves UTF-8 but omits the charset, so requests guesses
        # ISO-8859-1 and "£" would decode as "Â£".
        response.encoding = "utf-8"
        if self.delay:
            time.sleep(self.delay)
        return response.text
