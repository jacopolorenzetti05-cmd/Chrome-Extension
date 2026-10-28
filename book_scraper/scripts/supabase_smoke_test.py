"""Steps 3 + 4: prove we can talk to Supabase before pointing the scraper at it.

    python scripts/supabase_smoke_test.py

1. Write one row into `connection_test`, read it back by id, check it matches, delete it.
2. Check every scraper table exists and is reachable with the configured key.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.supabase_client import SupabaseClient, SupabaseError  # noqa: E402

TABLES = ("categories", "books", "scrape_runs", "book_snapshots")


def main() -> int:
    try:
        client = SupabaseClient.from_env()
    except SupabaseError as exc:
        print(f"FAIL config: {exc}")
        return 1

    message = f"smoke-test {uuid.uuid4()}"
    try:
        written = client.insert("connection_test", [{"message": message}])[0]
        print(f"ok   write: connection_test id={written['id']} message={written['message']!r}")

        read = client.select("connection_test", id=f"eq.{written['id']}")
        assert len(read) == 1 and read[0]["message"] == message, f"read back {read!r}"
        print(f"ok   read:  got the same row back (created_at={read[0]['created_at']})")

        client.delete("connection_test", id=f"eq.{written['id']}")
        print("ok   cleanup: test row deleted")

        for table in TABLES:
            client.select(table, limit="1")
            print(f"ok   table: {table}")
    except (SupabaseError, AssertionError) as exc:
        print(f"FAIL {exc}")
        print("hint: has db/schema.sql been run in the Supabase SQL editor? "
              "Is the key the service_role key (or are RLS policies set)?")
        return 1

    print("Supabase connection OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
