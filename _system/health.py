#!/usr/bin/env python3
"""Service health of the job-search system -> health.json (+ 60-day health_history.json).

    python3 _system/health.py [--today YYYY-MM-DD] [--now ISO-8601] [--data pipeline.csv] [--quiet]

Ten checks in the ITIL 5 split Warranty / Utility / Continual Improvement. Each is OK, Watch or Act
with a one-line reason; a check that cannot be computed is Act with the error text, never missing.
Reads only. Writes health.json, health_history.json and last_run.json next to this file.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))

OK, WATCH, ACT = "OK", "Watch", "Act"
RANK = {OK: 0, WATCH: 1, ACT: 2}
HISTORY_DAYS = 60
LEDGER_ALLOWED = {"backend", "cost_usd", "input_tokens", "model", "task", "ts"}
PROTECTED = {"Interviewing", "Final"}
FRESH_OK_H, FRESH_WATCH_H = 36, 60      # daily schedule plus jitter (spec: 24 h / 48 h at page-open time)


def _check(cid, group, name, status, reason, target):
    return {"id": cid, "group": group, "name": name, "status": status, "reason": reason, "target": target}


def worst(statuses):
    return max(statuses, key=lambda s: RANK[s], default=OK)


def _age_hours(now, then):
    return (now - then).total_seconds() / 3600.0


def parse_date(text):
    """ISO date (surrounding blanks allowed) or None: anything else (TBD, 01.10.2026, ...) is ignored, never compared as text."""
    try:
        return date.fromisoformat(str(text).strip())
    except (TypeError, ValueError):
        return None


def parse_ts(text):
    """ISO timestamp -> naive local time, so values with an offset or a trailing Z never mix with naive ones."""
    dt = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def _by_age(hours):
    return OK if hours <= FRESH_OK_H else WATCH if hours <= FRESH_WATCH_H else ACT


# ---- the ten checks (pure) -------------------------------------------------------------------
def check_run_freshness(now, prev_run):
    target = "previous run within %d h" % FRESH_OK_H
    if prev_run is None:
        return _check("run_freshness", "warranty", "Availability · run", OK, "first recorded run", target)
    h = _age_hours(now, prev_run)
    return _check("run_freshness", "warranty", "Availability · run", _by_age(h),
                  "previous run %.0f h ago" % h, target)


def check_discovery(now, ran_at, new=None):
    target = "discovery ran within %d h" % FRESH_OK_H
    if ran_at is None:
        return _check("discovery", "warranty", "Continuity · discovery", WATCH, "no discovery run recorded yet", target)
    h = _age_hours(now, ran_at)
    return _check("discovery", "warranty", "Continuity · discovery", _by_age(h),
                  "discovery ran %.0f h ago%s" % (h, "" if new is None else ", %d new" % new), target)


def check_security(env_mode, bad_keys):
    problems = []
    if env_mode is not None and env_mode & 0o077:
        problems.append(".env is readable by group/others (chmod 600)")
    if bad_keys:
        problems.append("ledger holds unexpected fields: " + ", ".join(sorted(bad_keys)))
    return _check("security", "warranty", "Security · secrets and ledger", ACT if problems else OK,
                  "; ".join(problems) if problems else ".env private, ledger holds tokens and cost only",
                  ".env mode 600, ledger fields limited to tokens/cost")


def check_capacity(usage):
    target = "no spike, under 80 % of the monthly ceiling"
    if usage is None:
        return _check("capacity", "warranty", "Capacity · Jev tokens", ACT, "usage report unavailable", target)
    used = usage["month"].get("ceiling_used")
    if usage["spike"]:
        return _check("capacity", "warranty", "Capacity · Jev tokens", ACT, "SPIKE: " + usage["why"], target)
    if used is not None and used >= 1.0:
        status = ACT
    elif used is not None and used >= 0.8:
        status = WATCH
    else:
        status = OK
    reason = "%s tokens this month%s" % (
        format(usage["month"]["input_tokens"], ","), "" if used is None else " (%.1f %% of ceiling)" % (100 * used))
    return _check("capacity", "warranty", "Capacity · Jev tokens", status, reason, target)


def check_api_contract(now, state):
    """Live contract smoke of TypeSafe and BA (api_contract.py, spec 2026-09-27-api-contract-design.md)."""
    target, name = "live contract smoke within %d h, all APIs match" % FRESH_OK_H, "Continuity · API contracts"
    if not state:
        return _check("api_contract", "warranty", name, WATCH, "no contract smoke recorded yet", target)
    try:
        h = _age_hours(now, parse_ts(state["ts"]))
        results = {"TypeSafe": state.get("typesafe") or {}, "BA": state.get("ba") or {}}
    except Exception as exc:
        return _check("api_contract", "warranty", name, ACT, "contract state unreadable: %s" % exc, target)
    broken = ["%s: %s" % (k, "; ".join(r.get("problems") or ["failed"])) for k, r in results.items() if r.get("ok") is False]
    if broken:
        return _check("api_contract", "warranty", name, ACT, " | ".join(broken), target)
    skipped = [k for k, r in results.items() if r.get("ok") is None]
    if skipped:
        return _check("api_contract", "warranty", name, WATCH, "%s not checked (%.0f h ago)" % (", ".join(skipped), h), target)
    return _check("api_contract", "warranty", name, _by_age(h), "TypeSafe and BA match the contract (%.0f h ago)" % h, target)


def check_data_quality(career):
    target = "0 errors, 0 warnings from career_check"
    if career is None or "error" in career:
        return _check("data_quality", "utility", "Data quality", ACT,
                      "check failed: %s" % (career or {}).get("error", "no result"), target)
    e, w = career["errors"], career["warnings"]
    status = ACT if e else WATCH if w else OK
    return _check("data_quality", "utility", "Data quality", status, "%d errors, %d warnings" % (e, w), target)


def _open(rows):
    return [r for r in rows if r.get("stage") != "Closed"]


def _int(x, default=0):
    try:
        return int(float(str(x).strip()))
    except (TypeError, ValueError):
        return default


def check_follow_through(rows, today):
    t = date.fromisoformat(today)
    overdue = [r for r in _open(rows) if (parse_date(r.get("due")) or t) < t]
    n = len(overdue)
    status = OK if n == 0 else WATCH if n <= 3 else ACT
    return _check("follow_through", "utility", "Follow-through · due items", status,
                  "none overdue" if n == 0 else "%d overdue: %s" % (n, ", ".join(
                      "uid %s" % (r.get("uid") or "?") for r in overdue[:5])), "no overdue items")


def check_value_stream(rows):
    live = _open(rows)
    protected = [r for r in live if r.get("stage") in PROTECTED and _int(r.get("days_idle")) > 60]
    stale = [r for r in live if _int(r.get("days_idle")) > 45]
    status = ACT if protected else WATCH if stale else OK
    if protected:
        reason = "protected process idle > 60 d: " + ", ".join("uid %s" % r.get("uid") for r in protected)
    elif stale:
        reason = "%d open rows idle > 45 d" % len(stale)
    else:
        reason = "no open row idle > 45 d"
    return _check("value_stream", "utility", "Value stream · idle rows", status, reason,
                  "no open row idle > 45 d (protected stages > 60 d)")


def check_profile_freshness(reviewed, today):
    target = "capability profile reviewed within 30 d"
    if reviewed is None:
        return _check("profile", "improvement", "Capability profile", WATCH, "no capability_profile.md with a reviewed: date", target)
    age = (date.fromisoformat(today) - reviewed).days
    status = OK if age <= 30 else WATCH if age <= 45 else ACT
    return _check("profile", "improvement", "Capability profile", status, "reviewed %d d ago" % age, target)


def find_problems(history, checks, today):
    """Ids of checks that are not OK today and were not OK on the two previous recorded days either."""
    prior = [h for h in sorted(history, key=lambda h: h["day"]) if h["day"] < today][-2:]
    if len(prior) < 2:
        return []
    return sorted(c["id"] for c in checks
                  if c["status"] != OK and all(h["status"].get(c["id"], OK) != OK for h in prior))


def check_problems(problem_ids):
    n = len(problem_ids)
    status = OK if n == 0 else WATCH if n <= 2 else ACT
    return _check("problems", "improvement", "Recurring problems", status,
                  "none" if n == 0 else "not OK on 3 consecutive days: " + ", ".join(problem_ids),
                  "no check not OK on 3 consecutive days")


def compute_health(*, now, rows, prev_run, discovery_ts, discovery_new, career, usage, env_mode, ledger_bad_keys,
                   profile_reviewed, history, deploy=None, contract=None, intel=None):
    today = now.date().isoformat()
    checks = [
        check_run_freshness(now, prev_run),
        check_discovery(now, discovery_ts, discovery_new),
        check_security(env_mode, ledger_bad_keys),
        check_capacity(usage),
        check_api_contract(now, contract),
        check_data_quality(career),
        check_follow_through(rows, today),
        check_value_stream(rows),
        check_profile_freshness(profile_reviewed, today),
    ]
    if isinstance(intel, dict):             # the snapshot of the intel process could not be built: never silently green
        checks.append(_check("intel_warranty", "warranty", "Quality · intel process", ACT, "cannot be computed: %s" % intel.get("error", "unknown"),
                             "the intel warranty checks run without error"))
    elif isinstance(intel, list):
        import warranty
        checks.extend(warranty.checks(intel, today))
    problem_ids = find_problems(history, checks, today)
    checks.append(check_problems(problem_ids))
    incidents = ["Run gap: %s" % c["reason"] for c in checks if c["id"] == "run_freshness" and c["status"] == ACT]
    return {"generated": now.isoformat(timespec="seconds"), "today": today,
            "overall": worst([c["status"] for c in checks]), "checks": checks,
            "problems": problem_ids, "incidents": incidents, "deploy": deploy}


def update_history(history, today, checks):
    cutoff = (date.fromisoformat(today) - timedelta(days=HISTORY_DAYS - 1)).isoformat()
    kept = [h for h in history if h["day"] != today and h["day"] >= cutoff]
    kept.append({"day": today, "status": {c["id"]: c["status"] for c in checks}})
    return sorted(kept, key=lambda h: h["day"])


# ---- gathering inputs (impure) ----------------------------------------------------------------
def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _safe_ts(text):
    try:
        return parse_ts(text) if text else None
    except ValueError:
        return None


def career_counts(system_dir, data_path, today):
    script = kit_run.script_path(system_dir, "career_check")
    try:
        out = subprocess.run([sys.executable, script, "--data", data_path, "--today", today],
                             capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": str(e)}
    m = re.search(r"(\d+) Fehler · (\d+) Warnungen", out)
    if m:
        return {"errors": int(m.group(1)), "warnings": int(m.group(2))}
    if "sauber" in out:
        return {"errors": 0, "warnings": 0}
    return {"error": "career_check output not understood"}


def read_ledger(system_dir):
    path = os.path.join(system_dir, "logs", "llm_calls.jsonl")
    records, bad = [], set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    records.append(r)
                    bad |= set(r) - LEDGER_ALLOWED
    except OSError:
        pass
    except ValueError as e:
        return records, {"unreadable line (%s)" % e}
    return records, bad


def _first_existing(*paths):
    return next((p for p in paths if os.path.exists(p)), None)


def usage_report(system_dir, today, records):
    """decision_layer usage report, or None if the vendored module cannot be loaded."""
    vendor = _first_existing(os.path.join(system_dir, "vendor"), os.path.join(system_dir, "..", "vendor"))
    gov = _first_existing(os.path.join(system_dir, "decisions", "governance.json"),
                          os.path.join(system_dir, "..", "decisions", "governance.json"))
    try:
        if vendor and vendor not in sys.path:
            sys.path.insert(0, vendor)
        from decision_layer.infrastructure import usage
        ceiling = _read_json(gov, {}).get("budget", {}).get("monthly_usd_ceiling") if gov else None
        return usage.report(records, today, ceiling)
    except Exception:
        return None


def profile_reviewed(system_dir):
    try:
        with open(os.path.join(system_dir, "capability_profile.md"), encoding="utf-8") as f:
            m = re.search(r"^reviewed:\s*(\d{4}-\d{2}-\d{2})", f.read(), re.M)
        return date.fromisoformat(m.group(1)) if m else None
    except (OSError, ValueError):
        return None


def last_events_run(system_dir, now):
    """The last real run: the newest valid `datum` in events.csv (one row per scheduled run) at the end of that day, never later than now; None if unreadable.
    Manual health calls do not count: they used to hide a missed scheduled run."""
    try:
        with open(os.path.join(system_dir, "events.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    for r in reversed(rows):
        d = parse_date(r.get("datum") if isinstance(r, dict) else None)
        if d is not None:
            return min(datetime.combine(d, datetime.max.time()).replace(microsecond=0), now)
    return None


def _intel_snapshot(system_dir, rows, today):
    try:
        import warranty
        return warranty.snapshot(system_dir, os.path.dirname(os.path.abspath(system_dir)), rows, today)
    except Exception as exc:                # reported as an Act check, never swallowed
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def gather(system_dir, data_path, now, career_runner=career_counts):
    today = now.date().isoformat()
    with open(data_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    records, bad = read_ledger(system_dir)
    stamp = _read_json(os.path.join(system_dir, "discovery_last.json"), {})
    env = os.path.join(system_dir, ".env")
    return dict(
        now=now, rows=rows,
        prev_run=last_events_run(system_dir, now) or _safe_ts(_read_json(os.path.join(system_dir, "last_run.json"), {}).get("ts")),
        discovery_ts=_safe_ts(stamp.get("ts")), discovery_new=stamp.get("new") if isinstance(stamp.get("new"), int) else None,
        career=career_runner(system_dir, data_path, today),
        usage=usage_report(system_dir, today, records),
        env_mode=(os.stat(env).st_mode & 0o777) if os.path.exists(env) else None,
        ledger_bad_keys=bad, profile_reviewed=profile_reviewed(system_dir),
        history=_read_json(os.path.join(system_dir, "health_history.json"), []),
        deploy=_read_json(os.path.join(system_dir, "deployed.json"), None),
        contract=_read_json(os.path.join(system_dir, "contract_state.json"), None),
        intel=_intel_snapshot(system_dir, rows, today),
    )


def render_text(h):
    icon = {OK: "✓", WATCH: "▲", ACT: "●"}
    lines = ["Service health %s: overall %s" % (h["today"], h["overall"])]
    lines += ["  %s %-5s %s — %s" % (icon[c["status"]], c["status"], c["name"], c["reason"]) for c in h["checks"]]
    lines += ["  INCIDENT: %s" % i for i in h["incidents"]]
    return "\n".join(lines) + "\n"


def run(system_dir, data_path, now, career_runner=career_counts):
    """Compute the health, write health.json, health_history.json and last_run.json, return the health dict."""
    inputs = gather(system_dir, data_path, now, career_runner)
    h = compute_health(**inputs)
    with open(os.path.join(system_dir, "health.json"), "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    with open(os.path.join(system_dir, "health_history.json"), "w", encoding="utf-8") as f:
        json.dump(update_history(inputs["history"], h["today"], h["checks"]), f, ensure_ascii=False, indent=1)
    with open(os.path.join(system_dir, "last_run.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": now.isoformat(timespec="seconds")}, f)
    return h


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--system-dir", default=HERE)
    ap.add_argument("--now", default=None, help="ISO-8601 timestamp, default: now")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD, default: today")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--render", action="store_true", help="refresh the HTML pages afterwards")
    a = ap.parse_args(argv)
    try:
        now = parse_ts(a.now) if a.now else (
            datetime.combine(date.fromisoformat(a.today), datetime.now().time()) if a.today else datetime.now())
    except ValueError as e:
        print("health: bad --now/--today (%s)" % e, file=sys.stderr)
        return 1
    system_dir = a.system_dir
    if system_dir == HERE:
        if a.data and os.path.dirname(a.data) and os.path.exists(os.path.join(os.path.dirname(a.data), "pipeline.csv")):
            system_dir = os.path.dirname(a.data)
        elif os.path.isdir("_system"):
            system_dir = "_system"
    try:
        h = run(system_dir, a.data, now)
    except (OSError, ValueError, csv.Error) as e:
        print("health: cannot read %s (%s)" % (a.data, e), file=sys.stderr)
        return 1
    if not a.quiet:
        sys.stdout.write(render_text(h))
    if a.render:
        import subprocess
        root = os.path.dirname(os.path.abspath(system_dir))
        today_str = (a.today or now.date().isoformat())
        cmd = [sys.executable, kit_run.script_path(system_dir, "render"), "--data", a.data,
               "--prep", os.path.join(system_dir, "prep.json"), "--folders", os.path.join(system_dir, "folders.tsv"),
               "--today", today_str, "--out", root]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("  ! render.py fehlgeschlagen (Code %s): %s" % (r.returncode, (r.stderr or "").strip()[-400:]), file=sys.stderr)
            return 2
        print("  Seiten aktualisiert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
