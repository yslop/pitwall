#!/usr/bin/env python3
"""What the Sync session researches next: the intel work of every process in conversation, ranked, capped per run.

The research itself is done by the Claude session that runs the Sync (RUNBOOK step 3h), not by Python: this module only decides *what* and *in which order*,
so the stage drives the research without a manual trigger. Screening, Interviewing and Final owe work (Applied only on request, owner decision 2026-10-02).

    python3 _system/intel_queue.py [--limit 3] [--json] [--today YYYY-MM-DD] [--data pipeline.csv]

Work items, in the order of one process: `after_interview` (debrief and next version after a conversation), `stage_doc` (the document of the stage:
cheat sheet, briefing, strategy), `prep_content` (Prep_Inhalt.json, prep brief and cockpit of the conversation, once the document exists). Ranking: a date within 3 days first,
then Final, Interviewing, Screening, then the earlier date, then the kind. Python 3.9 compatible. Never writes anything.
"""
import argparse
import csv
import datetime
import json
import os
import sys

import kit_demo
import warranty as W

HERE = os.path.dirname(os.path.abspath(__file__))
TIER = {"Final": 0, "Interviewing": 1, "Screening": 2}
KIND_ORDER = {"after_interview": 0, "stage_doc": 1, "prep_content": 2}
ORDER_PREFIX = {"after_interview": "Nachbereitung_Auftrag_", "stage_doc": "Recherche_Auftrag_", "prep_content": "Prep_Auftrag_"}
DEFAULT_LIMIT = 3


def _prep_needed(p):
    if p["stage"] not in W.PREP_STAGES or not p.get("folder") or not W._has_stage_doc(p):
        return False
    pr, ck = p.get("prep"), p.get("cockpit")
    if not pr or not pr.get("file") or pr.get("gaps") or not pr.get("questions") or not ck or not ck.get("file") or ck.get("gaps"):
        return True
    newest = max((d.get("date") or "" for d in p.get("docs") or [] if d.get("kind") in ("briefing", "strategy")), default="")
    return bool(newest and ((pr.get("date") or "") < newest or (ck.get("date") or "") < newest))


def build_queue(positions, today, limit=None):
    items = []
    for p in positions:
        if p["stage"] not in TIER or kit_demo.is_demo_uid(p["uid"]):
            continue
        base = {"uid": p["uid"], "company": p["company"], "stage": p["stage"], "due": p.get("due")}
        opens = W.open_orders(p)
        for o in opens:
            items.append(dict(base, kind="after_interview" if o.get("after") else "stage_doc", doc=o.get("doc")))
        if not opens and p.get("folder") and not W._has_stage_doc(p):
            items.append(dict(base, kind="stage_doc", doc=None))                      # no order yet: intel_job.py --live writes it first
        if _prep_needed(p):
            items.append(dict(base, kind="prep_content", doc=None))

    def key(i):
        left = W._days_until(i, today) if i.get("due") else None
        urgent = 0 if left is not None and 0 <= left <= W.DEADLINE_DAYS else 1
        return (urgent, TIER[i["stage"]], left if left is not None else 9999, KIND_ORDER[i["kind"]], str(i["uid"]))
    items.sort(key=key)
    total = len(items)
    for i in items:
        i["total"] = total
    return items[:limit] if limit else items


def _order_file(folder, kind):
    try:
        names = sorted((n for n in os.listdir(os.path.join(folder, "20 Vorbereitung")) if n.startswith(ORDER_PREFIX[kind]) and n.endswith(".md")),
                       key=lambda n: os.path.getmtime(os.path.join(folder, "20 Vorbereitung", n)), reverse=True)
    except OSError:
        return None
    return os.path.join(folder, "20 Vorbereitung", names[0]) if names else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ranked intel work for the Sync session.")
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    a = ap.parse_args(argv)
    with open(a.data, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    from folder_utils import locate_role_folder
    positions = W.snapshot(os.path.dirname(os.path.abspath(a.data)), a.base_dir, rows, a.today)
    items = build_queue(positions, a.today, a.limit)
    by_uid = {p["uid"]: p for p in positions}
    for i in items:
        row = next((r for r in rows if W.IJ.C.norm_uid(r.get("uid")) == i["uid"] and (r.get("stage") or "") == i["stage"]), {})
        folder, _ = locate_role_folder(a.base_dir, i["uid"], row.get("role") or "", row.get("folder_id") or "")
        i["order_file"] = _order_file(str(folder), i["kind"]) if folder else None
        i["uid_row_found"] = bool(by_uid.get(i["uid"]))
    if a.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0
    if not items:
        print("intel queue: nothing to research")
        return 0
    print("intel queue: %d of %d work items this run" % (len(items), items[0]["total"]))
    for n, i in enumerate(items, 1):
        print("  %d. uid %s %s (%s)%s · %s%s · %s" % (n, i["uid"], i["company"], i["stage"], " · due " + i["due"] if i.get("due") else "", i["kind"],
                                                    " " + i["doc"] if i.get("doc") else "", os.path.basename(i["order_file"]) if i.get("order_file") else "kein Auftrag: intel_job.py --live"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
