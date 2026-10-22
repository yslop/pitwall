#!/usr/bin/env python3
"""
RUNBOOK Step 4c — Fit Scoring Engine.
TypeSafe Score across 6 dimensions for newly discovered Watchlist entries.

CLI:
    python3 fit_score.py "<job_title>" "<company>" "<jd_text>" ["<context>"]
    → JSON: {"ts_fit_score": 0.78, "salary_fit": "high", "boost_contribution": 12, "dimensions": {...}}
"""
import json, os, sys, urllib.request
from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

# salary_fit score → 5-value enum (first match wins, top-down)
SALARY_FIT_THRESHOLDS = [
    (0.80, "top"),
    (0.60, "high"),
    (0.40, "mid"),
    (0.20, "stretch"),
    (0.00, "below"),
]

from kit_profile import salary_band as _salary_band
_BAND = _salary_band()

_QUESTIONS = {
    "lane_fit": {
        "type": "score",
        "instructions": (
            "How well does this role match: Data/AI Architecture, IT Leadership, "
            "or Digital Transformation at executive level (own team, own budget)?"
        ),
        "criteria": [
            "No match — unrelated to Data/AI, IT Leadership, or Digital Transformation, "
            "or clearly non-executive with no team or budget",
            "Weak match — adjacent to one of these areas but lacking executive scope "
            "(no own team/budget, or a narrow individual-contributor mandate)",
            "Good match — clearly in one of these areas with meaningful team/budget "
            "ownership, though not full executive authority",
            "Strong match — squarely in Data/AI Architecture, IT Leadership, or Digital "
            "Transformation with full executive-level authority (own team, own budget)",
        ],
    },
    "salary_fit": {
        "type": "score",
        "instructions": _BAND["instructions"],
        "criteria": _BAND["criteria"],
    },
    "stability": {
        "type": "score",
        "instructions": (
            "How financially stable and strategically healthy is this organisation "
            "based on the job posting and company context?"
        ),
        "criteria": [
            "Unstable — signs of financial distress, layoffs, or restructuring",
            "Uncertain — insufficient or mixed signal to judge",
            "Stable — no negative signals, steady operations implied",
            "Strong — explicit signals of growth, investment, or market leadership",
        ],
    },
    "bypass_signal": {
        "type": "score",
        "instructions": (
            "Does the posting suggest a warm-channel entry is likely: named recruiter, "
            "referral hint, or direct application path visible?"
        ),
        "criteria": [
            "No signal — standard portal posting, no named contact or referral hint",
            "Weak signal — generic 'apply now' with minor personalization",
            "Moderate signal — named recruiter or HR contact provided",
            "Strong signal — explicit referral path, named hiring manager, or direct "
            "application encouraged",
        ],
    },
    "scope_fit": {
        "type": "score",
        "instructions": (
            "Does the mandate suggest: own team, own budget, direct C-level or board "
            "reporting line?"
        ),
        "criteria": [
            "No scope — individual contributor, no team or budget ownership implied",
            "Limited scope — some team-lead responsibility but no clear budget "
            "ownership or senior reporting line",
            "Moderate scope — own team and some budget authority, reports to "
            "director/VP level",
            "Full scope — own team, own budget, and direct C-level or board "
            "reporting line",
        ],
    },
    "urgency": {
        "type": "score",
        "instructions": (
            "How actively is this role being filled right now — recently posted, "
            "explicit urgency signals, fast-moving process indicators?"
        ),
        "criteria": [
            "No urgency — no timing signals, could be evergreen or low-priority",
            "Some urgency — recently posted but no explicit timing pressure",
            "Moderate urgency — explicit timeline mentioned or active interviewing",
            "High urgency — explicit urgency language (e.g. 'immediate start') or "
            "fast-moving process indicators",
        ],
    },
}


def _map_salary_fit(score: float) -> str:
    for threshold, label in SALARY_FIT_THRESHOLDS:
        if score >= threshold:
            return label
    return "below"


def score_opportunity(
    job_title: str,
    company: str,
    jd_text: str,
    context: str = "",
) -> dict:
    """
    Score a job opportunity across 6 TypeSafe dimensions.

    Returns:
        {"ts_fit_score": float, "salary_fit": str, "boost_contribution": int, "dimensions": dict}
        {"error": str}   on failure
    """
    api_key = get_typesafe_api_key()
    if not api_key:
        return {"error": "TYPESAFE_API_KEY not set"}

    state_parts = [job_title, company, jd_text[:1500]]
    if context:
        state_parts.append(context[:300])
    state = "\n".join(state_parts)

    payload = json.dumps({
        "state": state,
        "model": "jev-latest",
        "questions": _QUESTIONS,
    }).encode()

    req = urllib.request.Request(
        TYPESAFE_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            log_call("fit_score", data)
        answers = data["answers"]
        # Each question has 4 criteria levels (indices 0-3); normalize the
        # raw 0-3 score to 0-1 so ts_fit_score/salary_fit/boost stay on the
        # scale the rest of this function already assumes.
        dims = {k: round(answers[k]["score"] / 3, 4) for k in _QUESTIONS}
    except Exception as exc:
        return {"error": str(exc)}

    ts_fit = round(sum(dims.values()) / len(dims), 4)
    boost  = min(15, round(ts_fit * 15))

    return {
        "ts_fit_score":       ts_fit,
        "salary_fit":         _map_salary_fit(dims["salary_fit"]),
        "boost_contribution": boost,
        "dimensions":         dims,
    }


if __name__ == "__main__":
    title   = sys.argv[1] if len(sys.argv) > 1 else ""
    company = sys.argv[2] if len(sys.argv) > 2 else ""
    jd      = sys.argv[3] if len(sys.argv) > 3 else ""
    ctx     = sys.argv[4] if len(sys.argv) > 4 else ""
    print(json.dumps(score_opportunity(title, company, jd, ctx), indent=2))
