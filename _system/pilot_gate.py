#!/usr/bin/env python3
"""Evaluate the pilot gate (spec §5) from the weekly reports and the closing answers. Says what is open instead of guessing.

    python3 _system/pilot_gate.py --reports reports_dir --answers answers.json [--max-cost-per-cockpit 0.5]

reports_dir has one sub-folder per pilot with that pilot's pilot_report_*.json files; answers.json is
{"pilot": {"helped": true, "would_pay_eur": 2.99}}.
"""
import argparse
import glob
import json
import math
import os
import sys

MIN_PILOTS = 4
PAY_EUR = 2.99


def _cost(reports):
    for r in reports:
        cost = (r or {}).get("estimated_ai_cost_by_document_type") or {}
        if cost.get("calibrated") and isinstance(cost.get("cockpit"), (int, float)):
            return cost["cockpit"]
    return None


def _complete(ans):
    return isinstance(ans, dict) and isinstance(ans.get("helped"), bool) and isinstance(ans.get("would_pay_eur"), (int, float)) and not isinstance(ans.get("would_pay_eur"), bool)


def evaluate(reports_by_pilot, answers, max_cost_per_cockpit=None):
    n = len(reports_by_pilot)
    active = helped = would_pay = 0
    costs = []
    for pilot, reports in reports_by_pilot.items():
        first_two = (reports or [])[:2]
        if sum((r.get("cockpits_created") or 0) for r in first_two) >= 2:
            active += 1
        ans = (answers or {}).get(pilot) or {}
        if ans.get("helped") is True:
            helped += 1
        pay = ans.get("would_pay_eur")
        if isinstance(pay, (int, float)) and pay >= PAY_EUR:
            would_pay += 1
        c = _cost(reports or [])
        if c is not None:
            costs.append(c)
    needed = max(3, int(math.ceil(0.6 * n))) if n else 3
    cost_ok = None
    if max_cost_per_cockpit is not None and costs:
        cost_ok = all(c < max_cost_per_cockpit for c in costs)
    no_answers = [p for p in reports_by_pilot if not _complete((answers or {}).get(p))]
    short_reports = [p for p, r in reports_by_pilot.items() if len(r or []) < 2]
    out = {"pilots": n, "active": active, "helped": helped, "would_pay": would_pay, "needed": needed, "cost_ok": cost_ok, "go": None, "reason": ""}
    if n < MIN_PILOTS:
        out["reason"] = "zu wenige Piloten (%d, mindestens %d)" % (n, MIN_PILOTS)
    elif no_answers:
        out["reason"] = "offen: Antworten fehlen von %d Piloten" % len(no_answers)
    elif short_reports:
        out["reason"] = "offen: weniger als zwei Berichte von %d Piloten" % len(short_reports)
    elif max_cost_per_cockpit is None:
        out["reason"] = "Kostenschwelle offen: erst Messläufe, dann Schwelle festlegen"
    elif cost_ok is None:
        out["reason"] = "keine kalibrierten Kosten in den Berichten"
    else:
        misses = [label for label, value in (("Nutzung", active), ("Hilfe im Gespräch", helped), ("Zahlungsbereitschaft", would_pay)) if value < needed]
        if not cost_ok:
            misses.append("Kosten je Cockpit über der Schwelle")
        out["go"] = not misses
        out["reason"] = "alle Kriterien erfüllt" if not misses else "nicht erfüllt: " + ", ".join(misses).replace("Zahlungsbereitschaft", "zahlen (Zahlungsbereitschaft)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evaluate the pilot gate.")
    ap.add_argument("--reports", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--max-cost-per-cockpit", type=float, default=None)
    a = ap.parse_args(argv)
    reports = {}
    for sub in sorted(glob.glob(os.path.join(a.reports, "*"))):
        if os.path.isdir(sub):
            files = sorted(glob.glob(os.path.join(sub, "pilot_report_*.json")))
            reports[os.path.basename(sub)] = [json.load(open(f, encoding="utf-8")) for f in files]
    with open(a.answers, encoding="utf-8") as f:
        answers = json.load(f)
    print(json.dumps(evaluate(reports, answers, a.max_cost_per_cockpit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
