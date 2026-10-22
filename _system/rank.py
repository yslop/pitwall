#!/usr/bin/env python3
"""
Top-10 ranking (Phase 3b): which rows deserve the free Top-10 places, with the reason.

Candidates are rows at Watchlist or Applied (not Closed, not a headhunter channel, not excluded). Each gets a score 0-100 from what is known about it:
  base      30 %  the pipeline's own score (0-100)
  fit       30 %  Jev's fit for the posting (ts_fit_score 0-1; from pipeline.csv or rank_state.json); unknown = neutral 0.5, reason says so
  coverage  20 %  share of must-haves proven (coverage_state.json); unknown = neutral 0.5
  lane      10 %  the row's lane against the target lanes of your profile (Data/AI, IT leadership, transformation, executive)
  momentum  10 %  Watchlist = 1.0; Applied: recent 0.8, older 0.5, stale 0.2 (an old application is less actionable)
Your pins (own finds) always come first; the ranking only proposes fillers for the free places (`rank_state.json`, never `top10.json`).
`--score-missing` asks Jev (fit_score.py) for rows without a fit: the posting text, else the role title alone (never notes or names), at most --limit CALLS per run (capped at 20),
never for pinned, excluded or channel rows; failures are reported, not retried the same day, and never block.

    python3 rank.py [--score-missing --limit 8] [--dry-run]
"""
import argparse
import csv
import datetime
import json
import os
import sys

import coverage as C
import top10 as T

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = {"base": 0.30, "fit": 0.30, "coverage": 0.20, "lane": 0.10, "momentum": 0.10}
TARGET_LANES = {"data/ai arch", "it leadership", "transformation", "executive"}
CANDIDATE_STAGES = ("Watchlist", "Applied")
NEUTRAL = 0.5


def _num(v, lo=0.0, hi=1.0):
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f if f == f and lo <= f <= hi else None


def lane_value(lane):
    l = (lane or "").strip().lower()
    return 1.0 if l in TARGET_LANES else 0.2 if l in ("", "other", "public", "operations") else 0.4


def momentum_value(stage, idle):
    if stage == "Watchlist":
        return 1.0
    d = _num(idle, 0, 100000)
    if d is None:
        return NEUTRAL                                                                    # unknown idle time: neither good nor bad
    return 0.8 if d <= 14 else 0.5 if d <= 45 else 0.2


def score_row(row, fit, share):
    """(score 0-100, parts dict, reasons list) for one row; unknown inputs are neutral and named in the reasons."""
    base = _num(row.get("score"), 0, 100)
    parts = {"base": (base / 100.0) if base is not None else NEUTRAL, "fit": fit if fit is not None else NEUTRAL, "coverage": share if share is not None else NEUTRAL,
             "lane": lane_value(row.get("lane")), "momentum": momentum_value(row.get("stage"), row.get("days_idle"))}
    score = round(100 * sum(WEIGHTS[k] * parts[k] for k in WEIGHTS))
    reasons = []
    reasons.append("Fit %d %%" % round(100 * fit) if fit is not None else "Fit noch nicht bewertet")
    reasons.append("Abdeckung %d %%" % round(100 * share) if share is not None else "Abdeckung offen")
    reasons.append("Lane %s" % (row.get("lane") or "?"))
    reasons.append(row.get("stage") or "")
    return score, {k: round(v, 2) for k, v in parts.items()}, [r for r in reasons if r]


def rank_rows(rows, top, fit_state=None, coverage=None, channels=None):
    """Ranked candidates [{uid, company, role, stage, score, parts, reasons, unrated}] best first. Pinned uids are left out (they are already placed);
    excluded uids, channels and closed rows never appear."""
    top = top if isinstance(top, dict) else {}
    skip = set(T._uids(top.get("pinned"))) | set(T._uids(top.get("excluded"))) | set(T._uids(list(channels) if isinstance(channels, (set, list, dict, tuple)) else []))
    fit_state = fit_state if isinstance(fit_state, dict) else {}
    coverage = coverage if isinstance(coverage, dict) else {}
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("stage") not in CANDIDATE_STAGES:
            continue
        uid = C.norm_uid(r.get("uid"))
        if not uid.isdigit() or int(uid) in skip or uid in seen:
            continue
        seen.add(uid)
        own_fit = _num(r.get("ts_fit_score"))
        st = fit_state.get(uid) if isinstance(fit_state.get(uid), dict) else {}
        fit = own_fit if own_fit is not None else _num(st.get("ts_fit_score"))
        cov = coverage.get(uid) if isinstance(coverage.get(uid), dict) else {}
        share = _num(cov.get("share"))
        score, parts, reasons = score_row(r, fit, share)
        if fit is not None and own_fit is None and st.get("basis") == "titel":
            reasons[0] += " (nur Titel)"
        out.append({"uid": uid, "company": (r.get("company") or "")[:60], "role": (r.get("role") or "")[:80], "stage": r.get("stage"), "score": score,
                    "parts": parts, "reasons": reasons, "unrated": fit is None})
    out.sort(key=lambda x: (-x["score"], int(x["uid"])))
    return out


def suggestions(ranked, top, slots=T.SLOTS):
    """The ranked rows that fill the places your pins leave free."""
    free = max(0, slots - len((top or {}).get("pinned") or []))
    return ranked[:free]


STALE_FIT_DAYS = 45
FAIL_KEEP_DAYS = 7


def _age_days(then, today):
    try:
        return (datetime.date.fromisoformat(str(today)) - datetime.date.fromisoformat(str(then))).days
    except ValueError:
        return 0


