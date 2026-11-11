"""The daily run: fetch every source, filter, enrich, verify URLs, update history, record source health."""
from __future__ import annotations

import datetime as dt
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import adapters, config, enrich, filters, verify
from .http import Browser
from .models import Posting, clean_ws
from .store import Store

DETAIL_CAP = 80          # max detail calls per source per run (only for postings that pass the title filter)
MISSES_TO_REMOVE = 2


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_source(src: dict) -> tuple[list[Posting], str | None, float]:
    t0 = time.time()
    try:
        mod = adapters.get(src["adapter"])
        posts = mod.fetch(src)
        clean = []
        for p in posts:
            p.title = clean_ws(__import__("html").unescape(p.title or ""))
            p.location = clean_ws(__import__("html").unescape(p.location or ""))
            p.source_key = src["key"]
            if config.is_aggregator(p.url) or config.is_aggregator(p.apply_url):
                continue  # never allowed as a source or a link
            if p.title:
                clean.append(p)
        # de-duplicate ids within a source
        uniq = {}
        for p in clean:
            uniq.setdefault(p.id, p)
        return list(uniq.values()), None, time.time() - t0
    except Exception as e:
        return [], f"{type(e).__name__}: {str(e)[:300]}", time.time() - t0


def health_label(ok: bool, fetched: int, history: list[dict]) -> str:
    if not ok:
        return "ERROR"
    prev = [h["fetched"] for h in history if h["ok"]]
    if fetched == 0:
        return "ZERO (usually has jobs)" if prev and max(prev) > 0 else "OK (0 open jobs listed)"
    if prev and fetched < 0.3 * (sum(prev) / len(prev)) and sum(prev) / len(prev) > 10:
        return "WARN (far fewer jobs than usual)"
    return "OK"


def _meta(p: Posting) -> str:
    keys = ("department", "division", "category", "function", "jobFunction", "career_level", "jobFamily")
    return " ".join(str(p.extra.get(k, "")) for k in keys if p.extra.get(k))


def classify_and_enrich(src: dict, posts: list[Posting], store: Store | None, pay_table: dict,
                        refresh: bool = False) -> list[dict]:
    """Return one record per posting (all postings, with relevance)."""
    mod = adapters.get(src["adapter"])
    old = store.by_source(src["key"]) if store else {}
    records, need_detail = [], []
    for p in posts:
        prev = old.get(p.id)
        desc = p.description_text
        if not desc and prev and prev.get("description") and prev.get("title") == p.title and not refresh:
            desc = prev["description"]
            p.description_text = desc
            p.deadline = p.deadline or prev.get("deadline") or ""
            p.salary_text = p.salary_text or prev.get("salary_text") or ""
            if prev.get("location") and len(prev["location"]) > len(p.location):
                p.location = prev["location"]
        v = filters.classify(p.title, p.location, desc, src["sector"], src, _meta(p))
        if v.relevance != "drop" and not desc and hasattr(mod, "detail"):
            if prev and prev.get("title") == p.title and prev.get("relevance") == "drop" and not refresh:
                pass  # dropped after a detail read in an earlier run – keep that decision
            else:
                need_detail.append(p)
        records.append((p, v))

    # detail calls (parallel, capped)
    cap = src.get("params", {}).get("detail_cap", DETAIL_CAP)
    todo = need_detail[:cap]
    if todo:
        def _d(p):
            try:
                mod.detail(src, p)
            except Exception as e:
                p.extra["detail_error"] = f"{type(e).__name__}: {str(e)[:150]}"
            return p
        workers = 1 if src["adapter"] in ("successfactors", "hibob") and src["params"].get("mode") == "classic" else 6
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(_d, todo))

    out = []
    todo_ids = {p.id for p in todo}
    for p, v in records:
        prev = old.get(p.id)
        if p.id in todo_ids or p.description_text:
            v = filters.classify(p.title, p.location, p.description_text, src["sector"], src, _meta(p))
        elif prev and prev.get("title") == p.title and prev.get("relevance") == "drop" and not refresh and v.relevance != "drop":
            v = filters.Verdict("drop", prev.get("reason") or "dropped earlier", v.level, v.region, v.country)
        rec = {
            "id": p.id, "source_key": src["key"], "company": src.get("display_company") or p.company,
            "sector": src["sector"], "segment": src.get("segment", ""), "title": p.title, "location": p.location,
            "country": v.country, "url": p.url, "apply_url": p.apply_url or p.url, "posted_at": p.posted_at,
            "deadline": p.deadline, "relevance": v.relevance, "reason": v.reason, "level": v.level,
            "salary_text": p.salary_text, "source_adapter": src["adapter"],
            "description": p.description_text if v.relevance != "drop" else "",
            "extra": p.extra,
        }
        if v.relevance != "drop":
            enrich.enrich(rec, pay_table)
        out.append(rec)
    return out


