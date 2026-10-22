"""Builds the template context for 00_today.html from pipeline rows and health.json.

Everything the template needs is computed here as plain strings/lists, because the zero-dependency
template engine in render.py supports only simple `if`, `for` and the safe/default/length filters.
"""
import os
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from health import parse_date

STATUS_LABEL = {"OK": "In Ordnung", "Watch": "Beobachten", "Act": "Handeln"}
STATUS_ICON = {"OK": "✓", "Watch": "▲", "Act": "●"}
GROUP_LABEL = {"warranty": "Zuverlässigkeit · Warranty", "utility": "Nutzen · Utility",
               "improvement": "Verbesserung · Continual Improvement"}
LIVE_STAGES = ("Final", "Interviewing", "Screening", "Applied")
DUE_WINDOW_DAYS = 7
NOTE_MAX = 160


def _short(text, n=NOTE_MAX):
    if isinstance(text, bool) or not isinstance(text, (str, int, float)):
        text = ""                                                   # only text and numbers are shown; anything else is dropped
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _check_view(c):
    key = c["status"].lower()
    return {"id": c["id"], "name": c["name"], "group": c["group"], "group_label": GROUP_LABEL.get(c["group"], c["group"]),
            "status": c["status"], "status_key": key, "status_label": STATUS_LABEL[c["status"]],
            "icon": STATUS_ICON[c["status"]], "reason": c["reason"], "target": c["target"]}


def _needs(rows, today):
    t = date.fromisoformat(today)
    limit = t + timedelta(days=DUE_WINDOW_DAYS)
    due = [(parse_date(r.get("due")), r) for r in rows if r.get("stage") != "Closed"]
    due = sorted(((d, r) for d, r in due if d is not None and d <= limit), key=lambda x: x[0])
    return [{"uid": r.get("uid", ""), "company": r.get("company", ""), "role": _short(r.get("role"), 60),
             "action": _short(r.get("next_action"), 120) or "—", "due": d.isoformat(),
             "overdue": "overdue" if d < t else ""} for d, r in due]


def _new_today(rows, today):
    tag = "Discovered via portal %s" % today
    return [{"uid": r.get("uid", ""), "company": r.get("company", ""), "role": _short(r.get("role"), 70)}
            for r in rows if r.get("stage") == "Watchlist" and tag in (r.get("note") or "")]


def _uid_key(uid):
    """'09' and '9' are the same employer: the index keys uids as plain integers."""
    s = str(uid if uid is not None else "").strip()
    return str(int(s)) if s.isdigit() else s


INTEL_STAGES = ("Interviewing", "Final")        # stages where a missing cheat sheet is worth flagging


def _intel_label(uid, stage, intel):
    """(label, flag) for the cheat-sheet status of one live row; blank when there is no intel index at all."""
    if not intel or "uids" not in intel:
        return "", ""
    items = (intel["uids"].get(_uid_key(uid)) or {}).get("items", [])
    n = sum(1 for i in items if not i.get("superseded"))
    if n:
        return "%d Cheat Sheet%s" % (n, "" if n == 1 else "s"), ""
    return ("kein Cheat Sheet", "missing") if stage in INTEL_STAGES else ("", "")


def _lead_text(lead):
    person, org, note = (_short(lead.get(k), n) for k, n in (("person", 60), ("org", 60), ("note", 140)))
    status, nxt = _short(lead.get("status"), 30), _short(lead.get("next"), 100)
    text = " · ".join(x for x in (person, org) if x) + (" — " + note if note else "")
    if status:
        text += " (%s)" % status
    if nxt:
        text += " → " + nxt
    return text.strip()


def _channel(uid, channels):
    """(label, leads) for a uid that is a channel (e.g. a headhunter) rather than a process; malformed entries are ignored."""
    table = (channels or {}).get("channels") if isinstance(channels, dict) else None
    entry = {_uid_key(k): v for k, v in table.items()}.get(_uid_key(uid)) if isinstance(table, dict) else None
    if not isinstance(entry, dict):
        return "", []
    label = _short(entry.get("label") or str(entry.get("type") or "Kanal").title(), 30)
    leads = entry.get("leads") if isinstance(entry.get("leads"), list) else []
    texts = (_lead_text(l) for l in leads if isinstance(l, dict))
    return label, [{"text": t} for t in texts if t]


