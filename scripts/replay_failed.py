"""Resend every queued lead that was not replayed yet, then mark it as replayed.

If a lead fails again, the flow queues it as a new row, so nothing is lost. A lead
that already failed MAX_TRIES times is left in the queue for a person to look at.
"""

import sys
from collections import Counter
from pathlib import Path

import httpx
import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import env, n8n_base_url

# A lead HubSpot rejects for good (bad data, not an outage) would otherwise loop forever.
MAX_TRIES = 3


def flow_status(resp: httpx.Response) -> str:
    try:
        return resp.json().get("status", "")
    except ValueError:
        return resp.text[:80]


def main() -> int:
    url = f"{n8n_base_url()}/webhook/lead-intake"
    answers: Counter = Counter()
    try:
        with (
            psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn,
            httpx.Client(timeout=90) as client,
        ):
            rows = conn.execute(
                "select f.id, f.submission_id, f.payload, "
                "(select count(*) from failed_leads g where g.submission_id = f.submission_id) "
                "from failed_leads f where f.replayed_at is null order by f.id"
            ).fetchall()
            for row_id, submission_id, payload, tries in rows:
                if tries >= MAX_TRIES:
                    print(f"{submission_id}: failed {tries} times, check failed_leads")
                    answers["left for a person"] += 1
                    continue
                try:
                    resp = client.post(url, json=payload)
                except httpx.HTTPError as exc:
                    print(f"{submission_id}: not sent, will retry next run ({exc})")
                    answers["not sent"] += 1
                    continue
                status = flow_status(resp)
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
        return 0
    print("replayed: " + ", ".join(f"{k} x{v}" for k, v in answers.most_common()))
    done = sum(v for k, v in answers.items() if k.startswith("200 "))
    return 0 if done == sum(answers.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
