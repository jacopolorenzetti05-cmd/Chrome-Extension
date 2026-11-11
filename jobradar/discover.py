"""`add-source`: open an official careers page, detect which hiring system it uses, test it live and
append it to sources.yaml."""
from __future__ import annotations

import re

import yaml

from . import adapters, config
from .http import Browser

SIGNATURES = [
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=|v1/boards/)?([A-Za-z0-9_-]+)", lambda m: {"token": m.group(1)}),
    ("lever", r"jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9_-]+)", lambda m: {"company": m.group(1)}),
    ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", lambda m: {"company": m.group(1)}),
    ("workable", r"apply\.workable\.com/([A-Za-z0-9_-]+)", lambda m: {"account": m.group(1)}),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)", lambda m: {"org": m.group(1)}),
    ("personio", r"([a-z0-9-]+)\.jobs\.personio\.(de|com)", lambda m: {"company": m.group(1), "tld": m.group(2)}),
    ("recruitee", r"([a-z0-9-]+)\.recruitee\.com", lambda m: {"company": m.group(1)}),
    ("teamtailor", r"https?://([a-z0-9-]+)\.teamtailor\.com", lambda m: {"company": m.group(1)}),
    ("workday", r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)",
     lambda m: {"host": f"{m.group(1)}.{m.group(2)}.myworkdayjobs.com", "tenant": m.group(1), "site": m.group(3)}),
    ("oracle", r"([a-z0-9.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}/sites/([A-Za-z0-9_]+)",
     lambda m: {"host": m.group(1), "site": m.group(2)}),
    ("pinpoint", r"([a-z0-9-]+)\.pinpointhq\.com", lambda m: {"company": m.group(1)}),
    ("eightfold", r"([a-z0-9-]+)\.eightfold\.ai", lambda m: {"host": f"{m.group(1)}.eightfold.ai", "domain": f"{m.group(1)}.com"}),
    ("successfactors", r"(career\d*\.(?:successfactors\.eu|successfactors\.com|sapsf\.eu|sapsf\.com))/career\?company=([A-Za-z0-9_]+)",
     lambda m: {"mode": "classic", "host": m.group(1), "company": m.group(2)}),
]


def detect(careers_url: str) -> tuple[str, dict, str]:
    res = Browser.get().render(careers_url, wait_ms=5000)
    blob = " ".join([res["url"], res["html"]] + [h for h, _ in res["links"]])
    for name, rx, fn in SIGNATURES:
        m = re.search(rx, blob)
        if m:
            return name, fn(m), f"detected {name} via {m.group(0)[:80]}"
    if "jobTitle-link" in res["html"]:
        base = re.match(r"https?://[^/]+", res["url"]).group(0)
        return "successfactors", {"mode": "rmk", "base_url": base}, "SuccessFactors RMK markup on page"
    if "softgarden" in blob:
        base = re.match(r"https?://[^/]+", res["url"]).group(0)
        return "softgarden", {"base_url": base}, "softgarden career site"
    if "emp.jobylon.com/jobs" in blob:
        return "jobylon", {"list_urls": [careers_url]}, "Jobylon job links on page"
    if "phenompeople" in blob:
        base = re.match(r"https?://[^/]+", res["url"]).group(0)
        return "phenom", {"base_url": base}, "Phenom career site"
    host = re.match(r"https?://([^/]+)", res["url"]).group(1)
    return "html", {"list_urls": [careers_url], "render": True,
                    "link_pattern": re.escape(host) + r"/.*(job|stelle|vacanc|position|karriere|career)"}, \
        "no machine-readable source found – html fallback (review link_pattern)"


def add_source(name, sector, careers_url, segment="", country="", write=True) -> int:
    adapter, params, how = detect(careers_url)
    entry = {"name": name, "sector": sector, "segment": segment, "country": country, "adapter": adapter,
             "careers_url": careers_url, "params": params, "notes": how}
    src = dict(entry, key=config.slug(name))
    try:
        posts = adapters.get(adapter).fetch(src)
        print(f"{how}\nLive test: {len(posts)} postings fetched")
        for p in posts[:5]:
            print(f"   - {p.title} | {p.location} | {p.url}")
    except Exception as e:
        print(f"{how}\nLive test FAILED: {type(e).__name__}: {e}")
        entry["notes"] += f"; live test failed: {e}"
    finally:
        Browser.close_all()
    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)
    if write:
        existing = config.load_sources()
        if any(s["key"] == src["key"] for s in existing):
            print(f"A source with key '{src['key']}' already exists – not added.")
            return 1
        with open(config.SOURCES_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join("  " + l if l else l for l in block.splitlines()) + "\n")
        print(f"Added to {config.SOURCES_FILE}")
    else:
        print(block)
    return 0