def _intel_text(entry, uid_key):
    """Short status for one process from intel_state.json: latest document with lint result, or 'Auftrag bereit'; '' when nothing is recorded."""
    if not isinstance(entry, dict):
        return ""
    docs = entry.get("docs") if isinstance(entry.get("docs"), dict) else {}
    best = None
    for rec in docs.values():
        if not isinstance(rec, dict) or not isinstance(rec.get("versions"), dict):
            continue
        latest = rec.get("latest")
        v = rec["versions"].get(latest) if isinstance(latest, str) and re.fullmatch(r"v\d{1,3}", latest) else None
        doc = rec.get("doc") if rec.get("doc") in ("cheat_sheet", "briefing", "strategy") else None
        if isinstance(v, dict) and doc and (best is None or DOC_RANK[doc] >= DOC_RANK[best[0]]):
            best = (doc, latest, v)
    jobs = entry.get("jobs") if isinstance(entry.get("jobs"), dict) else {}
    job_docs = [j["doc"] for j in jobs.values() if isinstance(j, dict) and j.get("doc") in DOC_LABEL]
    top_job = max(job_docs, key=lambda d: DOC_RANK[d]) if job_docs else None
    if top_job and (best is None or DOC_RANK[top_job] > DOC_RANK[best[0]]):     # a pending deeper document is what the process needs next
        return "%s: Auftrag bereit" % DOC_LABEL[top_job]
    if best:
        doc, latest, v = best
        return "%s %s · Lint: %s" % (DOC_LABEL[doc], latest, LINT_WORDS.get(v.get("result"), "?"))
    return ""


DOC_LABEL = {"cheat_sheet": "Cheat Sheet", "briefing": "Briefing", "strategy": "Strategy-Dokument"}
DOC_RANK = {"cheat_sheet": 1, "briefing": 2, "strategy": 3}


def _live(rows, intel, channels=None, intel_state=None):
    out = []
    for stage in LIVE_STAGES:
        for r in rows:
            if r.get("stage") == stage:
                label, flag = _intel_label(r.get("uid", ""), stage, intel)
                channel, leads = _channel(r.get("uid", ""), channels)
                if channel and flag == "missing":
                    label, flag = "", ""                    # a headhunter channel has no interview to prepare for
                out.append({"uid": r.get("uid", ""), "company": r.get("company", ""), "role": _short(r.get("role"), 70),
                            "stage": stage, "last_event": r.get("last_event", ""), "idle": r.get("days_idle", ""),
                            "note": _short(r.get("note")), "intel_label": label, "intel_flag": flag,
                            "intel_work": _intel_text(({_uid_key(k): v for k, v in intel_state.items()} if isinstance(intel_state, dict) else {}).get(_uid_key(r.get("uid", ""))), ""),
                            "channel_label": channel, "leads": leads})
    return out


CHIP_BY_STAGE = {"Applied": "Beworben", "Screening": "Screening", "Interviewing": "Interviewing", "Final": "Final", "Closed": "Geschlossen"}
TOP_SLOTS = 10
MAX_INTAKE_LINES = 8


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")      # no NaN, no infinity


def _coverage_text(entry):
    """'Abdeckung 67 % (4 von 6 Muss)' for one coverage_state.json entry; '' for anything malformed (no share means no must-haves found)."""
    if not isinstance(entry, dict) or not _num(entry.get("share")) or not _num(entry.get("proven")) or not _num(entry.get("must")):
        return ""
    text = "Abdeckung %d %% (%d von %d Muss)" % (round(entry["share"] * 100), entry["proven"], entry["must"])
    if entry.get("below") is True:
        text += " · unter der Schwelle"
    if _num(entry.get("hard_gaps")) and entry["hard_gaps"] > 0:
        text += " · %d harte Lücke%s" % (entry["hard_gaps"], "" if entry["hard_gaps"] == 1 else "n")
    return text


def _count(v):
    """A small non-negative count from a state file; anything else (negative, huge, NaN, text) is 0."""
    return int(v) if _num(v) and 0 <= v <= 999 else 0


LINT_WORDS = {"pass": "bestanden", "warn": "Warnungen", "fail": "Fehler"}


