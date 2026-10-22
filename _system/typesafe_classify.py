#!/usr/bin/env python3
"""
TypeSafe email classification for RUNBOOK Step 2.

Usage (CLI):
    python3 typesafe_classify.py "<subject>" "<body_snippet>"
    → JSON: {"signal": "closed_rejected", "confidence": 0.92}
    → JSON: {"error": "TYPESAFE_API_KEY not set"}

Usage (module):
    from typesafe_classify import classify_email, STAGE_MAP, CONFIDENCE_HIGH, CONFIDENCE_LOW
"""
import json, os, sys, urllib.request
from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
CONFIDENCE_HIGH = 0.75   # accept silently
CONFIDENCE_LOW  = 0.65   # accept but flag; below → UNKLAR

STAGE_MAP = {
    "applied":          {"stage": "Applied",       "outcome": None},
    "screening":        {"stage": "Screening",     "outcome": None},
    "interviewing":     {"stage": "Interviewing",  "outcome": None},
    "final":            {"stage": "Final",         "outcome": None},
    "closed_rejected":  {"stage": "Closed",        "outcome": "rejected"},
    "closed_withdrawn": {"stage": "Closed",        "outcome": "withdrawn"},
    "closed_declined":  {"stage": "Closed",        "outcome": "declined"},
    "closed_signed":    {"stage": "Closed",        "outcome": "signed"},
    "no_match":         None,
}

_CRITERIA = {
    "applied":          "ATS acknowledgement, Eingangsbestätigung, application received",
    "screening":        "HR/recruiter follow-up, availability request, phone call proposed, Terminvorschlag",
    "interviewing":     "Interview invitation with confirmed date or named panel",
    "final":            "Final round, C-Level, contract or salary discussion, Angebot",
    "closed_rejected":  "Rejection — leider, Absage, nicht berücksichtigen, anderweitig besetzt, not proceed",
    "closed_withdrawn": "Candidate withdrawal confirmed by the employer system",
    "closed_declined":  "Candidate declined a received offer",
    "closed_signed":    "Contract signed, start date confirmed",
    "no_match":         "Newsletter, job alert, unrelated, or no recognisable recruitment signal",
}


def classify_email(subject: str, body_snippet: str) -> dict:
    """
    Classify a recruitment email thread via TypeSafe Choice.

    Returns:
        {"signal": str, "confidence": float}   on success
        {"error": str}                          on failure
    """
    api_key = get_typesafe_api_key()
    if not api_key:
        return {"error": "TYPESAFE_API_KEY not set"}

    state = f"{subject}\n{body_snippet}"[:800]
    payload = json.dumps({
        "state": state,
        "model": "jev-latest",
        "questions": {
            "signal": {
                "type": "choice",
                "instructions": "Classify this recruitment email by its strongest signal. One answer only.",
                "criteria": _CRITERIA,
            }
        }
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            log_call("classify_fallback", data)
            s = data["answers"]["signal"]
            return {"signal": s["choice"], "confidence": s["confidence"]}
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    subject = sys.argv[1] if len(sys.argv) > 1 else ""
    body    = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(classify_email(subject, body)))
