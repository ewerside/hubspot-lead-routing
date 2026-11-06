"""Export the live workflows back to n8n/, with markers in place of ids and secrets.

Use it after editing a workflow in the n8n editor. It fails if a secret is still
in any JSON file in n8n/ afterwards.
"""

import json
import sys
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIG_DIR, ROOT, env, n8n_base_url

N8N_DIR = ROOT / "n8n"
WORKFLOWS = {
    "portfolio lead errors": "lead-errors.json",
    "portfolio lead intake": "lead-intake.json",
}


def checked(resp: httpx.Response) -> httpx.Response:
    if resp.status_code >= 400:
        raise RuntimeError(
            f"{resp.request.method} {resp.request.url.path} answered "
            f"{resp.status_code}: {resp.text[:300]}"
        )
    return resp


def workflow_ids(client: httpx.Client) -> dict[str, str]:
    found, cursor = {}, None
    while True:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        body = checked(client.get("/workflows", params=params)).json()
        found.update(
            {w["name"]: w["id"] for w in body["data"] if w["name"] in WORKFLOWS}
        )
        cursor = body.get("nextCursor")
        if not cursor:
            return found


def replacements(ids: dict[str, str]) -> list[tuple[str, str]]:
    """(text in the exported JSON, marker). Short values are matched with context."""
    hubspot = json.loads((CONFIG_DIR / "hubspot.json").read_text(encoding="utf-8"))
    creds = json.loads((CONFIG_DIR / "n8n.json").read_text(encoding="utf-8"))
    creds = creds["credentials"]
    return [
        (env("SLACK_WEBHOOK_URL"), "{{SLACK_WEBHOOK_URL}}"),
        (env("HUBSPOT_PORTAL_ID"), "{{HUBSPOT_PORTAL_ID}}"),
        (f"model: '{env('LLM_MODEL')}'", "model: '{{LLM_MODEL}}'"),
        (f"pipeline: '{hubspot['pipeline_id']}'", "pipeline: '{{PIPELINE_ID}}'"),
        (f"dealstage: '{hubspot['stage_id']}'", "dealstage: '{{STAGE_ID}}'"),
        (f"'{hubspot['owner_id']}'", "'{{OWNER_ID}}'"),
        (f'"{creds["hubspot"]["id"]}"', '"{{CRED_HUBSPOT}}"'),
        (f'"{creds["anthropic"]["id"]}"', '"{{CRED_ANTHROPIC}}"'),
        (f'"{creds["supabase"]["id"]}"', '"{{CRED_SUPABASE}}"'),
        (f'"{ids["portfolio lead errors"]}"', '"{{ERROR_WORKFLOW_ID}}"'),
    ]


def secrets_in(text: str) -> list[str]:
    patterns = ["pat-", "sk-ant", "hooks.slack.com", env("HUBSPOT_PORTAL_ID")]
    return [p for p in patterns if p in text]


def main() -> None:
    headers = {"X-N8N-API-KEY": env("N8N_API_KEY")}
    exports = {}
    try:
        with httpx.Client(
            base_url=f"{n8n_base_url()}/api/v1", headers=headers, timeout=30
        ) as client:
            ids = workflow_ids(client)
            missing = set(WORKFLOWS) - set(ids)
            if missing:
                raise RuntimeError(f"not found on n8n: {', '.join(sorted(missing))}")
            swaps = replacements(ids)
            for name, filename in WORKFLOWS.items():
                live = checked(client.get(f"/workflows/{ids[name]}")).json()
                keep = {
                    k: live[k] for k in ("name", "nodes", "connections", "settings")
                }
                text = json.dumps(keep, indent=2, ensure_ascii=False)
                for value, marker in swaps:
                    text = text.replace(value, marker)
                exports[filename] = text
    except (RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"export_n8n failed: {exc}") from None

    # Check before writing: a leaked file in n8n/ is one commit away from the public repo.
    leaks = [f"{f}: {p}" for f, text in exports.items() for p in secrets_in(text)]
    if leaks:
        raise SystemExit("secret found, nothing written: " + "; ".join(leaks))
    for filename, text in exports.items():
        (N8N_DIR / filename).write_text(text + "\n", encoding="utf-8")
        print(f"exported n8n/{filename}")
    print("secret check passed: no token, key, Slack URL or portal id in the export")


if __name__ == "__main__":
    main()