def _draft_view(entry, has_coverage):
    """(chip, text) for one draft_state.json entry: 'Entwurf v2' with the lint result, 'Bereit zum Entwurf' once the job file exists, else ('', '')."""
    if not isinstance(entry, dict):
        return ("Analysiert" if has_coverage else ""), ""
    versions = entry.get("versions") if isinstance(entry.get("versions"), dict) else {}
    latest = entry.get("latest")
    if isinstance(latest, str) and re.fullmatch(r"v\d{1,3}", latest) and isinstance(versions.get(latest), dict):
        v = versions[latest]
        result = LINT_WORDS.get(v.get("result"), "")
        counts = []
        fails, warns = _count(v.get("fails")), _count(v.get("warns"))
        if fails:
            counts.append("%d Fehler" % fails)
        if warns:
            counts.append("%d Warnung%s" % (warns, "" if warns == 1 else "en"))
        text = "Entwurf %s" % latest + (" · Lint: %s" % result if result else "") + (" (%s)" % ", ".join(counts) if counts and result != "bestanden" else "")
        return "Entwurf %s" % latest, text
    if isinstance(entry.get("job"), dict):
        return "Bereit zum Entwurf", "Auftrag bereit: Entwurf in einer Claude-Sitzung anfragen"
    return ("Analysiert" if has_coverage else ""), ""


def _render_text(entry, version):
    """'ATS + CI' when both renderings of the draft version exist in render_state.json, 'ATS' or 'CI' when only one does, else ''."""
    if not isinstance(entry, dict) or not isinstance(version, str) or not re.fullmatch(r"v\d{1,3}", version):
        return ""
    files = entry.get(version, {}).get("files") if isinstance(entry.get(version), dict) else None
    if not isinstance(files, list):
        return ""
    names = [f for f in files if isinstance(f, str)]
    parts = [label for label, mark in (("ATS", "_ATS.docx"), ("CI", "_CI.pdf")) if any(n.endswith(mark) for n in names)]
    return " + ".join(parts)


STAGE_WORDS = {"Applied": "beworben", "Watchlist": "noch nicht beworben"}


def _suggestions(rank_state, top10):
    """Rows the ranking proposes for the free Top-10 places (not the ones already pinned): score, what it rests on, and the pin command."""
    if not isinstance(rank_state, dict) or not isinstance(rank_state.get("ranked"), list):
        return [], ""
    pinned = {_uid_key(u) for u in (top10.get("pinned") if isinstance(top10, dict) and isinstance(top10.get("pinned"), list) else [])}
    wanted = [_uid_key(u) for u in (rank_state.get("suggested") if isinstance(rank_state.get("suggested"), list) else [])]
    out = []
    for x in rank_state["ranked"]:
        if not isinstance(x, dict) or _uid_key(x.get("uid")) not in wanted or _uid_key(x.get("uid")) in pinned:
            continue
        score = x.get("score")
        reasons = x.get("reasons") if isinstance(x.get("reasons"), list) else []
        out.append({"uid": _short(x.get("uid"), 10), "company": _short(x.get("company"), 60), "role": _short(x.get("role"), 80), "stage": STAGE_WORDS.get(x.get("stage"), _short(x.get("stage"), 20)),
                    "score": int(score) if _num(score) and 0 <= score <= 100 else 0, "why": " · ".join(_short(r, 60) for r in reasons[:3] if isinstance(r, str))})
    return out, _short(rank_state.get("date"), 12)


def _own_finds(rows, top10, prep, coverage=None, drafts=None, renders=None):
    """Pinned rows in pin order with a stage chip; uids without a row are skipped."""
    pinned = top10.get("pinned") if isinstance(top10, dict) else None
    if not isinstance(pinned, list):
        return []
    by_uid = {_uid_key(r.get("uid")): r for r in rows}
    out = []
    for u in pinned:
        r = by_uid.get(_uid_key(u))
        if not r or isinstance(u, bool):
            continue
        uid = _uid_key(u)
        cov = {_uid_key(k): v for k, v in coverage.items()} if isinstance(coverage, dict) else {}
        dr = {_uid_key(k): v for k, v in drafts.items()} if isinstance(drafts, dict) else {}
        d_chip, d_text = _draft_view(dr.get(uid), _coverage_text(cov.get(uid)) != "")
        rn = {_uid_key(k): v for k, v in renders.items()} if isinstance(renders, dict) else {}
        latest = dr.get(uid, {}).get("latest") if isinstance(dr.get(uid), dict) else None
        r_text = _render_text(rn.get(uid), latest)
        if r_text and d_text:
            d_text += " · Dateien: " + r_text
        chip = CHIP_BY_STAGE.get(r.get("stage", "")) or d_chip or ("Vorbereitet" if isinstance(prep, dict) and uid in prep else "Eingegangen")
        out.append({"uid": r.get("uid", ""), "company": r.get("company", ""), "role": _short(r.get("role"), 70), "chip": chip,
                    "note": _short(r.get("note"), 120),
                    "coverage": _coverage_text(cov.get(uid)), "draft": d_text})
    return out


