#!/usr/bin/env python3
"""
Browser click chooser (Manifest job-crm.browser_pick).
Jev picks the next element to click from a list of {id, role, label}; the main model judges the
final result. Sends only role and label (capped), never page text. Fails closed.

CLI:
    echo '[{"id":"e1","role":"button","label":"Archiv"}]' | python3 browser_pick.py "<goal>"
    → JSON: {"decision": "click"|"done"|"blocked"|"UNKLAR", "id": "e1", "confidence": 0.9} | {"error": ...}
"""
import json, re, sys, urllib.request
from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
MAX_ELEMENTS = 20
MAX_LABEL = 60
MIN_CONFIDENCE = 0.6


def _clean(label: str) -> str:
    return re.sub(r"\s+", " ", str(label or "")).strip()[:MAX_LABEL]


def _fast_path(goal: str, elements: list):
    """Exactly one label named in the goal: no model call needed."""
    g = goal.lower()
    hits = [e for e in elements if len(_clean(e.get("label"))) >= 3 and _clean(e["label"]).lower() in g]
    return hits[0] if len(hits) == 1 else None


def pick_next(goal: str, elements: list) -> dict:
    """
    Returns {"decision": "click", "id", "confidence"} | {"decision": "done"|"blocked", ...}
    | {"decision": "UNKLAR", "confidence"} | {"error": str}.
    """
    els = [e for e in (elements or []) if isinstance(e, dict) and e.get("id")][:MAX_ELEMENTS]
    hit = _fast_path(goal, els)
    if hit:
        return {"decision": "click", "id": hit["id"], "confidence": 1.0}

    api_key = get_typesafe_api_key()
    if not api_key:
        return {"error": "TYPESAFE_API_KEY not set"}

    criteria = {e["id"]: "%s: %s" % (e.get("role", "element"), _clean(e.get("label"))) for e in els}
    criteria["done"] = "The goal is already reached on this page"
    criteria["blocked"] = "No listed element gets closer to the goal"
    payload = json.dumps({
        "state": "Goal: %s" % _clean(goal)[:200],
        "model": "jev-latest",
        "questions": {"next": {
            "type": "choice",
            "instructions": "Which element should be clicked next to get closer to the goal? One answer only.",
            "criteria": criteria,
        }},
    }).encode()

    req = urllib.request.Request(
        TYPESAFE_URL, data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            log_call("browser_pick", data)
        ans = data["answers"]["next"]
        choice, conf = str(ans["choice"]), float(ans["confidence"])
    except Exception as exc:
        return {"error": str(exc)}

    if choice not in criteria:
        return {"error": "choice %r is not one of the offered elements" % choice}
    if conf < MIN_CONFIDENCE:
        return {"decision": "UNKLAR", "confidence": conf}
    if choice in ("done", "blocked"):
        return {"decision": choice, "confidence": conf}
    return {"decision": "click", "id": choice, "confidence": conf}


if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(pick_next(goal, json.load(sys.stdin)), indent=2))
