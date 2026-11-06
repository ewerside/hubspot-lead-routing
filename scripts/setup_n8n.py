"""Create this project's n8n credentials from .env and save their ids.

The ids go to config/n8n.json, which deploy_n8n.py reads. Secrets go from .env
straight to the n8n API and are never printed or written anywhere else.
"""

import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIG_DIR, env, n8n_base_url


def checked(resp: httpx.Response) -> httpx.Response:
    if resp.status_code >= 400:
        raise RuntimeError(
            f"{resp.request.method} {resp.request.url.path} answered "
            f"{resp.status_code}: {resp.text[:300]}"
        )
    return resp


def supabase_data() -> dict:
    url = urlsplit(env("DATABASE_URL"))
    return {
        "host": url.hostname,
        "port": url.port or 5432,
        "database": url.path.lstrip("/") or "postgres",
        "user": unquote(url.username or ""),
        "password": unquote(url.password or ""),
        "ssl": "require",
        "allowUnauthorizedCerts": False,
        "sshTunnel": False,
    }


def header_auth(header: str, value: str, domain: str) -> dict:
    # Limiting the domain means n8n refuses to send this secret anywhere else.
    return {
        "name": header,
        "value": value,
        "allowedHttpRequestDomains": "domains",
        "allowedDomains": domain,
    }


def wanted_credentials() -> dict[str, dict]:
    # Not "portfolio HubSpot" etc.: another portfolio project on this n8n already
    # uses "portfolio Anthropic" and "portfolio Supabase".
    return {
        "hubspot": {
            "name": "portfolio lead-routing HubSpot",
            "type": "httpHeaderAuth",
            "data": header_auth(
                "Authorization", f"Bearer {env('HUBSPOT_TOKEN')}", "api.hubapi.com"
            ),
        },
        "anthropic": {
            "name": "portfolio lead-routing Anthropic",
            "type": "httpHeaderAuth",
            "data": header_auth(
                "x-api-key", env("ANTHROPIC_API_KEY"), "api.anthropic.com"
            ),
        },
        "supabase": {
            "name": "portfolio lead-routing Supabase",
            "type": "postgres",
            "data": supabase_data(),
        },
    }


def existing_credentials(client: httpx.Client) -> dict[str, dict]:
    found, cursor = {}, None
    while True:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        body = checked(client.get("/credentials", params=params)).json()
        found.update({c["name"]: c for c in body["data"]})
        cursor = body.get("nextCursor")
        if not cursor:
            return found


def main() -> None:
    headers = {"X-N8N-API-KEY": env("N8N_API_KEY")}
    saved = {}
    try:
        with httpx.Client(
            base_url=f"{n8n_base_url()}/api/v1", headers=headers, timeout=20
        ) as client:
            existing = existing_credentials(client)
            for key, cred in wanted_credentials().items():
                current = existing.get(cred["name"])
                if current and current["type"] != cred["type"]:
                    raise RuntimeError(
                        f"'{cred['name']}' exists with type {current['type']}, "
                        f"expected {cred['type']}"
                    )
                status = "already there"
                if not current:
                    current = checked(client.post("/credentials", json=cred)).json()
                    status = "created"
                saved[key] = {"id": current["id"], "name": current["name"]}
                print(f"{current['name']}: {status} ({current['id']})")
    except (RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"setup_n8n failed: {exc}") from None

    CONFIG_DIR.mkdir(exist_ok=True)
    out = {"credentials": saved}
    (CONFIG_DIR / "n8n.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote config/n8n.json")


if __name__ == "__main__":
    main()