def score_missing(rows, system, today, limit=8, scorer=None, skip=None, failed=None, order=None):
    """Ask Jev for the fit of candidate rows without one: posting text from jd_cache.json, else the role title alone (never notes or names). At most `limit` CALLS
    (failures count), never for skipped rows (pinned, excluded, channels), a row that failed today is not retried today, a title-only fit is redone when the posting
    text arrives, and a fit older than 45 days is asked again. Returns ({uid: {ts_fit_score, salary_fit, date, basis}}, problems); `failed` (uid -> date) is updated in place."""
    if scorer is None:
        from fit_score import score_opportunity as scorer
    skip = skip or set()
    failed = failed if isinstance(failed, dict) else {}
    cache = C._read_json(os.path.join(system, "jd_cache.json"), {})
    state = C._read_state(os.path.join(system, "rank_state.json"))
    done = state.get("fit") if isinstance(state.get("fit"), dict) else {}
    new, problems, attempts, seen = {}, [], 0, set()
    if order:                                                                             # the most promising rows first: they get the limited calls
        pos = {u: i for i, u in enumerate(order)}
        rows = sorted(rows, key=lambda r: pos.get(C.norm_uid(r.get("uid")), len(pos)))
    for r in rows:
        if attempts >= limit:
            break
        uid = C.norm_uid(r.get("uid"))
        if uid in seen or not uid.isdigit() or int(uid) in skip or r.get("stage") not in CANDIDATE_STAGES or _num(r.get("ts_fit_score")) is not None:
            continue
        seen.add(uid)
        jd = next((v for k, v in cache.items() if C.norm_uid(k) == uid), "")
        basis = "text"
        if not isinstance(jd, str) or not jd.strip():                                   # no posting text: judge the title alone, and say so
            jd, basis = (r.get("role") or "").strip(), "titel"
            if len(jd) < 8:
                continue
        prev = done.get(uid) if isinstance(done.get(uid), dict) else None
        if prev and not ((prev.get("basis") == "titel" and basis == "text") or _age_days(prev.get("date"), today) > STALE_FIT_DAYS):
            continue
        if failed.get(uid) == today:
            continue
        attempts += 1
        try:
            res = scorer(r.get("role") or "", r.get("company") or "", jd, "")
        except Exception as exc:                                                        # a slow or broken Jev never stops the run
            res = {"error": "%s: %s" % (type(exc).__name__, exc)}
        if isinstance(res, dict) and "error" not in res and _num(res.get("ts_fit_score")) is not None:
            new[uid] = {"ts_fit_score": res["ts_fit_score"], "salary_fit": res.get("salary_fit", ""), "date": today, "basis": basis}
            failed.pop(uid, None)
        else:
            failed[uid] = today
            problems.append("uid %s: %s" % (uid, (res or {}).get("error", "keine Bewertung") if isinstance(res, dict) else "keine Bewertung"))
    return new, problems


def run(system, today, do_score=False, limit=8, dry_run=False, scorer=None):
    """Rank, optionally score missing fits with Jev, write rank_state.json. Returns the state dict (with 'problems')."""
    try:
        with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return {"error": "pipeline.csv: %s" % exc}
    top = T.load(os.path.join(system, "top10.json"))
    coverage = C._read_json(os.path.join(system, "coverage_state.json"), {})
    chans = C._read_json(os.path.join(system, "channels.json"), {}).get("channels")
    channels = {k for k in chans} if isinstance(chans, dict) else set()
    channels = {int(k) for k in channels if str(k).strip().isdigit()}
    prev = C._read_state(os.path.join(system, "rank_state.json"))
    fit = dict(prev.get("fit")) if isinstance(prev.get("fit"), dict) else {}
    problems = []
    failed = {k: v for k, v in (prev.get("failed") or {}).items() if isinstance(prev.get("failed"), dict) and _age_days(v, today) <= FAIL_KEEP_DAYS}
    if do_score and not dry_run:                                                          # a dry run makes no Jev calls
        skip = set(T._uids(top.get("pinned"))) | set(T._uids(top.get("excluded"))) | channels
        order = [x["uid"] for x in rank_rows(rows, top, fit, coverage, channels)]
        new, problems = score_missing(rows, system, today, limit, scorer, skip, failed, order)
        fit.update(new)
    ranked = rank_rows(rows, top, fit, coverage, channels)
    state = {"date": today, "slots": T.SLOTS, "pinned": top["pinned"], "ranked": ranked[:25], "suggested": [x["uid"] for x in suggestions(ranked, top)], "fit": fit, "failed": failed}
    if not dry_run:
        C._write_atomic(os.path.join(system, "rank_state.json"), json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True))
    state["problems"] = problems
    return state


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rank Watchlist and Applied rows for the free Top-10 places.")
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--today", default=None)
    ap.add_argument("--score-missing", action="store_true", help="ask Jev for the fit of rows that have posting text but no fit yet")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    st = run(a.system, a.today or datetime.date.today().isoformat(), a.score_missing, max(0, min(a.limit, 20)), a.dry_run)
    if "error" in st:
        print("rank: " + st["error"], file=sys.stderr)
        return 1
    print("rank: %d Kandidaten, %d Vorschläge für die restlichen %d Fokus-Plätze" % (len(st["ranked"]), len(st["suggested"]), max(0, st["slots"] - len(st["pinned"]))))
    for x in st["ranked"][:len(st["suggested"])]:
        print("  %3d  uid %-4s %s · %s (%s) — %s" % (x["score"], x["uid"], x["company"], x["role"][:40], x["stage"], ", ".join(x["reasons"][:3])))
    for p in st["problems"]:
        print("  ! Jev-Bewertung fehlgeschlagen, %s" % p, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