def _inbox_target(item):
    """The file the user should open: the proposal, else the file itself ('' when unknown)."""
    target = item.get("edit") or item.get("sidecar") or item.get("file")
    return target if isinstance(target, str) else ""


def _inbox_href(item):
    """Relative link (from the pages in the career folder) to that file."""
    target = _inbox_target(item)
    return "_Eingang/" + quote(target, safe="") if target else ""


MAX_CHANGE_LINES = 12
SNAPSHOT_RE = re.compile(r"^\d{8}(?:_\d{1,4})?_pipeline\.csv$")


def _stage_text(row):
    stage = _short(row.get("stage"), 20)
    outcome = _short(row.get("outcome"), 20)
    return "%s (%s)" % (stage, outcome) if stage == "Closed" and outcome else stage


def changes_since(rows, baseline):
    """[{'label','text'}]: rows that are new or whose stage/outcome differ from an older snapshot. No snapshot (None or empty) means no statement."""
    if not isinstance(baseline, list) or not baseline or not isinstance(rows, list):
        return []
    old = {_uid_key(r.get("uid")): r for r in baseline if isinstance(r, dict) and r.get("uid") not in (None, "")}
    out = []
    for r in rows:
        if not isinstance(r, dict) or r.get("uid") in (None, ""):
            continue
        o = old.get(_uid_key(r.get("uid")))
        who = "%s · %s" % (_short(r.get("company"), 60), _short(r.get("role"), 70))
        if o is None:
            out.append({"label": "Neu", "text": "%s (%s)" % (who, _stage_text(r))})
        elif (o.get("stage"), o.get("outcome") or "") != (r.get("stage"), r.get("outcome") or ""):
            new = r.get("stage")
            label = "Absage" if new == "Closed" and r.get("outcome") == "rejected" else "Geschlossen" if new == "Closed" else "Beworben" if new == "Applied" else "Stufe"
            out.append({"label": label, "text": "%s: %s → %s" % (who, _short(o.get("stage"), 20), _stage_text(r))})
    if len(out) > MAX_CHANGE_LINES:
        rest = len(out) - MAX_CHANGE_LINES
        out = out[:MAX_CHANGE_LINES] + [{"label": "…", "text": "und %d weitere" % rest}]
    return out


def _snapshot_key(name):
    m = re.match(r"^(\d{8})(?:_(\d{1,4}))?_pipeline\.csv$", name)
    return (m.group(1), int(m.group(2) or 0)) if m else ("", 0)


def latest_baseline(archive_dir, rows):
    """(rows, 'dd.mm. hh:mm') of the newest archived pipeline snapshot (by file name: date, then run number or time) that differs from the current rows, else (None, '').
    Unreadable, broken or oddly shaped snapshots are skipped."""
    import csv
    try:
        names = sorted((n for n in os.listdir(archive_dir) if SNAPSHOT_RE.match(n)), key=_snapshot_key, reverse=True)[:12]
    except (OSError, TypeError):
        return None, ""
    for n in names:
        p = os.path.join(archive_dir, n)
        try:
            with open(p, newline="", encoding="utf-8-sig") as f:
                snap = list(csv.DictReader(f))
            stamp = datetime.fromtimestamp(os.path.getmtime(p))
        except (OSError, UnicodeDecodeError, csv.Error, ValueError):
            continue
        if snap and "uid" in snap[0] and "stage" in snap[0] and changes_since(rows, snap):
            day, num = _snapshot_key(n)
            hhmm = "%02d:%02d" % divmod(num, 100) if 100 <= num <= 2359 and num % 100 < 60 else stamp.strftime("%H:%M")
            return snap, "%s.%s. %s" % (day[6:8], day[4:6], hhmm)
    return None, ""


def last_run_text(events):
    """'2026-09-25 · 5 Threads gesichtet · 2 Zeilen geändert · 0 neue UIDs' from the newest valid events.csv row, '' if none."""
    for e in reversed(events if isinstance(events, list) else []):
        if not isinstance(e, dict):
            continue
        try:
            d = date.fromisoformat(str(e.get("datum", "")).strip())
        except ValueError:
            continue
        parts = [d.isoformat()]
        for key, word in (("threads_gesichtet", "Threads gesichtet"), ("zeilen_geaendert", "Zeilen geändert"), ("neue_uids", "neue UIDs")):
            v = str(e.get(key, "")).strip()
            if v.isdigit() and len(v) <= 5:
                parts.append("%s %s" % (v, word))
        return " · ".join(parts)
    return ""


