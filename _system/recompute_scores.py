#!/usr/bin/env python3
"""
RUNBOOK Step 4 — Recompute Days Idle and Priority Score.
Deterministic score formula per SCHEMA.md:
  score = stage_pts + gehalt_pts + akt_pts + lane_pts + (boost // 2)
  Closed stage always has score = 0.
"""
import argparse, csv, datetime, os, sys
from datetime import date
import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))

STAGE_PTS = {'Watchlist': 5, 'Applied': 20, 'Screening': 45, 'Interviewing': 65, 'Final': 85, 'Closed': 0}
GEHALT_PTS = {'above': 10, 'around': 5, 'below': -15}
LANE_BONUS = {'Data/AI Arch', 'IT Leadership', 'Transformation'}


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def compute_days_idle(last_event, reference_date):
    d = parse_date(last_event)
    if d is None:
        return None
    return max(0, (reference_date - d).days)


def compute_score(stage, salary_fit, days_idle, lane, boost):
    stage_str = (stage or '').strip()
    if stage_str == 'Closed':
        return 0
    stage_pts = STAGE_PTS.get(stage_str, 0)
    gehalt_pts = GEHALT_PTS.get((salary_fit or '').strip(), 0)
    if days_idle is None:
        akt = 0
    elif days_idle <= 7:
        akt = 10
    elif days_idle <= 14:
        akt = 5
    elif days_idle <= 30:
        akt = 0
    elif days_idle <= 60:
        akt = -10
    else:
        akt = -20
    lane_pts = 5 if (lane or '').strip() in LANE_BONUS else 0
    try:
        b = int(boost) if boost not in (None, '') else 0
    except ValueError:
        b = 0
    boost_pts = b // 2
    total = stage_pts + gehalt_pts + akt + lane_pts + boost_pts
    return max(0, min(100, total))


def main():
    ap = argparse.ArgumentParser(description="Recompute days_idle and score in pipeline.csv")
    ap.add_argument("pos_pipeline", nargs="?", default=None, help="Optional positional path to pipeline.csv")
    ap.add_argument("--pipeline", default=None, help="Path to pipeline.csv")
    ap.add_argument("--today", default=None, help="Reference date YYYY-MM-DD (defaults to today)")
    ap.add_argument("--render", action="store_true", help="refresh the HTML pages afterwards")
    args = ap.parse_args()

    pipeline_path = args.pipeline or args.pos_pipeline or os.path.join(HERE, "pipeline.csv")
    
    if args.today:
        try:
            today_date = datetime.date.fromisoformat(args.today)
        except ValueError:
            print(f"⚠️ Invalid date '{args.today}', falling back to current date.", file=sys.stderr)
            today_date = date.today()
    else:
        today_date = date.today()

    if not os.path.exists(pipeline_path):
        print(f"❌ File not found: {pipeline_path}", file=sys.stderr)
        sys.exit(1)

    with open(pipeline_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    changes = []
    for r in rows:
        old_days = r.get('days_idle', '')
        old_score = r.get('score', '')
        di = compute_days_idle(r.get('last_event'), today_date)
        new_days = str(di) if di is not None else ''
        sc = compute_score(r.get('stage'), r.get('salary_fit'), di, r.get('lane'), r.get('boost'))
        new_score = str(sc)
        if new_days != (old_days or '') or new_score != (old_score or ''):
            changes.append((r.get('uid'), r.get('company'), old_days, new_days, old_score, new_score))
        r['days_idle'] = new_days
        r['score'] = new_score

    with open(pipeline_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {len(rows)} rows for reference date {today_date.isoformat()}. {len(changes)} had a days_idle/score change.")
    for c in changes[:20]:
        print(f"  [uid {c[0]}] {c[1]}: days {c[2]}->{c[3]}, score {c[4]}->{c[5]}")
    if len(changes) > 20:
        print(f"  ... and {len(changes) - 20} more.")

    if args.render:
        import subprocess
        system = os.path.dirname(os.path.abspath(pipeline_path))
        root = os.path.dirname(system)
        cmd = [sys.executable, kit_run.script_path(system, "render"), "--data", pipeline_path,
               "--prep", os.path.join(system, "prep.json"), "--folders", os.path.join(system, "folders.tsv"),
               "--today", today_date.isoformat(), "--out", root]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ! render.py fehlgeschlagen (Code {r.returncode}): {(r.stderr or '').strip()[-400:]}", file=sys.stderr)
            sys.exit(2)
        print("  Seiten aktualisiert")


if __name__ == "__main__":
    main()
