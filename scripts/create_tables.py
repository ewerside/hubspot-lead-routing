"""Create the lead_log and failed_leads tables from sql/schema.sql."""

import sys
from pathlib import Path

import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, env

SCHEMA_FILE = ROOT / "sql" / "schema.sql"


def main() -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    try:
        with psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn:
            conn.execute(sql)
            schema = conn.execute("select current_schema()").fetchone()[0]
            tables = conn.execute(
                "select table_name from information_schema.tables "
                "where table_schema = current_schema() order by table_name"
            ).fetchall()
    except psycopg.Error as exc:
        raise SystemExit(f"create_tables failed: {exc}") from None
    print(f"schema {schema}: {', '.join(t[0] for t in tables)}")


if __name__ == "__main__":
    main()
