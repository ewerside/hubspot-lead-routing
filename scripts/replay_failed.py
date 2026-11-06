"""Resend every queued lead that was not replayed yet, then mark it as replayed.

If a lead fails again, the flow queues it as a new row, so nothing is lost.
"""

import sys
from collections import Counter
from pathlib import Path

import httpx
import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import env, n8n_base_url


def main() -> None:
    url = f"{n8n_base_url()}/webhook/lead-intake"
    answers: Counter = Counter()
    try:
        with (
            psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn,
            httpx.Client(timeout=90) as client,
        ):
            rows = conn.execute(
                "select id, submission_id, payload from failed_leads "
                "where replayed_at is null order by id"
            ).fetchall()
            for row_id, submission_id, payload in rows:
                try:
                    resp = client.post(url, json=payload)
                except httpx.HTTPError as exc:
                    print(f"{submission_id}: not sent, will retry next run ({exc})")
                    answers["not sent"] += 1
                    continue
                status = resp.json().get("status", "") if resp.content else ""
                print(f"{submission_id}: {resp.status_code} {status}")
                answers[f"{resp.status_code} {status}"] += 1
                if resp.is_success:
                    conn.execute(
                        "update failed_leads set replayed_at = now() where id = %s",
                        (row_id,),
                    )
                    conn.commit()
    except psycopg.Error as exc:
        raise SystemExit(f"replay_failed: database error: {exc}") from None

    if not answers:
        print("nothing to replay")
        return
    print("replayed: " + ", ".join(f"{k} x{v}" for k, v in answers.most_common()))
    if answers["202 queued"]:
        print("some leads failed again and are back in the queue")


if __name__ == "__main__":
    main()
