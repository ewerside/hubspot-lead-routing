"""Build docs/report.md and docs/tier_confusion.png from lead_log and the answer key."""

import csv
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import psycopg

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, env

DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
TIERS = ["hot", "warm", "cold"]
# One blue ramp from the chart surface (zero) to dark blue (most leads).
BLUES = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#104281"]
INK, INK_ON_DARK, INK_MUTED = "#0b0b0b", "#fcfcfb", "#52514e"


def load_key() -> dict[str, dict]:
    with open(DATA_DIR / "expected.csv", newline="", encoding="utf-8") as fh:
        return {r["submission_id"]: r for r in csv.DictReader(fh)}


def load_db() -> tuple[list[dict], tuple[int, int]]:
    query = (
        "select submission_id, path, tier, intent, score_source, received_at, alerted_at "
        "from lead_log"
    )
    try:
        with psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn:
            cur = conn.execute(query)
            names = [c.name for c in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
            failed = conn.execute(
                "select count(*), count(replayed_at) from failed_leads"
            ).fetchone()
    except psycopg.Error as exc:
        raise SystemExit(f"report: database error: {exc}") from None
    return rows, failed


def webhook_median_ms() -> float | None:
    """Median of the last full run in data/send_log.csv, if there is one."""
    path = DATA_DIR / "send_log.csv"
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))[-200:]
    return statistics.median(int(r["ms"]) for r in rows) if rows else None


def share(hits: int, total: int) -> str:
    return f"{hits} of {total} ({100 * hits / total:.1f}%)" if total else "none"


def compute(rows: list[dict], key: dict[str, dict], failed: tuple[int, int]) -> dict:
    by_id = {r["submission_id"]: r for r in rows}

    def flagged(column: str) -> list[str]:
        return [s for s, k in key.items() if k[column] == "true"]

    new = [r for r in rows if r["path"] == "new" and r["submission_id"] in key]
    ai = [r for r in new if r["score_source"] == "llm"]

    def tier_ok(r: dict) -> bool:
        return r["tier"] == key[r["submission_id"]]["expected_tier"]

    alerted = [r for r in new if r["alerted_at"]]
    matrix = Counter((key[r["submission_id"]]["expected_tier"], r["tier"]) for r in new)
    return {
        "paths": Counter(r["path"] for r in rows),
        "dups": share(
            sum(
                by_id.get(s, {}).get("path") == "duplicate"
                for s in flagged("is_duplicate")
            ),
            len(flagged("is_duplicate")),
        ),
        "junk": share(
            sum(by_id.get(s, {}).get("path") == "rejected" for s in flagged("is_junk")),
            len(flagged("is_junk")),
        ),
        "tier": share(sum(map(tier_ok, new)), len(new)),
        "tier_ai": share(sum(map(tier_ok, ai)), len(ai)),
        "intent": share(
            sum(r["intent"] == key[r["submission_id"]]["expected_intent"] for r in new),
            len(new),
        ),
        "rule": share(sum(r["score_source"] == "rule" for r in new), len(new)),
        "replayed": f"{failed[1]} of {failed[0]}",
        "hot": sum(r["tier"] == "hot" for r in new),
        "alerted": len(alerted),
        "alert_s": statistics.median(
            (r["alerted_at"] - r["received_at"]).total_seconds() for r in alerted
        )
        if alerted
        else None,
        "webhook_ms": webhook_median_ms(),
        "matrix": [[matrix[(e, a)] for a in TIERS] for e in TIERS],
        "new_count": len(new),
    }


