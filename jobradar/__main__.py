"""Command line: python -m jobradar run | doctor | verify | add-source | export | dashboard | digest"""
from __future__ import annotations

import argparse
import random
import sys

from . import config


def _table(rows: list[list], headers: list[str]) -> str:
    w = [max(len(str(x)) for x in col) for col in zip(headers, *rows)] if rows else [len(h) for h in headers]
    line = "  ".join(h.ljust(w[i]) for i, h in enumerate(headers))
    out = [line, "  ".join("-" * x for x in w)]
    for r in rows:
        out.append("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))
    return "\n".join(out)


def cmd_run(a):
    from . import pipeline
    from .report import dashboard, digest
    from .store import Store
    res = pipeline.run(do_verify=not a.no_verify, only=a.only, refresh=a.refresh, claude=not a.no_claude)
    st = Store()
    path = dashboard.build(st)
    print(f"Dashboard written to {path}")
    if not a.no_digest:
        d = digest.build(st, dashboard_url=a.dashboard_url or "")
        try:
            digest.send(d)
        except Exception as e:
            print(f"Digest delivery failed: {type(e).__name__}: {e}")
            st.close()
            return 2
    st.close()
    bad = [s for s in res["sources"] if s["health"] == "ERROR"]
    print(f"Run finished: {res['relevant']} relevant postings, {len(bad)} sources with errors.")
    return 0


def cmd_doctor(a):
    from . import pipeline
    res = pipeline.run(dry_run=True, do_verify=False, only=a.only, claude=False, log=lambda *x: None)
    rows = []
    for s in res["sources"]:
        status = s["health"] if s["health"] != "ERROR" else "ERROR: " + s["error"][:70]
        rows.append([s["name"][:34], s["sector"], s["adapter"], s["fetched"], s["relevant"], s["maybe"], status])
    print(_table(rows, ["source", "sector", "adapter", "jobs fetched", "relevant", "maybe", "status"]))
    errs = [s for s in res["sources"] if not s["health"].startswith("OK")]
    ok = len(res["sources"]) - len(errs)
    print(f"\n{ok}/{len(res['sources'])} sources OK · {sum(s['fetched'] for s in res['sources'])} jobs fetched · "
          f"{sum(s['relevant'] for s in res['sources'])} relevant + {sum(s['maybe'] for s in res['sources'])} maybe")
    if errs:
        print("\nSources not OK (reason / fallback from sources.yaml notes):")
        for s in errs:
            print(f" - {s['name']}: {s['health']} {s['error']}\n     notes: {s['notes'] or '(none – please document)'}")
    undocumented = [s for s in errs if not s["notes"]]
    return 1 if undocumented else 0


def cmd_verify(a):
    from . import verify
    from .http import Browser
    from .store import Store
    st = Store()
    pool = st.all("status='active' AND relevance IN ('keep','maybe') AND verified=1")
    st.close()
    random.seed(a.seed)
    sample = random.sample(pool, min(a.sample, len(pool)))
    rows, fails = [], 0
    for r in sample:
        ok, note = verify.check(r["url"], r["title"], r["source_adapter"] or "")
        fails += not ok
        rows.append(["PASS" if ok else "FAIL", r["company"][:22], r["title"][:48], note[:60], r["url"][:80]])
    Browser.close_all()
    print(_table(rows, ["result", "company", "title", "check", "official URL"]))
    print(f"\n{len(sample) - fails}/{len(sample)} passed (HTTP 200 + title on the official page), {fails} failures")
    return 1 if fails else 0


def cmd_export(a):
    from .report import export
    x, c = export.export()
    print(f"Wrote {x} and {c}")
    return 0


def cmd_dashboard(a):
    from .report import dashboard
    print(dashboard.build())
    return 0


def cmd_digest(a):
    from .report import digest
    from .store import Store
    st = Store()
    d = digest.build(st, dashboard_url=a.dashboard_url or "")
    st.close()
    digest.send(d)
    return 0


def cmd_add_source(a):
    from . import discover
    return discover.add_source(a.name, a.sector, a.careers_url, segment=a.segment, country=a.country,
                               write=not a.dry_run)


def main(argv=None):
    p = argparse.ArgumentParser(prog="jobradar", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch all sources, update history, build dashboard, send digest")
    r.add_argument("--only", nargs="*", help="source keys/names to run (default: all)")
    r.add_argument("--no-verify", action="store_true")
    r.add_argument("--no-digest", action="store_true")
    r.add_argument("--no-claude", action="store_true", help="skip optional Claude scoring")
    r.add_argument("--refresh", action="store_true", help="re-read every posting's details")
    r.add_argument("--dashboard-url", default=None)
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("doctor", help="run every source live and print a health table (no writes)")
    d.add_argument("--only", nargs="*")
    d.set_defaults(fn=cmd_doctor)
    v = sub.add_parser("verify", help="re-check a random sample of relevant postings live")
    v.add_argument("--sample", type=int, default=20)
    v.add_argument("--seed", type=int, default=None)
    v.set_defaults(fn=cmd_verify)
    e = sub.add_parser("export", help="write jobs.xlsx and jobs.csv with the full history")
    e.set_defaults(fn=cmd_export)
    sub.add_parser("dashboard", help="rebuild site/index.html from the database").set_defaults(fn=cmd_dashboard)
    g = sub.add_parser("digest", help="build and send the digest from the database")
    g.add_argument("--dashboard-url", default=None)
    g.set_defaults(fn=cmd_digest)
    s = sub.add_parser("add-source", help="detect the hiring system behind a careers page and add it to sources.yaml")
    s.add_argument("name")
    s.add_argument("--sector", choices=["sports", "wealth"], required=True)
    s.add_argument("--careers-url", required=True)
    s.add_argument("--segment", default="")
    s.add_argument("--country", default="")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_add_source)
    a = p.parse_args(argv)
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