def run(dry_run: bool = False, do_verify: bool = True, only: list[str] | None = None, refresh: bool = False,
        workers: int = 8, log=print, claude: bool = True) -> dict:
    all_sources = config.load_sources()
    if only:
        all_sources = [s for s in all_sources if s["key"] in only or s["name"] in only]
    sources = [s for s in all_sources if s.get("enabled", True)]
    disabled = [s for s in all_sources if not s.get("enabled", True)]
    store = Store()
    pay_table = config.load_yaml(config.PAY_FILE, {})
    today = dt.date.today().isoformat()
    started = now_iso()
    run_id = None if dry_run else store.start_run(started)
    results: dict[str, dict] = {}

    log(f"Fetching {len(sources)} sources …")
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fetch_source, s): s for s in sources}
        for f in as_completed(futs):
            s = futs[f]
            posts, err, dur = f.result()
            results[s["key"]] = {"src": s, "posts": posts, "error": err, "duration": dur}
            log(f"  {'ERR' if err else 'ok '} {s['name']:<38} {s['adapter']:<16} {len(posts):>5} jobs  {dur:5.1f}s"
                + (f"  {err}" if err else ""))

    log("Filtering & enriching …")
    for key, r in results.items():
        if r["error"]:
            r["records"] = []
            continue
        try:
            r["records"] = classify_and_enrich(r["src"], r["posts"], store, pay_table, refresh)
        except Exception as e:
            r["error"] = f"filter/enrich failed: {type(e).__name__}: {e}"
            r["records"] = []
            traceback.print_exc()

    relevant = [rec for r in results.values() for rec in r["records"] if rec["relevance"] != "drop"]

    # Optional Claude scoring for new relevant postings only (keeps API use small)
    profile = config.PROFILE_FILE.read_text(encoding="utf-8") if config.PROFILE_FILE.exists() else ""
    if claude and profile:
        for rec in relevant:
            prev = store.get(rec["id"])
            if prev and prev.get("score_source") == "claude" and prev.get("title") == rec["title"]:
                rec["score"], rec["why"], rec["score_source"] = prev["score"], prev["why"], "claude"
                continue
            res = enrich.claude_score(rec, profile)
            if res:
                rec["score"], rec["why"], rec["score_source"] = res[0], res[1], "claude"

    # URL verification for every relevant posting
    if do_verify and relevant:
        log(f"Verifying {len(relevant)} official URLs …")
        verify_records(relevant, log=log)

    Browser.close_all()
    summary = {"run_id": run_id, "started": started, "sources": [], "relevant": len(relevant)}
    for key, r in sorted(results.items(), key=lambda kv: kv[1]["src"]["name"].lower()):
        s = r["src"]
        ok = r["error"] is None
        recs = r["records"]
        hist = store.source_history(key)
        h = health_label(ok, len(r["posts"]), hist)
        row = {"source_key": key, "name": s["name"], "sector": s["sector"], "adapter": s["adapter"], "ok": int(ok),
               "fetched": len(r["posts"]), "relevant": sum(1 for x in recs if x["relevance"] == "keep"),
               "maybe": sum(1 for x in recs if x["relevance"] == "maybe"), "error": r["error"] or "",
               "duration": round(r["duration"], 1), "snapshot": s.get("_snapshot", ""), "health": h,
               "notes": s.get("notes", ""), "careers_url": s.get("careers_url", "")}
        summary["sources"].append(row)
        if dry_run:
            continue
        store.add_source_run(run_id=run_id, run_at=started, **{k: v for k, v in row.items()
                                                                   if k not in ("notes", "careers_url")})
        if ok:
            _apply_history(store, key, recs, today, started, partial=bool(s["params"].get("partial")), log=log)
    for s in disabled:
        summary["sources"].append({"source_key": s["key"], "name": s["name"], "sector": s["sector"], "adapter": s["adapter"],
                                   "ok": 0, "fetched": 0, "relevant": 0, "maybe": 0, "error": "", "duration": 0,
                                   "snapshot": "", "health": "DISABLED", "notes": s.get("notes", ""),
                                   "careers_url": s.get("careers_url", "")})
    if not dry_run:
        store.finish_run(run_id, now_iso(), json.dumps({"relevant": len(relevant)}))
    store.close()
    summary["records"] = relevant
    return summary


