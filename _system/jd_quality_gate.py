#!/usr/bin/env python3
"""
RUNBOOK Step 4c.5 — JD Quality Gate (Top-3 candidates only).
TypeSafe Score across 3 dimensions, gating prep effort on posting quality.

CLI:
    python3 jd_quality_gate.py "<role>" "<company>" "<jd_text>"
    → JSON: {"overall": 0.62, "pass": false, "dimensions": {...}}
"""
import json, os, sys, urllib.request
from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

_WEIGHTS = {
    "clarity": 0.4,
    "requirements_realism": 0.3,
    "compensation_transparency": 0.3,
}
_PASS_THRESHOLD = 0.7

_QUESTIONS = {
    "clarity": {
        "type": "score",
        "instructions": "How clearly and coherently is this job posting structured?",
        "criteria": [
            "Rambling or contradictory; role and responsibilities are unclear",
            "Basic structure but vague; responsibilities and requirements blend together",
            "Clearly organized into sections (role, responsibilities, requirements)",
            "Crisp and specific; a candidate could summarize the day-to-day after one read",
        ],
    },
    "requirements_realism": {
        "type": "score",
        "instructions": "How realistic are the stated requirements for the role's seniority and compensation level?",
        "criteria": [
            "Contradictory or absurd requirements for the role/level",
            "Long, unfocused wishlist presented as hard requirements",
            "Mostly appropriate for the seniority/comp level, with a few negotiable asks",
            "Tightly scoped to what's truly necessary, consistent with seniority and comp",
        ],
    },
    "compensation_transparency": {
        "type": "score",
        "instructions": "How transparent is the posting about compensation and logistics?",
        "criteria": [
            "No salary info, no work-arrangement or logistics stated at all",
            "Vague or partial (e.g. 'competitive salary'; work arrangement unclear)",
            "Salary range and work arrangement given, but missing other logistics",
            "Full salary range, benefits, and logistics (remote policy, sponsorship) stated",
        ],
    },
}


def score_jd(role: str, company: str, jd_text: str) -> dict:
    """
    Score a job posting across 3 TypeSafe dimensions.

    Returns:
        {"overall": float, "pass": bool, "dimensions": {...}}
        {"error": str}   on failure
    """
    api_key = get_typesafe_api_key()
    if not api_key:
        return {"error": "TYPESAFE_API_KEY not set"}

    state = json.dumps({"role": role, "company": company, "jd_text": jd_text[:4000]})
    payload = json.dumps({
        "state": state,
        "model": "jev-latest",
        "questions": _QUESTIONS,
    }).encode()

    req = urllib.request.Request(
        TYPESAFE_URL,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            log_call("jd_quality_gate", data)
        answers = data["answers"]
        dims = {k: round(answers[k]["score"] / 3, 4) for k in _QUESTIONS}
    except Exception as exc:
        return {"error": str(exc)}

    overall = round(sum(_WEIGHTS[k] * dims[k] for k in _WEIGHTS), 4)
    return {
        "overall": overall,
        "pass": overall >= _PASS_THRESHOLD,
        "dimensions": dims,
    }


if __name__ == "__main__":
    role    = sys.argv[1] if len(sys.argv) > 1 else ""
    company = sys.argv[2] if len(sys.argv) > 2 else ""
    jd      = sys.argv[3] if len(sys.argv) > 3 else ""
    print(json.dumps(score_jd(role, company, jd), indent=2))
