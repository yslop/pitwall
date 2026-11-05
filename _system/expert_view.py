"""The expert view (Phase 3b): one card per process that is in conversation (Screening, Interviewing, Final).

For each: where it stands, the timeline of stage changes, the next step, and a preparation checklist (briefing, debrief after the last conversation,
transcript or notes, follow-up). Pure functions plus one folder scan. Everything shown is a fixed label or a short escaped value; malformed input is skipped.
"""
import os
import re
from datetime import date

import today_view as TV

EXPERT_STAGES = ("Screening", "Interviewing", "Final")
CLOSED_ROLE = re.compile(r"\((rejected|inactive)\)\s*$", re.I)
TRANSCRIPT = re.compile(r"transkript|transcript|gespr(?:ä|ae)chs?[-_ ]?notiz|interview[-_ ]?notes?|call[-_ ]?notes?|meeting[-_ ]?notes?|notizen? (?:zum|zu|vom)|\.(?:vtt|srt)$", re.I)
DEBRIEF = re.compile(r"^Debrief_.*?(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})", re.I)
CONVERSATION = re.compile(r"gespr(?:ä|ae)ch|telefonat|(?<![a-z])call(?![a-z])|interview|teams|kennenlern|runde|round|gef(?:ü|ue)hrt|stattgefunden|gehalten", re.I)
INVITATION = re.compile(r"einladung|eingeladen|geplant|terminiert|scheduled|invitation|vereinbart", re.I)
MAX_TIMELINE = 4
FOLLOW_UP_DAYS = {"Interviewing": 7, "Final": 14}


def _iso(text):
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})$", text)
    return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1))) if m else text


def scan_folders(base_dir, rows, finder=None, role_finder=None):
    """{uid: {'debriefs': [(iso date, name)], 'transcripts': [names, oldest first]}} from the process's own role folder (`30 Verlauf`); when the role folder
    cannot be told apart, all open role folders of the employer. A missing folder is an empty entry."""
    if finder is None or role_finder is None:
        from folder_utils import find_company_folder, find_role_folder
        finder = finder or find_company_folder
        role_finder = role_finder or find_role_folder
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("stage") not in EXPERT_STAGES:
            continue
        uid = TV._uid_key(r.get("uid"))
        entry = {"debriefs": [], "transcripts": []}
        try:
            company, _ = finder(base_dir, uid, r.get("folder_id") or "")
            roles = []
            if company:
                mine, _ = role_finder(company, r.get("role") or "")
                roles = [str(mine)] if mine is not None and os.path.isdir(str(mine)) else [os.path.join(str(company), d) for d in sorted(os.listdir(str(company)))
                                                                                            if os.path.isdir(os.path.join(str(company), d)) and not CLOSED_ROLE.search(d)]
            files = []
            for role in roles:
                verlauf = os.path.join(role, "30 Verlauf")
                try:
                    names = [n for n in os.listdir(verlauf) if os.path.isfile(os.path.join(verlauf, n)) and not n.startswith(".")]
                except OSError:
                    continue
                for n in names:
                    m = DEBRIEF.match(n)
                    if m:
                        entry["debriefs"].append((_iso(m.group(1)), n))
                    elif TRANSCRIPT.search(n):
                        files.append((os.path.getmtime(os.path.join(verlauf, n)), n))
            entry["transcripts"] = [n for _, n in sorted(files)]
            entry["debriefs"].sort()
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        out[uid] = entry
    return out


def _d(text):
    try:
        return date.fromisoformat(str(text).strip()[:10])
    except ValueError:
        return None


def _timeline(uid, transitions, today):
    """(timeline lines, date of the last real conversation). A conversation is a stage change into Interviewing/Final that is not just an invitation, or a change
    whose reason names a conversation (call, Gespräch, round); an invitation or a planned date in the future is not one."""
    rows = [t for t in (transitions if isinstance(transitions, list) else []) if isinstance(t, dict) and TV._uid_key(t.get("uid")) == uid and _d(t.get("datum"))]
    rows.sort(key=lambda t: _d(t["datum"]))
    talks = []
    for t in rows:
        why = str(t.get("ausloeser") or "")
        if _d(t["datum"]) <= today and (CONVERSATION.search(why) or (t.get("nach") in ("Interviewing", "Final") and not INVITATION.search(why))):
            talks.append(_d(t["datum"]))
    lines = [{"date": _d(t["datum"]).strftime("%d.%m.%y"), "text": "%s → %s%s" % (TV._short(t.get("von"), 20), TV._short(t.get("nach"), 20),
                                                                                     (" · " + TV._short(t.get("ausloeser"), 90)) if t.get("ausloeser") else "")}
             for t in rows[-MAX_TIMELINE:]]
    return lines, (max(talks) if talks else None)


