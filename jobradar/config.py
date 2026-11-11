"""Paths and configuration loading."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("JOBRADAR_ROOT", Path(__file__).resolve().parent.parent))
SOURCES_FILE = ROOT / "sources.yaml"
PAY_FILE = ROOT / "pay_estimates.yaml"
PROFILE_FILE = ROOT / "profile.md"
STATUS_FILE = ROOT / "my_status.yaml"
DATA_DIR = ROOT / "data"
DB_FILE = Path(os.environ.get("JOBRADAR_DB", DATA_DIR / "jobradar.db"))
SITE_DIR = ROOT / "site"
OUT_DIR = ROOT / "out"

# Domains that must never be the source or the link of a posting.
AGGREGATOR_DOMAINS = [
    "indeed.", "glassdoor.", "linkedin.com/jobs", "iagora.", "jobsinfootball.", "globalsportsjobs.",
    "talendo.", "jobleads.", "monster.", "stepstone.", "totaljobs.", "reed.co.uk", "jooble.",
    "adzuna.", "simplyhired.", "ziprecruiter.", "careerjet.", "neuvoo.", "talent.com", "jobrapido.",
    "infojobs.", "workinsports.", "teamworkonline.com/jobs", "jobsinsports.", "sportsjobs.",
    "efinancialcareers.", "welcometothejungle.", "otta.com", "builtin.", "wellfound.", "kununu.",
    "xing.com/jobs", "jobteaser.", "gradcracker.", "targetjobs.", "prospects.ac.uk", "brightnetwork.",
]


def is_aggregator(url: str) -> bool:
    """True if the URL's host (plus path, for entries like 'linkedin.com/jobs') belongs to a job board/aggregator."""
    from urllib.parse import urlparse
    u = urlparse((url or "").strip().lower())
    host = u.netloc.split("@")[-1].split(":")[0]
    hp = host + u.path
    for d in AGGREGATOR_DOMAINS:
        if "/" in d:
            if ("." + hp).find("." + d) != -1 or hp.startswith(d):
                return True
        elif d.endswith("."):
            # 'indeed.' matches indeed.com, de.indeed.com, indeed.co.uk …
            if re.search(r"(^|\.)" + re.escape(d), host + "."):
                return True
        elif host == d or host.endswith("." + d):
            return True
    return False


def load_sources(path: Path | None = None) -> list[dict]:
    data = yaml.safe_load((path or SOURCES_FILE).read_text(encoding="utf-8")) or {}
    sources = data.get("sources", data) if isinstance(data, dict) else data
    out = []
    seen = set()
    for s in sources:
        s = dict(s)
        s.setdefault("key", slug(s["name"]))
        if s["key"] in seen:
            raise ValueError(f"duplicate source key {s['key']}")
        seen.add(s["key"])
        s.setdefault("params", {})
        s.setdefault("enabled", True)
        out.append(s)
    return out


def load_yaml(path: Path, default):
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text(encoding="utf-8")) or default


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
