"""Send data/leads.jsonl to the n8n webhook and log every answer to data/send_log.csv.

At most 2 requests per second, and each request waits for its answer, so a
duplicate is never in flight at the same time as its original.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, n8n_base_url

DATA_DIR = ROOT / "data"
LOG_FILE = DATA_DIR / "send_log.csv"
PER_SECOND = 2


def load_leads(only: str | None, limit: int | None) -> list[dict]:
    lines = (DATA_DIR / "leads.jsonl").read_text(encoding="utf-8").splitlines()
    leads = [json.loads(line) for line in lines if line.strip()]
    if only:
        column = {"duplicates": "is_duplicate", "junk": "is_junk"}[only]
        with open(DATA_DIR / "expected.csv", newline="", encoding="utf-8") as fh:
            keep = {
                r["submission_id"] for r in csv.DictReader(fh) if r[column] == "true"
            }
        leads = [lead for lead in leads if lead["submission_id"] in keep]
    return leads[:limit] if limit else leads


def send(client: httpx.Client, url: str, lead: dict) -> tuple[int, str, float]:
    """Return HTTP status (0 if it never got an answer), the flow's status and ms."""
    start = time.perf_counter()
    try:
        resp = client.post(url, json=lead)
    except httpx.HTTPError as exc:
        return 0, f"no answer: {exc}", (time.perf_counter() - start) * 1000
    ms = (time.perf_counter() - start) * 1000
    try:
        status = resp.json().get("status", "")
    except ValueError:
        status = resp.text[:80]
    return resp.status_code, status, ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Send synthetic leads to the webhook.")
    parser.add_argument("--limit", type=int, help="send only the first N leads")
    parser.add_argument("--only", choices=["duplicates", "junk"])
    args = parser.parse_args()

    leads = load_leads(args.only, args.limit)
    url = f"{n8n_base_url()}/webhook/lead-intake"
    answers: Counter = Counter()
    times = []
    new_file = not LOG_FILE.exists()
    with (
        httpx.Client(timeout=90) as client,
        open(LOG_FILE, "a", newline="", encoding="utf-8") as fh,
    ):
        log = csv.writer(fh)
        if new_file:
            log.writerow(["sent_at", "submission_id", "http_status", "status", "ms"])
        for i, lead in enumerate(leads, 1):
            started = time.monotonic()
            sent_at = datetime.now(UTC).isoformat(timespec="seconds")
            code, status, ms = send(client, url, lead)
            log.writerow([sent_at, lead["submission_id"], code, status, round(ms)])
            fh.flush()
            answers[f"{code} {status}"] += 1
            times.append(ms)
            print(f"{i}/{len(leads)} {code} {status} {ms:.0f} ms", flush=True)
            time.sleep(max(0.0, 1 / PER_SECOND - (time.monotonic() - started)))

    print("answers: " + ", ".join(f"{k} x{v}" for k, v in answers.most_common()))
    if times:
        print(f"median response time: {statistics.median(times):.0f} ms")


if __name__ == "__main__":
    main()
