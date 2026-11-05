"""Check that each external service answers with the values in .env.

Run all checks, or name some: python scripts/check_env.py hubspot slack
"""

import sys
from pathlib import Path

import httpx
import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import env, n8n_base_url

TIMEOUT = 15


def fail_on_status(resp: httpx.Response) -> None:
    # Not raise_for_status(): its message has the URL, and the Slack URL is a secret.
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


def check_n8n() -> None:
    resp = httpx.get(
        f"{n8n_base_url()}/api/v1/workflows",
        params={"limit": 1},
        headers={"X-N8N-API-KEY": env("N8N_API_KEY")},
        timeout=TIMEOUT,
    )
    if resp.status_code == 404:
        raise RuntimeError(
            "public API not found (404). Check N8N_BASE_URL, or set "
            "N8N_PUBLIC_API_DISABLED=false on the server and restart n8n."
        )
    fail_on_status(resp)
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(
            "answered with something that is not JSON. Check N8N_BASE_URL."
        ) from None
    if "data" not in body:
        raise RuntimeError(
            "answered, but not with a workflow list. Check N8N_BASE_URL."
        )


def check_hubspot() -> None:
    resp = httpx.get(
        "https://api.hubapi.com/crm/v3/objects/contacts",
        params={"limit": 1},
        headers={"Authorization": f"Bearer {env('HUBSPOT_TOKEN')}"},
        timeout=TIMEOUT,
    )
    fail_on_status(resp)


def check_slack() -> None:
    resp = httpx.post(
        env("SLACK_WEBHOOK_URL"),
        json={"text": "test from lead-routing setup"},
        timeout=TIMEOUT,
    )
    fail_on_status(resp)


def check_supabase() -> None:
    with psycopg.connect(env("DATABASE_URL"), connect_timeout=TIMEOUT) as conn:
        conn.execute("select 1").fetchone()


def check_anthropic() -> None:
    model = env("LLM_MODEL")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": env("ANTHROPIC_API_KEY"),
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "Reply with: ok"}],
        },
        timeout=30,
    )
    if resp.status_code == 404:
        raise RuntimeError(f"model {model} not found. Check the current model names.")
    fail_on_status(resp)


CHECKS = {
    "n8n": check_n8n,
    "hubspot": check_hubspot,
    "slack": check_slack,
    "supabase": check_supabase,
    "anthropic": check_anthropic,
}


def main(names: list[str]) -> int:
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"unknown check: {', '.join(unknown)}. Options: {', '.join(CHECKS)}")
        return 2
    failed = 0
    for name in names or CHECKS:
        try:
            CHECKS[name]()
        except (RuntimeError, httpx.HTTPError, psycopg.Error) as exc:
            print(f"{name} FAILED: {exc}")
            failed += 1
        else:
            print(f"{name} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