def verify_records(recs: list[dict], log=print, workers: int = 10):
    def _v(rec):
        ok, note = verify.check(rec["url"], rec["title"], rec.get("source_adapter", ""), allow_render=False)
        return rec, ok, note
    retry = []
    with ThreadPoolExecutor(workers) as ex:
        for rec, ok, note in ex.map(_v, recs):
            rec["verified"], rec["verify_note"], rec["verified_at"] = int(ok), note, now_iso()
            if not ok:
                retry.append(rec)
    # second pass with a headless browser for JavaScript-rendered pages / bot checks
    for rec in retry:
        ok, note = verify.check(rec["url"], rec["title"], rec.get("source_adapter", ""), allow_render=True)
        rec["verified"], rec["verify_note"], rec["verified_at"] = int(ok), note, now_iso()
    bad = [r for r in recs if not r["verified"]]
    log(f"  verified {len(recs) - len(bad)}/{len(recs)} OK; {len(bad)} failed (hidden from the active view)")


def _apply_history(store: Store, key: str, recs: list[dict], today: str, run_at: str, partial: bool = False,
                   log=print):
    seen = set()
    for rec in recs:
        seen.add(rec["id"])
        prev = store.get(rec["id"])
        rec["first_seen"] = prev["first_seen"] if prev else today
        rec["last_seen"] = today
        rec["status"] = "active"
        rec["consecutive_misses"] = 0
        rec["removed_at"] = None
        if rec["relevance"] == "drop":
            # keep a light record so the decision is remembered and misses can be tracked
            for k in ("description",):
                rec[k] = ""
        if "verified" not in rec and prev:
            rec["verified"], rec["verify_note"], rec["verified_at"] = prev.get("verified"), prev.get("verify_note"), prev.get("verified_at")
        store.upsert(rec)
    for pid, prev in store.by_source(key).items():
        if pid in seen or prev["status"] == "removed":
            continue
        if partial and prev.get("relevance") in ("keep", "maybe"):
            # the source only exposes part of its list (e.g. first pages): a posting that is not in today's list
            # counts as missing only if its official page is gone too
            ok, note = verify.check(prev["url"], prev["title"], prev.get("source_adapter") or "", allow_render=True)
            if ok:
                store.update(pid, verified=1, verify_note=note + " (not in today's partial list)", consecutive_misses=0)
                continue
        misses = (prev["consecutive_misses"] or 0) + 1
        if misses >= MISSES_TO_REMOVE:
            store.update(pid, consecutive_misses=misses, status="removed", removed_at=today)
        else:
            store.update(pid, consecutive_misses=misses)
    store.commit()