def _intake_lines(intake):
    lines = []
    for key, label, field in (("unclear", "Unklar", "reason"), ("failed", "Fehler", "error"), ("waiting", "Wartet", "reason")):
        items = intake.get(key) if isinstance(intake, dict) else None
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                lines.append({"label": label, "file": _short(item.get("file"), 80), "reason": _short(item.get(field), 160), "href": _inbox_href(item),
                              "target": _short(_inbox_target(item), 80)})
    items = [i for key in ("new", "existing", "healed") for i in ((intake.get(key) if isinstance(intake, dict) else None) or []) if isinstance(intake.get(key), list)]
    for item in items:
        if isinstance(item, dict) and item.get("auto") is True:
            lines.append({"label": "Automatisch angelegt", "file": _short(item.get("file"), 80), "href": "", "target": "",
                          "reason": "uid %s · %s · %s: bitte prüfen" % (_short(item.get("uid"), 10), _short(item.get("company"), 60), _short(item.get("role"), 80))})
    items = intake.get("already") if isinstance(intake, dict) else None
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            lines.append({"label": "Bereits verarbeitet", "file": _short(item.get("file"), 80), "href": _inbox_href(item), "target": _short(_inbox_target(item), 80),
                          "reason": "identisch mit uid %s: bitte aus dem Eingang entfernen" % _short(item.get("uid"), 10)})
    if len(lines) > MAX_INTAKE_LINES:                                              # a batch of stray files must not flood the card
        rest = len(lines) - MAX_INTAKE_LINES
        lines = lines[:MAX_INTAKE_LINES] + [{"label": "…", "file": "…", "reason": "und %d weitere" % rest, "href": "", "target": ""}]
    return lines


def build_context(rows, health, today, intel=None, channels=None, top10=None, prep=None, intake=None, coverage=None, drafts=None, renders=None, intel_state=None, baseline=None, baseline_label="", events=None, rank_state=None):
    """health may be None (health.json missing): then Today shows a single Act row instead of a strip."""
    if not health:
        checks = [{"id": "health", "name": "Health data", "group": "warranty", "status": "Act",
                   "reason": "health.json missing — run health.py", "target": "health.json written every run"}]
        overall, incidents, generated, deploy = "Act", [], "", None
    else:
        checks, overall = health["checks"], health["overall"]
        incidents, generated, deploy = health.get("incidents", []), health.get("generated", ""), health.get("deploy")
        if health.get("today") != today:
            checks = [{"id": "health_stale", "name": "Health data", "group": "warranty", "status": "Act",
                       "reason": "health.json is from %s, not today — the health step failed or was skipped" % health.get("today", "an unknown day"),
                       "target": "health.json written every run"}] + list(checks)
            overall = "Act"
    views = [_check_view(c) for c in checks]
    needs, new_today, live = _needs(rows, today), _new_today(rows, today), _live(rows, intel, channels, intel_state)
    own = _own_finds(rows, top10, prep, coverage, drafts, renders)
    return {
        "overall": overall, "overall_key": overall.lower(), "overall_label": STATUS_LABEL[overall],
        "overall_icon": STATUS_ICON[overall], "checks": views,
        "n_act": sum(1 for v in views if v["status"] == "Act"), "n_watch": sum(1 for v in views if v["status"] == "Watch"),
        "incidents": incidents, "generated_at": generated.replace("T", " ")[:16],
        "deploy_line": ("Letzter Deploy: %s · %s" % (deploy.get("date", "?"), deploy.get("commit", "?"))) if deploy else "",
        "needs": needs, "n_overdue": sum(1 for n in needs if n["overdue"]),
        "new_today": new_today, "live": live,
        "own_finds": own, "own_slots": ("%d von %d Fokus-Plätzen durch eigene Funde belegt" % (len(own), TOP_SLOTS)) if isinstance(top10, dict) else "", "intake_lines": _intake_lines(intake), "intake_hint": "yes" if any(l["label"] == "Unklar" for l in _intake_lines(intake)) else "",
        "suggestions": _suggestions(rank_state, top10)[0], "suggestions_date": _suggestions(rank_state, top10)[1],
        "free_places": max(0, TOP_SLOTS - len(own)) if isinstance(top10, dict) else 0,
        "changes": changes_since(rows, baseline), "changes_since": _short(baseline_label, 20) if baseline else "", "last_run": last_run_text(events),
    }
