"""Create the lead_* contact properties and save pipeline, stage and owner ids.

The ids go to config/hubspot.json, which deploy_n8n.py reads later.
"""

import json
import sys
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIG_DIR, env

API = "https://api.hubapi.com"
GROUP = "contactinformation"
TIERS = ["hot", "warm", "cold"]
INTENTS = [
    "demo_request",
    "pricing",
    "support_existing_customer",
    "partnership",
    "job_seeker",
    "spam",
]


def options(values: list[str]) -> list[dict]:
    return [
        {"label": v.replace("_", " ").capitalize(), "value": v, "displayOrder": i}
        for i, v in enumerate(values)
    ]


PROPERTIES = [
    {
        "name": "lead_score",
        "label": "Lead score",
        "type": "number",
        "fieldType": "number",
        "description": "0 to 100, from the AI or the fallback rule.",
    },
    {
        "name": "lead_tier",
        "label": "Lead tier",
        "type": "enumeration",
        "fieldType": "select",
        "options": options(TIERS),
    },
    {
        "name": "lead_intent",
        "label": "Lead intent",
        "type": "enumeration",
        "fieldType": "select",
        "options": options(INTENTS),
    },
    {
        "name": "lead_reason",
        "label": "Lead reason",
        "type": "string",
        "fieldType": "textarea",
        "description": "One sentence on why the lead got this score.",
    },
    {
        "name": "lead_submission_id",
        "label": "Lead submission id",
        "type": "string",
        "fieldType": "text",
        "description": "Last form submission seen for this contact.",
    },
]


def checked(resp: httpx.Response) -> httpx.Response:
    if resp.status_code >= 400:
        raise RuntimeError(
            f"{resp.request.method} {resp.request.url.path} answered "
            f"{resp.status_code}: {resp.text[:300]}"
        )
    return resp


def ensure_property(client: httpx.Client, prop: dict) -> bool:
    """Create the property if it is missing. Return True if it was created."""
    resp = client.get(f"/crm/v3/properties/contacts/{prop['name']}")
    if resp.status_code == 200:
        return False
    if resp.status_code != 404:
        checked(resp)
    checked(
        client.post("/crm/v3/properties/contacts", json={**prop, "groupName": GROUP})
    )
    return True


def default_pipeline(client: httpx.Client) -> tuple[dict, dict]:
    """Return the default deal pipeline and its first stage."""
    pipelines = checked(client.get("/crm/v3/pipelines/deals")).json()["results"]
    pipeline = next((p for p in pipelines if p["id"] == "default"), None)
    if pipeline is None:
        names = ", ".join(f"{p['label']} ({p['id']})" for p in pipelines)
        raise RuntimeError(f"no pipeline with id 'default'. Found: {names}")
    stage = min(pipeline["stages"], key=lambda s: s["displayOrder"])
    return pipeline, stage


def only_owner(client: httpx.Client) -> dict:
    # A developer test account has one user, the person who created it.
    owners = checked(client.get("/crm/v3/owners", params={"limit": 100})).json()[
        "results"
    ]
    if len(owners) != 1:
        names = ", ".join(
            f"{o.get('firstName')} {o.get('lastName')} ({o['id']})" for o in owners
        )
        raise RuntimeError(
            f"expected one owner, found {len(owners)}: {names or 'none'}"
        )
    return owners[0]


def main() -> None:
    headers = {"Authorization": f"Bearer {env('HUBSPOT_TOKEN')}"}
    try:
        with httpx.Client(base_url=API, headers=headers, timeout=20) as client:
            for prop in PROPERTIES:
                created = ensure_property(client, prop)
                print(
                    f"property {prop['name']}: {'created' if created else 'already there'}"
                )
            pipeline, stage = default_pipeline(client)
            owner = only_owner(client)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"setup_hubspot failed: {exc}") from None

    config = {
        "portal_id": env("HUBSPOT_PORTAL_ID"),
        "pipeline_id": pipeline["id"],
        "pipeline_label": pipeline["label"],
        "stage_id": stage["id"],
        "stage_label": stage["label"],
        "owner_id": owner["id"],
        "owner_name": f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip(),
    }
    CONFIG_DIR.mkdir(exist_ok=True)
    (CONFIG_DIR / "hubspot.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"pipeline {pipeline['label']} ({pipeline['id']}), first stage {stage['label']} ({stage['id']})"
    )
    print(f"owner {config['owner_name']} ({owner['id']})")
    print("wrote config/hubspot.json")


if __name__ == "__main__":
    main()
