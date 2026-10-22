#!/usr/bin/env python3
"""Weekly numbers-only report for a pilot customer. The customer reads it and sends it to the owner.

Only counts, rates and cost estimates; never a company, person or file name and never document text.

    python3 _system/pilot_report.py [--data pipeline.csv] [--base-dir ..] [--today YYYY-MM-DD] [--cost-table cost.json]
"""
import argparse
import csv
import datetime
import glob
import json
import os
import sys

import intel_queue as Q
import kit_demo
import warranty as W

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = ("Watchlist", "Applied", "Screening", "Interviewing", "Final")
DOC_TYPES = ("cheat_sheet", "briefing", "strategy", "cockpit")
FIELDS = ("week", "processes_by_stage", "cockpits_created", "cockpits_current", "lint_pass_rate", "queue_open", "queue_done",
          "usage_days", "estimated_ai_cost_by_document_type")
WINDOW_DAYS = 7


def _day(ts):
    return datetime.date.fromtimestamp(ts)


def _recent(paths, today):
    out = []
    for p in paths:
        try:
            d = _day(os.path.getmtime(p))
        except OSError:
            continue
        if 0 <= (today - d).days < WINDOW_DAYS:
            out.append((p, d))
    return out


def _rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _lint_rate(system_dir):
    try:
        with open(os.path.join(system_dir, "intel_state.json"), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return None
    results = []
    for entry in state.values() if isinstance(state, dict) else []:
        for doc in (entry.get("docs") or {}).values() if isinstance(entry, dict) else []:
            latest = doc.get("latest") if isinstance(doc, dict) else None
            res = ((doc.get("versions") or {}).get(latest) or {}).get("result") if latest else None
            if res in ("pass", "warn", "fail"):
                results.append(res)
    return round(results.count("pass") / float(len(results)), 2) if results else None


def build_report(system_dir, base_dir, today, cost_table=None):
    system_dir, base_dir = os.path.abspath(system_dir), os.path.abspath(base_dir)
    day = datetime.date.fromisoformat(today)
    rows = [r for r in _rows(os.path.join(system_dir, "pipeline.csv")) if not kit_demo.is_demo_row(r)]       # demo processes never count
    by_stage = {}
    for r in rows:
        stage = (r.get("stage") or "").strip()
        if not stage or stage == "Closed":
            continue
        key = stage if stage in STAGES else "Other"
        by_stage[key] = by_stage.get(key, 0) + 1
    voraus = glob.glob(os.path.join(base_dir, "*", "20 Vorbereitung")) + glob.glob(os.path.join(base_dir, "*", "*", "20 Vorbereitung"))
    voraus = [v for v in voraus if "(Demo)" not in v]
    cockpits = [p for v in voraus for p in glob.glob(os.path.join(v, "Cockpit_*.html"))]
    docs = [p for v in voraus for p in glob.glob(os.path.join(v, "*.md")) + glob.glob(os.path.join(v, "*.html")) if not os.path.basename(p).startswith(("Prep_", "JD_", "Cockpit_"))]
    positions = W.snapshot(system_dir, base_dir, rows, today)
    current = sum(1 for p in positions if p.get("cockpit") and p["cockpit"].get("file") and not p["cockpit"].get("gaps"))
    recent_files = _recent([os.path.join(system_dir, "pipeline.csv")] + cockpits + docs, day)
    created = {"cockpit": len(_recent(cockpits, day)), "briefing": len([1 for p, _ in _recent(docs, day) if "riefing" in os.path.basename(p)]),
               "cheat_sheet": len([1 for p, _ in _recent(docs, day) if "heat" in os.path.basename(p)]),
               "strategy": len([1 for p, _ in _recent(docs, day) if "trategy" in os.path.basename(p)])}
    if cost_table:
        cost = {"calibrated": True}
        for t in DOC_TYPES:
            if t in cost_table and isinstance(cost_table[t], (int, float)):
                cost[t] = cost_table[t]
    else:
        cost = {"calibrated": False}
    iso = day.isocalendar()
    return {"week": "%d-W%02d" % (iso[0], iso[1]), "processes_by_stage": by_stage, "cockpits_created": created["cockpit"],
            "cockpits_current": current, "lint_pass_rate": _lint_rate(system_dir), "queue_open": len(Q.build_queue(positions, today)),
            "queue_done": created["briefing"] + created["cheat_sheet"] + created["strategy"], "usage_days": len({d for _, d in recent_files}),
            "estimated_ai_cost_by_document_type": cost}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weekly numbers-only pilot report.")
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--cost-table", default=None, help="JSON {cockpit, briefing, cheat_sheet, strategy: EUR per document}")
    a = ap.parse_args(argv)
    table = None
    if a.cost_table:
        with open(a.cost_table, encoding="utf-8") as f:
            table = json.load(f)
    rep = build_report(os.path.dirname(os.path.abspath(a.data)), a.base_dir, a.today, table)
    out = os.path.join(os.path.dirname(os.path.abspath(a.data)), "pilot_report_%s.json" % rep["week"])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print("Gespeichert: %s (nur Zahlen, ohne Namen; bitte lesen und senden)" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
