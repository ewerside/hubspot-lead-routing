"""Publish the workflows in n8n/ with real ids and secrets filled in.

The JSON in the repo has markers like {{SLACK_WEBHOOK_URL}}. They are filled in
memory and sent to the n8n API; the filled JSON is never written to disk.
"""

import json
import re
import sys
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIG_DIR, ROOT, env, n8n_base_url

# The error workflow goes first so the intake workflow can point to its id.
WORKFLOWS = ["lead-errors.json", "lead-intake.json"]
MARKER = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def checked(resp: httpx.Response) -> httpx.Response:
    if resp.status_code >= 400:
        raise RuntimeError(
            f"{resp.request.method} {resp.request.url.path} answered "
            f"{resp.status_code}: {resp.text[:300]}"
        )
    return resp


def marker_values() -> dict[str, str]:
    try:
        hubspot = json.loads((CONFIG_DIR / "hubspot.json").read_text(encoding="utf-8"))
        creds = json.loads((CONFIG_DIR / "n8n.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"{exc.filename} is missing. Run setup_hubspot.py and setup_n8n.py first."
        ) from None
    creds = creds["credentials"]
    return {
        "SLACK_WEBHOOK_URL": env("SLACK_WEBHOOK_URL"),
        "HUBSPOT_PORTAL_ID": env("HUBSPOT_PORTAL_ID"),
        "LLM_MODEL": env("LLM_MODEL"),
        "PIPELINE_ID": hubspot["pipeline_id"],
        "STAGE_ID": hubspot["stage_id"],
        "OWNER_ID": hubspot["owner_id"],
        "CRED_HUBSPOT": creds["hubspot"]["id"],
        "CRED_ANTHROPIC": creds["anthropic"]["id"],
        "CRED_SUPABASE": creds["supabase"]["id"],
    }


def fill(text: str, values: dict[str, str]) -> dict:
    for key, value in values.items():
        # Values land inside JSON strings, so escape them the way JSON would.
        text = text.replace("{{" + key + "}}", json.dumps(value)[1:-1])
    missing = sorted(set(MARKER.findall(text)))
    if missing:
        raise RuntimeError(f"no value for {', '.join(missing)}")
    return json.loads(text)


def find_workflow(client: httpx.Client, name: str) -> str | None:
    ids, cursor = [], None
    while True:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        body = checked(client.get("/workflows", params=params)).json()
        ids += [w["id"] for w in body["data"] if w["name"] == name]
        cursor = body.get("nextCursor")
        if not cursor:
            break
    if len(ids) > 1:
        raise RuntimeError(f"{len(ids)} workflows are named '{name}'. Keep one.")
    return ids[0] if ids else None


def publish(client: httpx.Client, workflow: dict) -> str:
    body = {k: workflow[k] for k in ("name", "nodes", "connections", "settings")}
    wf_id = find_workflow(client, workflow["name"])
    if wf_id:
        checked(client.put(f"/workflows/{wf_id}", json=body))
        status = "updated"
    else:
        wf_id = checked(client.post("/workflows", json=body)).json()["id"]
        status = "created"
    # A workflow with only an Error Trigger runs without being active.
    if any(n["type"] == "n8n-nodes-base.webhook" for n in workflow["nodes"]):
        checked(client.post(f"/workflows/{wf_id}/activate"))
        status += ", active"
    print(f"{workflow['name']}: {status} ({wf_id})")
    return wf_id


def main() -> None:
    base = n8n_base_url()
    headers = {"X-N8N-API-KEY": env("N8N_API_KEY")}
    try:
        values = marker_values()
        with httpx.Client(
            base_url=f"{base}/api/v1", headers=headers, timeout=30
        ) as client:
            for filename in WORKFLOWS:
                text = (ROOT / "n8n" / filename).read_text(encoding="utf-8")
                wf_id = publish(client, fill(text, values))
                if filename == "lead-errors.json":
                    values["ERROR_WORKFLOW_ID"] = wf_id
    except (RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"deploy_n8n failed: {exc}") from None
    print(f"webhook: {base}/webhook/lead-intake")


if __name__ == "__main__":
    main()
