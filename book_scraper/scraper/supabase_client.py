"""Minimal Supabase client over its REST API (PostgREST). Only what the scraper needs."""

from __future__ import annotations

import os

import requests


class SupabaseError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self, url: str, key: str, timeout: float = 30.0):
        self.base = url.rstrip("/") + "/rest/v1"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"apikey": key, "Content-Type": "application/json"})
        # Legacy keys are JWTs and go in Authorization too; new sb_secret_ keys only go in apikey.
        if key.startswith("eyJ"):
            self.session.headers["Authorization"] = f"Bearer {key}"

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        _load_dotenv()
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise SupabaseError(
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) "
                "in the environment or in a .env file — see .env.example"
            )
        return cls(url, key)

    def insert(self, table: str, rows: list[dict], on_conflict: str | None = None) -> list[dict]:
        """Insert rows and return them as stored. With `on_conflict`, upsert on that column."""
        prefer = ["return=representation"]
        params = {}
        if on_conflict:
            prefer.append("resolution=merge-duplicates")
            params["on_conflict"] = on_conflict
        resp = self.session.post(
            f"{self.base}/{table}", json=rows, params=params,
            headers={"Prefer": ",".join(prefer)}, timeout=self.timeout,
        )
        return self._check(resp)

    def select(self, table: str, columns: str = "*", **filters: str) -> list[dict]:
        """`filters` use PostgREST syntax, e.g. select('books', id='eq.5')."""
        params = {"select": columns, **filters}
        resp = self.session.get(f"{self.base}/{table}", params=params, timeout=self.timeout)
        return self._check(resp)

    def update(self, table: str, values: dict, **filters: str) -> list[dict]:
        resp = self.session.patch(
            f"{self.base}/{table}", json=values, params=filters,
            headers={"Prefer": "return=representation"}, timeout=self.timeout,
        )
        return self._check(resp)

    def delete(self, table: str, **filters: str) -> None:
        if not filters:
            raise ValueError("refusing to delete without a filter")
        resp = self.session.delete(f"{self.base}/{table}", params=filters, timeout=self.timeout)
        self._check(resp)

    @staticmethod
    def _check(resp: requests.Response):
        if resp.status_code >= 400:
            raise SupabaseError(f"{resp.request.method} {resp.url} -> {resp.status_code}: {resp.text}")
        return resp.json() if resp.content else []


def _load_dotenv(path: str = ".env") -> None:
    """Tiny .env reader so we don't need python-dotenv. Real env vars win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
