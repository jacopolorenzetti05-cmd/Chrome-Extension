"""One-shot Supabase setup, so nobody has to click through the dashboard.

Needs two environment variables (or lines in .env):
    SUPABASE_ACCESS_TOKEN  personal access token  (supabase.com/dashboard/account/tokens)
    SUPABASE_PROJECT_REF   project id, the 'xxxx' in https://xxxx.supabase.co

    python scripts/setup_supabase.py                 # create tables, write .env, test connection
    python scripts/setup_supabase.py --scrape 40     # ...then scrape 40 books into Supabase
    python scripts/setup_supabase.py --scrape all    # ...or the whole site

Steps:
1. Run db/schema.sql on the project (Supabase Management API).
2. Fetch the project's service key and write SUPABASE_URL + key to .env.
3. Run scripts/supabase_smoke_test.py (write one row, read it back, check tables).
4. Optionally run the scraper, then print row counts.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.supabase_client import _load_dotenv  # noqa: E402

API = "https://api.supabase.com/v1"

COUNTS_SQL = """
select 'categories' as table_name, count(*) as rows from categories
union all select 'books', count(*) from books
union all select 'scrape_runs', count(*) from scrape_runs
union all select 'book_snapshots', count(*) from book_snapshots
"""


class SetupError(RuntimeError):
    pass


def management(method: str, path: str, token: str, **kwargs):
    resp = requests.request(method, f"{API}{path}", timeout=60,
                            headers={"Authorization": f"Bearer {token}"}, **kwargs)
    if resp.status_code >= 400:
        raise SetupError(f"{method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json() if resp.content else None


def run_sql(ref: str, token: str, sql: str):
    return management("POST", f"/projects/{ref}/database/query", token, json={"query": sql})


def service_key(ref: str, token: str) -> str:
    keys = management("GET", f"/projects/{ref}/api-keys", token, params={"reveal": "true"})
    for k in keys:  # prefer the legacy service_role key, then a new-style secret key
        if k.get("name") == "service_role" and k.get("api_key"):
            return k["api_key"]
    for k in keys:
        if k.get("type") == "secret" and k.get("api_key"):
            return k["api_key"]
    raise SetupError("no service_role or secret key found on the project")


def write_env(url: str, key: str) -> None:
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    keep = [l for l in lines if not l.startswith(("SUPABASE_URL=", "SUPABASE_SERVICE_ROLE_KEY="))]
    keep += [f"SUPABASE_URL={url}", f"SUPABASE_SERVICE_ROLE_KEY={key}"]
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    os.environ["SUPABASE_URL"] = url
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = key


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        raise SetupError(f"command failed: {' '.join(cmd)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scrape", metavar="N|all", help="after setup, scrape N books (or all)")
    args = ap.parse_args()

    os.chdir(ROOT)
    _load_dotenv()
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    ref = os.environ.get("SUPABASE_PROJECT_REF")
    if not token or not ref:
        print("Set SUPABASE_ACCESS_TOKEN and SUPABASE_PROJECT_REF (environment or .env).")
        return 1
    ref = ref.strip().removeprefix("https://").split(".")[0]  # accept a full URL too
    url = f"https://{ref}.supabase.co"

    try:
        print(f"1/4 creating tables on project {ref} ...")
        run_sql(ref, token, (ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        print("    ok")

        print("2/4 fetching service key and writing .env ...")
        write_env(url, service_key(ref, token))
        print("    ok (.env is git-ignored)")

        print("3/4 testing the connection ...")
        run([sys.executable, "scripts/supabase_smoke_test.py"])

        if args.scrape:
            print("4/4 scraping into Supabase ...")
            cmd = [sys.executable, "scrape.py", "--sink", "supabase"]
            if args.scrape != "all":
                cmd += ["--limit", str(int(args.scrape))]
            run(cmd)
        else:
            print("4/4 skipped scraping (add --scrape 40 or --scrape all)")

        print("\nRows in Supabase now:")
        for row in run_sql(ref, token, COUNTS_SQL):
            print(f"    {row['table_name']:<15} {row['rows']}")
    except (SetupError, requests.RequestException) as exc:
        print(f"FAIL {exc}")
        return 1

    print(f"\nDone. Dashboard: https://supabase.com/dashboard/project/{ref}/editor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