def _int(v):
    try:
        n = int(float(str(v).strip()))
    except (TypeError, ValueError, OverflowError):
        return 0
    return n if 0 <= n <= 99999 else 0


def _item(ok, label, detail="", todo=""):
    return {"ok": "ja" if ok else "", "label": label, "detail": TV._short(detail, 140), "todo": TV._short(todo, 140)}


def build_expert(rows, transitions, today, intel=None, intel_state=None, coverage=None, drafts=None, renders=None, scan=None, channels=None):
    """[card] for the processes in conversation, Final first, then Interviewing, then Screening; each card carries its checklist."""
    try:
        t = date.fromisoformat(today)
    except ValueError:
        return []
    cov = {TV._uid_key(k): v for k, v in coverage.items()} if isinstance(coverage, dict) else {}
    ist = {TV._uid_key(k): v for k, v in intel_state.items()} if isinstance(intel_state, dict) else {}
    scan = scan if isinstance(scan, dict) else {}
    cards = []
    for stage in reversed(EXPERT_STAGES):
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict) or r.get("stage") != stage:
                continue
            uid = TV._uid_key(r.get("uid"))
            channel, _ = TV._channel(uid, channels)
            if channel:
                continue                                                          # a headhunter channel has no interview to prepare
            timeline, last_move = _timeline(uid, transitions, t)
            found = scan.get(uid) if isinstance(scan.get(uid), dict) else {"debriefs": [], "transcripts": []}
            debriefs = [d for d in found.get("debriefs", []) if isinstance(d, (tuple, list)) and len(d) == 2 and _d(d[0])]
            transcripts = [n for n in found.get("transcripts", []) if isinstance(n, str)]
            label, flag = TV._intel_label(uid, stage, intel)
            work = TV._intel_text(ist.get(uid), uid)
            idle = _int(r.get("days_idle"))
            due = _d(r.get("due"))
            ready = (bool(label) and flag != "missing") or bool(work and "Lint" in work and "Fehler" not in work)
            checks = [_item(ready, "Briefing oder Cheat Sheet", work or label,
                            "" if ready else ("Lint-Fehler beheben: intel_lint.py --uid %s" % uid if work and "Fehler" in work else "Recherche auslösen: intel_job.py --uid %s" % uid))]
            last_talk = last_move
            debrief_after = [d for d in debriefs if last_talk and _d(d[0]) >= last_talk]
            checks.append(_item(bool(debrief_after) or not last_talk, "Debrief zum letzten Gespräch",
                                debrief_after[-1][1] if debrief_after else ("kein Gespräch in transitions.csv" if not last_talk else ""),
                                "" if (debrief_after or not last_talk) else "Nach dem Gespräch: intel_job.py --uid %s --after-interview" % uid))
            checks.append(_item(bool(transcripts), "Notizen oder Gedächtnisprotokoll abgelegt", transcripts[-1] if transcripts else "",
                                "" if transcripts else "In 30 Verlauf ablegen (Datei oder eigene Mitschrift benennen)"))
            follow = stage in FOLLOW_UP_DAYS and idle > FOLLOW_UP_DAYS[stage]
            checks.append(_item(not follow, "Nachfassen", "%d Tage seit dem letzten Ereignis" % idle if follow else "kein Nachfassen nötig",
                                "Nachfassen prüfen" if follow else ""))
            c = TV._coverage_text(cov.get(uid))
            cards.append({"uid": r.get("uid", ""), "company": TV._short(r.get("company"), 60), "role": TV._short(r.get("role"), 90), "stage": stage,
                          "idle": idle, "next_action": TV._short(r.get("next_action"), 160) or "—", "due": due.isoformat() if due else "",
                          "overdue": "overdue" if due and due < t else "", "timeline": timeline, "checks": checks, "coverage": c,
                          "open_items": sum(1 for x in checks if not x["ok"]), "note": TV._short(r.get("note"), 200)})
    return cards
