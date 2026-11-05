"""Check that each external service answers with the values in .env."""

import sys
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import env, n8n_base_url

TIMEOUT = 15


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
    resp.raise_for_status()
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


CHECKS = {"n8n": check_n8n}


def main() -> int:
    failed = 0
    for name, check in CHECKS.items():
        try:
            check()
        except (RuntimeError, httpx.HTTPError) as exc:
            print(f"{name} FAILED: {exc}")
            failed += 1
        else:
            print(f"{name} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
