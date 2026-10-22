#!/usr/bin/env python3
"""
digest.py — tracker → vault synthesis digest

Reads _system/pipeline.csv + transitions.csv and writes a firewall-safe digest
into the vault at career/bridge/from-tracker/YYYY-MM-DD-digest.md.

FIREWALL (career/CAREER.md): the columns `note`, `contacts` and `location` are
read for AGGREGATION ONLY and are never emitted. No verbatim prose, no contact
details, no correspondence crosses this boundary — only counts and patterns.

The tracker leads; the vault follows. This script never writes to the tracker.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import pathlib
import re
import sys

STAGES = ["Watchlist", "Applied", "Screening", "Interviewing", "Final", "Closed"]
LIVE_STAGES = STAGES[:-1]
SCHEMA_LANES = {"Data/AI Arch", "IT Leadership", "Transformation",
                "Public", "Operations", "Executive", "Other"}
NEVER_EMIT = ("note", "contacts", "location")

# Signals that a closed pursuit reached a human conversation. Used to COUNT only.
REACHED_HUMAN = re.compile(
    r"\b(gespr[aä]ch|interview|telefonat|call|termin|panel|runde|screening|"
    r"kennenlernen|vorstellung|recruiter)\b", re.I)
REACHED_LATE = re.compile(
    r"\b(endrunde|final|vertrag|angebot|onboarding|gehalt|zweitgespr|runde 2|"
    r"2\. runde|c-level|vorstand|geschäftsführ)\b", re.I)


def clean_company(v: str) -> str:
    """Strip person-names that leaked into the company field (firewall)."""
    v = re.sub(r"\s*\((?:via|über|durch)[^)]*\)", "", v, flags=re.I)
    v = re.sub(r"\s*[—–-]\s*(?:network signal|warm channel)[^,]*", "", v, flags=re.I)
    return v.strip(" ,-–—") or "(unnamed)"


def pct(n: int, d: int) -> str:
    return "n/a" if not d else f"{100*n/d:.0f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default=str(pathlib.Path(__file__).resolve().parent))
    ap.add_argument("--vault", default=str(pathlib.Path.home() / "notes-vault"))
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    a = ap.parse_args()

    sysdir, vault = pathlib.Path(a.system), pathlib.Path(a.vault)
    today = dt.date.fromisoformat(a.today)

    pipeline = sysdir / "pipeline.csv"
    if not pipeline.exists():
        print(f"digest: {pipeline} not found", file=sys.stderr)
        return 2
    rows = list(csv.DictReader(pipeline.open(newline="", encoding="utf-8")))
    if not rows:
        print("digest: pipeline.csv is empty", file=sys.stderr)
        return 2

    transitions = []
    tpath = sysdir / "transitions.csv"
    if tpath.exists():
        transitions = list(csv.DictReader(tpath.open(newline="", encoding="utf-8")))

    openr = [r for r in rows if r["stage"].strip() != "Closed"]
    closed = [r for r in rows if r["stage"].strip() == "Closed"]

    # --- freshness ----------------------------------------------------------
    drift = []
    for r in rows:
        try:
            d = dt.date.fromisoformat(r["last_event"].strip()[:10])
            drift.append((today - d).days - int(r["days_idle"]))
        except Exception:
            pass
    median_drift = sorted(drift)[len(drift)//2] if drift else 0
    src_date = dt.date.fromtimestamp(pipeline.stat().st_mtime).isoformat()

    # --- lane performance ---------------------------------------------------
    lane_stats = {}
    for r in rows:
        lane = r["lane"].strip() or "(blank)"
        st = lane_stats.setdefault(lane, {"n": 0, "open": 0, "human": 0, "late": 0})
        st["n"] += 1
        if r["stage"].strip() != "Closed":
            st["open"] += 1
        note = r.get("note", "")
        stage = r["stage"].strip()
        if stage in ("Screening", "Interviewing", "Final") or REACHED_HUMAN.search(note):
            st["human"] += 1
        if stage in ("Interviewing", "Final") or REACHED_LATE.search(note):
            st["late"] += 1

    # --- decay --------------------------------------------------------------
    buckets = collections.Counter()
    stale_open = []
    for r in openr:
        try:
            idle = int(r["days_idle"]) + max(median_drift, 0)
        except Exception:
            idle = None
        if idle is None:
            buckets["unknown"] += 1
            continue
        b = "≤14 d" if idle <= 14 else "15–30 d" if idle <= 30 else \
            "31–60 d" if idle <= 60 else ">60 d"
        buckets[b] += 1
        if idle > 60:
            stale_open.append((clean_company(r["company"]), r["stage"].strip(), idle))
    stale_open.sort(key=lambda x: -x[2])

    # --- cockpit coverage ---------------------------------------------------
    with_action = sum(1 for r in openr if r["next_action"].strip())
    with_due = sum(1 for r in openr if r["due"].strip())
    with_salary = sum(1 for r in openr if r["salary_fit"].strip())
    with_folder = sum(1 for r in openr if r["folder_id"].strip())

    # --- outcomes -----------------------------------------------------------
    outcomes = collections.Counter(r["outcome"].strip() for r in closed if r["outcome"].strip())
    off_lane = {l: s["n"] for l, s in lane_stats.items() if l not in SCHEMA_LANES and l != "(blank)"}

    # --- counted transitions ------------------------------------------------
    t_uids = {t["uid"] for t in transitions}
    counted = collections.Counter((t["von"], t["nach"]) for t in transitions)

    # --- render -------------------------------------------------------------
    L = []
    w = L.append
    w("---")
    w(f'title: "Tracker Digest {today.isoformat()}"')
    w("type: digest")
    w("tags: [tracker, digest, pipeline]")
    w(f"created: {today.isoformat()}")
    w(f"updated: {today.isoformat()}")
    w("source: _system/pipeline.csv")
    w(f"source_snapshot: {src_date}")
    w("promoted: false")
    w("---")
    w("")
    w(f"# Tracker Digest — {today.isoformat()}")
    w("")
    w(f"> Generated by `_system/digest.py` from `pipeline.csv` ({len(rows)} rows, "
      f"snapshot {src_date}). Aggregates only — `note`, `contacts` and `location` "
      f"are read for counting and never emitted (Career Privacy Firewall).")
    w("")
    w("**State belongs to the tracker.** Nothing here is a stage of record; this is "
      "material for synthesis in `hub/` and `trajectory.md`.")
    w("")

    if median_drift > 1:
        w(f"⚠️ **Stale input.** `days_idle` was last recomputed about **{median_drift} days** "
          f"ago, so every score in the file — and the decay buckets below — are that far "
          f"behind. Idle figures here are drift-corrected; the tracker's own are not.")
        w("")

    w("## Funnel")
    w("")
    w("| Stage | Now |")
    w("|---|---:|")
    dist = collections.Counter(r["stage"].strip() for r in rows)
    for s in STAGES:
        w(f"| {s} | {dist.get(s, 0)} |")
    w(f"| **Total** | **{len(rows)}** |")
    w("")
    live = sum(dist.get(s, 0) for s in ("Screening", "Interviewing", "Final"))
    w(f"- Open: **{len(openr)}** · in conversation right now: **{live}**")
    w(f"- Closed: **{len(closed)}** — " +
      ", ".join(f"{k} {v}" for k, v in outcomes.most_common()))
    w("")

    w("## Lane performance")
    w("")
    w("Reached-human and reached-late are **estimates** derived by keyword over the note "
      "column (counted, never quoted). The tracker stores only the *current* stage, so for "
      "closed pursuits the furthest stage reached is not recorded — see Limits.")
    w("")
    w("| Lane | Rows | Open | Reached human (est.) | Reached late stage (est.) |")
    w("|---|---:|---:|---:|---:|")
    for lane, s in sorted(lane_stats.items(), key=lambda kv: -kv[1]["n"]):
        w(f"| {lane} | {s['n']} | {s['open']} | {s['human']} ({pct(s['human'], s['n'])}) "
          f"| {s['late']} ({pct(s['late'], s['n'])}) |")
    w("")

    w("## Decay — open pursuits by idle time")
    w("")
    w("| Bucket | Count |")
    w("|---|---:|")
    for b in ("≤14 d", "15–30 d", "31–60 d", ">60 d", "unknown"):
        if buckets.get(b):
            w(f"| {b} | {buckets[b]} |")
    w("")
    if stale_open:
        w(f"**{len(stale_open)} open pursuits are past 60 days idle.** The schema defines "
          f"`lapsed` for exactly this and it has been used **{outcomes.get('lapsed', 0)}** time"
          f"{'' if outcomes.get('lapsed', 0) == 1 else 's'}. Each of these is either a close "
          f"that never happened or a follow-up that is owed:")
        w("")
        w("| Company | Stage | Idle (drift-corrected) |")
        w("|---|---|---:|")
        for c, s, i in stale_open[:15]:
            w(f"| {c} | {s} | {i} d |")
        if len(stale_open) > 15:
            w(f"| … {len(stale_open)-15} more | | |")
        w("")

    w("## Cockpit coverage")
    w("")
    w("The Cockpit is driven by `next_action` and `due`. Coverage across the open pipeline:")
    w("")
    w("| Field | Open rows covered | |")
    w("|---|---:|---:|")
    w(f"| `next_action` | {with_action}/{len(openr)} | {pct(with_action, len(openr))} |")
    w(f"| `due` | {with_due}/{len(openr)} | {pct(with_due, len(openr))} |")
    w(f"| `salary_fit` | {with_salary}/{len(openr)} | {pct(with_salary, len(openr))} |")
    w(f"| `folder_id` | {with_folder}/{len(openr)} | {pct(with_folder, len(openr))} |")
    w("")
    w(f"`salary_fit` carries ±15 points in the score formula. With {len(openr)-with_salary} "
      f"of {len(openr)} open rows unset, those pursuits are scored as if salary were neutral.")
    w("")

    w("## Counted stage transitions")
    w("")
    if transitions:
        w(f"`transitions.csv` holds **{len(transitions)}** transitions across "
          f"**{len(t_uids)}** pursuits — the only stage history that survives a close.")
        w("")
        w("| From → To | Counted |")
        w("|---|---:|")
        for (v, n), c in counted.most_common():
            w(f"| {v} → {n} | {c} |")
    else:
        w("`transitions.csv` is empty — no counted stage history exists.")
    w("")

    w("## Limits of this digest")
    w("")
    w("- **Stage history is destroyed on close.** `pipeline.csv` stores current stage only. "
      f"Of {len(closed)} closed pursuits, stage history exists for **{len(t_uids)}**. Lane "
      "conversion above is therefore an estimate, and the real interview rate cannot be "
      "counted until `transitions.csv` is populated on every stage change.")
    if off_lane:
        w(f"- **Off-schema lane values:** {', '.join(f'`{k}` ({v})' for k, v in off_lane.items())}.")
    w(f"- **Derived values are persisted, not computed.** `days_idle` and `score` are stored, "
      f"so they age in place; at this snapshot they are ~{median_drift} days stale.")
    w("- Integrity defects (missing uid, duplicates, over-long notes) are the job of "
      "`career_check.py` and are deliberately not repeated here.")
    w("")

    w("## Questions for synthesis")
    w("")
    w("Answer in `hub/` or `trajectory.md` — not here, and not in the tracker.")
    w("")
    top = sorted(lane_stats.items(), key=lambda kv: -kv[1]["n"])[:3]
    w(f"1. Volume is concentrated in {', '.join(f'**{l}** ({s[chr(110)]})' for l, s in top)}. "
      "Does the reached-human column justify that split, or is effort following familiarity?")
    w(f"2. {len(stale_open)} pursuits are past 60 days with `lapsed` used "
      f"{outcomes.get('lapsed', 0)}×. Is the pipeline genuinely this wide, or is closing overdue? "
      "`CAREER.md` warns that a career/ over ~60 pages means the pipeline is too wide.")
    w("3. `declined` and `signed` are defined in the schema and never used. What would have to "
      "be true for either to appear, and does the thesis reflect that?")
    w("")

    out = "\n".join(L) + "\n"
    if a.stdout:
        print(out)
        return 0

    dest_dir = vault / "career" / "bridge" / "from-tracker"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{today.isoformat()}-digest.md"
        dest.write_text(out, encoding="utf-8")
    except (OSError, PermissionError) as e:
        print(f"digest: could not write to {dest_dir} ({e}), writing to stdout instead:\n", file=sys.stderr)
        print(out)
        return 0

    # firewall assertion: no forbidden column content may appear in the output
    leaked = [c for c in NEVER_EMIT
              if any((r.get(c) or "").strip() and (r.get(c) or "").strip() in out for r in rows)]
    if leaked:
        try:
            dest.unlink()
        except OSError:
            pass
        print(f"digest: ABORTED — firewall breach, {leaked} content found in output",
              file=sys.stderr)
        return 3

    print(f"digest written: {dest}")
    print(f"  {len(rows)} rows · {len(openr)} open · {len(closed)} closed · "
          f"input {median_drift}d stale")
    return 0


if __name__ == "__main__":
    sys.exit(main())
