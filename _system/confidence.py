"""Confidence to land the job, in percent: a transparent heuristic from stage, documented conversations, fit, pay band and silence.

Not a forecast. Closed rows have no value. `why` lists every factor so the owner can overrule it by judgement.
"""
import os
import re

BASE = {"Watchlist": 2, "Applied": 6, "Screening": 15, "Interviewing": 28, "Final": 55}
CAP = {"Watchlist": 5, "Applied": 15, "Screening": 30, "Interviewing": 60, "Final": 85}
PER_CONVERSATION, MAX_CONVERSATIONS = 5, 3
TRANSCRIPT = re.compile(r"transkript|transcript", re.I)
DEBRIEF = re.compile(r"debrief", re.I)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def conversations_done(role_folder):
    """Transcripts in `30 Verlauf` of the role folder, one per conversation held; a lone debrief counts as one."""
    try:
        names = os.listdir(os.path.join(role_folder, "30 Verlauf"))
    except (OSError, TypeError):
        return 0
    transcripts = sum(1 for n in names if TRANSCRIPT.search(n))
    return transcripts or min(1, sum(1 for n in names if DEBRIEF.search(n)))     # a debrief or summary of a call is not another call


def estimate(row, conversations):
    stage = row.get("stage", "")
    if stage not in BASE:
        return None
    pct, why = BASE[stage], ["Stufe %s: %d %%" % (stage, BASE[stage])]
    n = min(int(conversations or 0), MAX_CONVERSATIONS)
    if n:
        pct += n * PER_CONVERSATION
        why.append("%d dokumentierte Gespräche: +%d" % (n, n * PER_CONVERSATION))
    score = _num(row.get("score"))
    if score >= 70:
        pct += 5; why.append("Match-Score %d: +5" % score)
    elif 0 < score < 40:
        pct -= 3; why.append("Match-Score %d: -3" % score)
    fit = row.get("salary_fit", "")
    if fit in ("above", "around"):
        pct += 4; why.append("Gehalt im Zielband: +4")
    elif fit == "below":
        pct -= 6; why.append("Gehalt unter Zielband: -6")
    elif fit == "stretch":
        pct -= 3; why.append("Gehalt am Rand: -3")
    idle = _num(row.get("days_idle"))
    if idle > 45:
        pct -= 10; why.append("%d Tage ohne Signal: -10" % idle)
    elif idle > 21:
        pct -= 5; why.append("%d Tage ohne Signal: -5" % idle)
    pct = max(1, min(pct, CAP[stage]))
    return {"pct": int(pct), "why": why}


def valid_judgement(c):
    """True for {"pct": 1..95, "begruendung": text}; the observer's value must carry its reasoning."""
    return (isinstance(c, dict) and isinstance(c.get("pct"), int) and not isinstance(c.get("pct"), bool)
            and 1 <= c["pct"] <= 95 and bool(str(c.get("begruendung") or "").strip()))


def observer_judgement(role_folder):
    """The assessment written into Prep_Inhalt.json after the conversations (content and signals, not the stage), or None."""
    import json
    try:
        with open(os.path.join(role_folder, "20 Vorbereitung", "Prep_Inhalt.json"), encoding="utf-8") as f:
            c = json.load(f).get("confidence")
    except (OSError, TypeError, ValueError, AttributeError):
        return None
    if not valid_judgement(c):
        return None
    stand = str(c.get("stand") or "").strip()
    return {"pct": c["pct"], "why": ["Einschätzung nach den Gesprächen%s: %s" % (" (Stand %s)" % stand if stand else "", str(c["begruendung"]).strip())]}