def write_markdown(n: dict) -> None:
    m = n["matrix"]
    matrix_rows = "\n".join(
        f"| {e} | " + " | ".join(str(v) for v in m[i]) + " |"
        for i, e in enumerate(TIERS)
    )
    alert = (
        f"{n['alert_s']:.1f} s over {n['alerted']} alerts"
        if n["alert_s"] is not None
        else "no alerts"
    )
    webhook = (
        f"{n['webhook_ms'] / 1000:.1f} s over the last 200 sends"
        if n["webhook_ms"]
        else "no send log"
    )
    text = f"""# Lead routing test report

Built by `scripts/report.py` on {datetime.now(UTC):%Y-%m-%d} from `lead_log` and `data/expected.csv`. 200 synthetic leads went through the n8n flow.

## Paths

| Path | Leads |
| --- | --- |
| new | {n["paths"]["new"]} |
| duplicate | {n["paths"]["duplicate"]} |
| rejected | {n["paths"]["rejected"]} |

- Duplicates blocked: {n["dups"]}.
- Junk rejected: {n["junk"]}.
- Leads queued after a failure and replayed: {n["replayed"]}.

## Scoring

- Tier matches the answer key: {n["tier"]}.
- Tier matches when the AI scored the lead: {n["tier_ai"]}.
- Intent matches the answer key: {n["intent"]}.
- Scored by the fallback rule: {n["rule"]}.

Rows are the answer key, columns are what the flow decided:

| Answer key | hot | warm | cold |
| --- | --- | --- | --- |
{matrix_rows}

![Tier confusion matrix](tier_confusion.png)

## Speed

- Median time from the webhook to the Slack alert: {alert}.
- Median webhook response: {webhook}.
- Hot leads: {n["hot"]}, alerts sent: {n["alerted"]}.
"""
    (DOCS_DIR / "report.md").write_text(text, encoding="utf-8")


def plot(matrix: list[list[int]], total: int) -> None:
    fig, ax = plt.subplots(figsize=(4.8, 4.2), dpi=150)
    fig.patch.set_facecolor(BLUES[0])
    peak = max(max(row) for row in matrix) or 1
    ax.imshow(
        matrix,
        cmap=LinearSegmentedColormap.from_list("blues", BLUES),
        vmin=0,
        vmax=peak,
    )
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            color = INK_ON_DARK if value > peak * 0.55 else INK
            ax.text(
                j, i, str(value), ha="center", va="center", fontsize=13, color=color
            )
    ax.set_xticks(range(3), TIERS)
    ax.set_yticks(range(3), TIERS)
    ax.set_xlabel("Tier from the flow", color=INK_MUTED)
    ax.set_ylabel("Tier in the answer key", color=INK_MUTED)
    ax.set_title(
        f"Tier, answer key vs flow ({total} new leads)", color=INK, fontsize=11, pad=10
    )
    ax.tick_params(colors=INK_MUTED, length=0)
    # Thin gaps in the surface color between cells.
    ax.set_xticks([-0.5, 0.5, 1.5, 2.5], minor=True)
    ax.set_yticks([-0.5, 0.5, 1.5, 2.5], minor=True)
    ax.grid(which="minor", color=BLUES[0], linewidth=3)
    ax.tick_params(which="minor", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(DOCS_DIR / "tier_confusion.png", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    rows, failed = load_db()
    numbers = compute(rows, load_key(), failed)
    DOCS_DIR.mkdir(exist_ok=True)
    write_markdown(numbers)
    plot(numbers["matrix"], numbers["new_count"])
    print(f"paths {dict(numbers['paths'])}")
    print(
        f"duplicates blocked {numbers['dups']}, junk rejected {numbers['junk']}, replayed {numbers['replayed']}"
    )
    print(
        f"tier {numbers['tier']}, tier with AI {numbers['tier_ai']}, intent {numbers['intent']}"
    )
    print(
        f"fallback rule {numbers['rule']}, hot {numbers['hot']}, alerts {numbers['alerted']}"
    )
    if numbers["alert_s"] is not None:
        print(f"median webhook to alert {numbers['alert_s']:.1f} s")
    if numbers["webhook_ms"]:
        print(f"median webhook response {numbers['webhook_ms']:.0f} ms")
    print("wrote docs/report.md and docs/tier_confusion.png")


if __name__ == "__main__":
    main()
