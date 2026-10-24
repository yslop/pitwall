#!/usr/bin/env python3
"""Contracts for the external APIs Pitwall depends on, and a daily live smoke test against them.

    python3 _system/api_contract.py --smoke     # 1 TypeSafe call (3 tiny questions) + 1 BA request
    python3 _system/api_contract.py --show      # print the last result

One definition of each response shape (spec: specs/2026-09-27-api-contract-design.md). The tests
build their mocks from it (typesafe_fixture, ba_fixture); the smoke test holds the live APIs against
it (check_*). If the code drifts, a test fails; if an API drifts, the smoke test fails. The failure
of 22.09. (code and mocks sharing one wrong shape) can no longer pass silently.
Writes contract_state.json next to this file; health.py turns it into the check "API contracts".
Never raises: a failed check is a result, not a crash.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _typesafe_env import get_typesafe_api_key  # noqa: E402
from _typesafe_ledger import log_call  # noqa: E402

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
BA_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
BA_HEADERS = {"X-API-Key": "jobboerse-jobsuche", "Accept": "application/json"}
BA_ITEM_FIELDS = ("firma", "stellenangebotsTitel", "referenznummer")
STATE_FILE = "contract_state.json"
NUM = (int, float)

# One question per type, on a state of a few words: the cheapest call that still proves the shape.
SMOKE_STATE = "Kontrakt-Test: Head of Data, Hamburg, eigenes Team."
SMOKE_QUESTIONS = {
    "c": {"type": "choice", "instructions": "Is this a leadership role?",
          "criteria": {"yes": "Leadership role", "no": "Not a leadership role"}},
    "s": {"type": "score", "instructions": "How senior is the role?",
          "criteria": ["Junior", "Senior", "Executive"]},
    "n": {"type": "noul", "instructions": "Does the text name a city?"},
}


def _options(q):
    crit = q.get("criteria")
    return list(crit) if isinstance(crit, (dict, list)) else []


# ---- TypeSafe --------------------------------------------------------------------------------
def check_request(payload):
    """Problems with a TypeSafe request payload; [] when it meets the contract."""
    p = []
    if not isinstance(payload, dict):
        return ["payload is not an object"]
    if not isinstance(payload.get("state"), str) or not payload["state"].strip():
        p.append("state must be a non-empty string")
    if payload.get("model") != MODEL:
        p.append("model must be %r, got %r" % (MODEL, payload.get("model")))
    qs = payload.get("questions")
    if not isinstance(qs, dict) or not qs:
        return p + ["questions must be a non-empty object"]
    for qid, q in qs.items():
        kind = q.get("type") if isinstance(q, dict) else None
        opts = _options(q) if isinstance(q, dict) else []
        if kind == "choice":
            if len(opts) < 2:
                p.append("%s: choice needs at least 2 criteria" % qid)
        elif kind == "score":
            if not isinstance(q.get("criteria"), list) or not 2 <= len(opts) <= 10:
                p.append("%s: score needs a criteria list with 2-10 levels (else HTTP 422)" % qid)
        elif kind == "noul":
            if not str(q.get("instructions") or "").strip():
                p.append("%s: noul needs instructions" % qid)
        else:
            p.append("%s: unknown question type %r" % (qid, kind))
    return p


def check_typesafe_response(data, questions):
    """Problems with a TypeSafe answer for these questions; [] when it meets the contract."""
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        return ["missing 'answers' object (results must sit under data['answers'])"]
    answers, p = data["answers"], []
    for qid, q in questions.items():
        a = answers.get(qid)
        if not isinstance(a, dict):
            p.append("%s: no answer" % qid)
            continue
        kind = q.get("type")
        if kind == "choice":
            opts = [str(o) for o in _options(q)]
            if str(a.get("choice")) not in opts:
                p.append("%s: choice %r is not one of the criteria" % (qid, a.get("choice")))
            if not isinstance(a.get("confidence"), NUM) or not 0 <= a["confidence"] <= 1:
                p.append("%s: confidence missing or outside 0-1" % qid)
        elif kind == "score":
            top = len(_options(q)) - 1
            if not isinstance(a.get("score"), NUM) or not 0 <= a["score"] <= top:
                p.append("%s: score missing or outside 0-%d" % (qid, top))
        elif kind == "noul":
            if not isinstance(a.get("noul"), NUM) or not 0 <= a["noul"] <= 1:
                p.append("%s: noul missing or outside 0-1" % qid)
    return p


def typesafe_fixture(questions, pick=None):
    """A contract-conform answer for these questions (tests build their mocks from this)."""
    pick, answers = pick or {}, {}
    for qid, q in questions.items():
        kind = q.get("type")
        if kind == "choice":
            answers[qid] = {"choice": pick.get(qid, _options(q)[0]), "confidence": 0.9}
        elif kind == "score":
            answers[qid] = {"score": pick.get(qid, len(_options(q)) - 1)}
        elif kind == "noul":
            answers[qid] = {"noul": pick.get(qid, 0.8)}
    return {"model": MODEL, "answers": answers, "usage": {"input_tokens": 42}}


# ---- BA-Jobbörse -----------------------------------------------------------------------------
def check_ba_response(data):
    if not isinstance(data, dict) or not isinstance(data.get("ergebnisliste"), list):
        return ["missing 'ergebnisliste' list"]
    if not data["ergebnisliste"]:
        return ["'ergebnisliste' is empty for a broad query"]
    item = data["ergebnisliste"][0]
    missing = [f for f in BA_ITEM_FIELDS if not str((item or {}).get(f) or "").strip()]
    return ["result item lacks %s" % ", ".join(missing)] if missing else []


def ba_fixture(n=1):
    return {"ergebnisliste": [{"firma": "Muster AG %d" % i, "stellenangebotsTitel": "Head of Data %d" % i,
                               "referenznummer": "10000-%06d-S" % i} for i in range(n)],
            "maxErgebnisse": n}


# ---- live smoke ------------------------------------------------------------------------------
def _typesafe_smoke(api_key, opener):
    if not api_key:
        return {"ok": None, "problems": ["TYPESAFE_API_KEY not set, skipped"]}
    payload = {"state": SMOKE_STATE, "model": MODEL, "questions": SMOKE_QUESTIONS}
    req = urllib.request.Request(TYPESAFE_URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with opener(req, timeout=20) as resp:
            data = json.loads(resp.read())
        log_call("api_contract", data)
    except Exception as exc:
        return {"ok": False, "problems": ["request failed: %s" % exc]}
    problems = check_typesafe_response(data, SMOKE_QUESTIONS)
    return {"ok": not problems, "problems": problems}


def _ba_smoke(opener):
    url = BA_URL + "?" + urllib.parse.urlencode({"was": "Data", "wo": "Deutschland", "page": "1", "size": "1"})
    try:
        with opener(urllib.request.Request(url, headers=BA_HEADERS), timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "problems": ["request failed: %s" % exc]}
    problems = check_ba_response(data)
    return {"ok": not problems, "problems": problems}


def smoke(system_dir, now, api_key=None, opener=None):
    """Run both live checks, write contract_state.json, return the state."""
    if opener is None:
        opener = urllib.request.urlopen
    key = get_typesafe_api_key() if api_key is None else api_key
    state = {"ts": now.isoformat(timespec="seconds"), "typesafe": _typesafe_smoke(key, opener), "ba": _ba_smoke(opener)}
    try:
        with open(os.path.join(system_dir, STATE_FILE), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return state


def render(state):
    lines = ["API contracts %s" % state.get("ts")]
    for name in ("typesafe", "ba"):
        r = state.get(name) or {}
        mark = {True: "OK  ", False: "FAIL", None: "SKIP"}.get(r.get("ok"), "?   ")
        lines.append("  %s %-8s %s" % (mark, name, "; ".join(r.get("problems") or []) or "matches the contract"))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--smoke", action="store_true", help="run the live checks and write contract_state.json")
    ap.add_argument("--show", action="store_true", help="print the last result")
    ap.add_argument("--system-dir", default=None, help="system directory where contract_state.json is read/written")
    args = ap.parse_args(argv)
    system_dir = args.system_dir
    if not system_dir:
        system_dir = "_system" if os.path.isdir("_system") else HERE
    if args.smoke:
        state = smoke(system_dir, datetime.now())
    else:
        try:
            with open(os.path.join(system_dir, STATE_FILE), encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            print("no contract smoke recorded yet")
            return 0
    sys.stdout.write(render(state))
    return 1 if any((state.get(k) or {}).get("ok") is False for k in ("typesafe", "ba")) else 0


if __name__ == "__main__":
    sys.exit(main())
