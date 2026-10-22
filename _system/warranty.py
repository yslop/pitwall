"""Warranty of the intel process (ITIL 5 'warranty': does it hold, every day).

Four deterministic checks over the processes in conversation (Screening, Interviewing, Final; Applied owes nothing, headhunter
channels are skipped): the document of the stage exists, is not older than the newest input in the landing zone ('30 Verlauf'),
research orders do not rot, and inputs are acknowledged by revisit. No model calls. Thresholds (owner decision 2026-10-02):
Final and Interviewing 1 working day, Screening 3 working days (the routines run Monday to Friday); a deadline (due) within 3 days always escalates to Act.
Records have the shape of health.py (id, group, name, status, reason, target). Python 3.9 compatible.
"""
import json
import os
import re
from datetime import date, datetime

import intel_job as IJ
import intel_lint as L
import intel_quality as Q
import revisit as RV

OK, WATCH, ACT = "OK", "Watch", "Act"
RANK_STATUS = {OK: 0, WATCH: 1, ACT: 2}
SLA_DAYS = {"Final": 1, "Interviewing": 1, "Screening": 3}
DEADLINE_DAYS = 3
VERSION = re.compile(r"_v(\d+)\.\w+$")
DATE_IN_NAME = re.compile(r"(20\d{2}-\d{2}-\d{2})")
DOC_LABEL = {"cheat_sheet": "Cheat Sheet", "briefing": "Briefing", "strategy": "Strategy-Dokument"}
SUBS = ("", "20 Vorbereitung", "30 Verlauf")


def _json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _mtime_day(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat()
    except OSError:
        return ""


def _days(today, iso):
    try:
        return (date.fromisoformat(today) - date.fromisoformat(iso)).days
    except (TypeError, ValueError):
        return None


def age_days(today, iso):
    """Working days (Monday to Friday) after `iso` up to and including `today`: the routines run on weekdays only, so a Friday order is 1 day old on Monday.
    None for an unreadable date; 0 for a date that is today or in the future."""
    try:
        end, d = date.fromisoformat(today), date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    n = 0
    while d < end and n < 4000:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            n += 1
    return n


def _scan_docs(folder):
    docs = []
    for base in (str(folder), os.path.dirname(str(folder))):
        for sub in SUBS:
            d = os.path.join(base, sub) if sub else base
            try:
                names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)) and not n.startswith("."))
            except OSError:
                continue
            for n in names:
                kind = IJ.KIND_TO_DOC.get(IJ.II.classify(n))
                if not kind or n.startswith(("Recherche_Auftrag", "Nachbereitung_Auftrag")):
                    continue
                m, v = DATE_IN_NAME.search(n), VERSION.search(n)
                docs.append({"kind": kind, "version": int(v.group(1)) if v else None, "date": m.group(1) if m else _mtime_day(os.path.join(d, n))})
    return docs


def _quality(folder, stage, today):
    """Evidence metrics of the current document of the stage (or a deeper one), or None when none exists as markdown."""
    needed = IJ.RANK[IJ.STAGE_DOC[stage]]
    try:
        docs = [d for d in L.find_docs(folder) if IJ.RANK.get(d["doc"], 0) >= needed]
        if not docs:
            return None
        d = max(docs, key=lambda x: (IJ.RANK[x["doc"]], x["version"], x["date"]))
        with open(d["path"], encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = Q.metrics(text, d["doc"], d["version"], today, d["file"])
        m.update(file=d["file"], doc=d["doc"], version=d["version"])
        return m
    except Exception as exc:                  # reported by the check as Act, never swallowed
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _scan_inputs(folder):
    d = os.path.join(str(folder), "30 Verlauf")
    try:
        names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)) and not n.startswith(".") and not RV.is_generated(n))
    except OSError:
        return []
    return [{"name": n, "date": _mtime_day(os.path.join(d, n))} for n in names]


PREP_STAGES = ("Interviewing", "Final")


def _prep_state(folder):
    """Newest Prep_Brief html of the process: file name, number of visible gaps (PREP GAP marks, 'pending org research') and whether it has the questions section."""
    best = None
    for base in (str(folder), os.path.dirname(str(folder))):
        for sub in SUBS:
            d = os.path.join(base, sub) if sub else base
            try:
                names = [n for n in os.listdir(d) if re.match(r"prep[\s_-]*brief", n, re.I) and n.lower().endswith(".html")]
            except OSError:
                continue
            for n in names:
                m = DATE_IN_NAME.search(n)
                key = (m.group(1) if m else _mtime_day(os.path.join(d, n)) or "", n)
                if best is None or key > best[0]:
                    best = (key, os.path.join(d, n))
    if best is None:
        return {"file": None, "gaps": 0, "questions": False}
    try:
        with open(best[1], encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {"file": os.path.basename(best[1]), "date": best[0][0], "gaps": 0, "questions": False}
    return {"file": os.path.basename(best[1]), "date": best[0][0], "gaps": text.count("PREP GAP") + text.lower().count("pending org research"),
            "questions": 'id="meine-fragen"' in text}


def _cockpit_state(folder):
    """Newest generated Cockpit_*.html of the process (the owner's own PDF cockpits do not count): file, date, number of PREP GAP marks; None if there is none."""
    best = None
    for base in (str(folder), os.path.dirname(str(folder))):
        for sub in SUBS:
            d = os.path.join(base, sub) if sub else base
            try:
                names = [n for n in os.listdir(d) if re.match(r"cockpit[\s_-]", n, re.I) and n.lower().endswith(".html")]
            except OSError:
                continue
            for n in names:
                m = DATE_IN_NAME.search(n)
                key = (m.group(1) if m else _mtime_day(os.path.join(d, n)) or "", n)
                if best is None or key > best[0]:
                    best = (key, os.path.join(d, n))
    if best is None:
        return None
    try:
        with open(best[1], encoding="utf-8", errors="replace") as f:
            gaps = f.read().count("PREP GAP")
    except OSError:
        gaps = 0
    return {"file": os.path.basename(best[1]), "date": best[0][0], "gaps": gaps}


def snapshot(system, base_dir, rows, today, locate=None):
    """One dict per process that owes a document: stage, due, folder found, documents, inputs, unacknowledged inputs, orders."""
    if locate is None:
        from folder_utils import locate_role_folder as locate
    channels = set(IJ.channel_uids(system))
    state, seen = _json(os.path.join(system, "intel_state.json")), _json(os.path.join(system, "revisit_state.json"))
    out = []
    for r in rows or []:
        stage = (r.get("stage") or "").strip()
        if stage not in SLA_DAYS:
            continue
        raw = str(r.get("uid") or "").strip()
        uid = IJ.C.norm_uid(raw)
        if uid in channels:
            continue
        folder, _ = locate(base_dir, uid, r.get("role") or "", r.get("folder_id") or "")
        pos = {"uid": uid, "company": r.get("company") or uid, "stage": stage, "due": (r.get("due") or "").strip() or None,
               "folder": folder is not None, "docs": [], "inputs": [], "unacked": [], "orders": [], "quality": None, "prep": None, "cockpit": None}
        entry = state.get(uid) if isinstance(state.get(uid), dict) else state.get(raw) if isinstance(state.get(raw), dict) else {}
        jobs = entry.get("jobs") if isinstance(entry.get("jobs"), dict) else {}
        pos["orders"] = [{"doc": j.get("doc"), "date": j.get("date") or "", "version": j.get("version"), "after": bool(j.get("after"))}
                         for j in jobs.values() if isinstance(j, dict) and j.get("doc") in IJ.RANK]
        if folder is not None:
            pos["docs"], pos["inputs"] = _scan_docs(folder), _scan_inputs(folder)
            pos["quality"] = _quality(folder, stage, today)
            pos["prep"] = _prep_state(folder)
            pos["cockpit"] = _cockpit_state(folder)
            known = seen.get(uid) if isinstance(seen.get(uid), dict) else seen.get(raw) if isinstance(seen.get(raw), dict) else {}
            known_files = set(known.get("known_files") or [])
            pos["unacked"] = [i["name"] for i in pos["inputs"] if i["name"] not in known_files]
        out.append(pos)
    return out


# ---- checks ---------------------------------------------------------------------------------------------------------
def _rec(cid, name, status, reason, target):
    return {"id": cid, "group": "warranty", "name": name, "status": status, "reason": reason, "target": target}


def _verdict(items, ok_text):
    """items: [(status, text)] -> (status, reason)."""
    bad = [(s, t) for s, t in items if s != OK]
    if not bad:
        return OK, ok_text
    status = max((s for s, _ in bad), key=lambda s: RANK_STATUS[s])
    bad.sort(key=lambda it: -RANK_STATUS[it[0]])
    texts = [t for _, t in bad]
    return status, "; ".join(texts[:4]) + ("; und %d weitere" % (len(texts) - 4) if len(texts) > 4 else "")


def _days_until(p, today):
    return _days(p["due"], today) if p.get("due") else None          # negative: the date has passed


def _deadline_soon(p, today):
    n = _days_until(p, today)
    return n if n is not None and 0 <= n <= DEADLINE_DAYS else None


def _has_stage_doc(p):
    return p["stage"] in SLA_DAYS and p.get("folder") and any(IJ.RANK.get(d["kind"], 0) >= IJ.RANK[IJ.STAGE_DOC[p["stage"]]] for d in p.get("docs") or [])


def open_orders(p):
    """Orders no document of that depth (or a deeper one) has closed yet: version reached or not older than the order."""
    out = []
    for o in p.get("orders") or []:
        want = IJ.RANK.get(o.get("doc"), 0)
        done = any(IJ.RANK.get(d["kind"], 0) >= want and ((d.get("version") is not None and d["version"] >= (o.get("version") or 1))
                                                           or (d.get("date") or "") >= (o.get("date") or "")) for d in p.get("docs") or [])
        if not done:
            out.append(o)
    return out


def check_stage_docs(positions, today):
    items, owed = [], 0
    for p in positions:
        if p["stage"] not in SLA_DAYS:
            continue
        owed += 1
        needed = IJ.STAGE_DOC[p["stage"]]
        if not p.get("folder"):
            items.append((ACT, "%s (%s): Ordner nicht gefunden" % (p["company"], p["stage"])))
            continue
        if any(IJ.RANK.get(d["kind"], 0) >= IJ.RANK[needed] for d in p["docs"]):
            continue
        ages = [age_days(today, o["date"]) for o in open_orders(p) if IJ.RANK.get(o["doc"], 0) >= IJ.RANK[needed]]
        ages = [a for a in ages if a is not None]
        left = _deadline_soon(p, today)
        if not ages:
            status, why = (ACT if p["stage"] != "Screening" else WATCH), "kein Auftrag"
        else:
            age = max(ages)
            status, why = (ACT if age > SLA_DAYS[p["stage"]] else WATCH), "Auftrag seit %d Arbeitstagen offen" % age
        if left is not None:
            status, why = ACT, why + ", Frist in %d Tagen" % left
        items.append((status, "%s (%s): %s fehlt, %s" % (p["company"], p["stage"], DOC_LABEL[needed], why)))
    status, reason = _verdict(items, "%d Prozesse in Screening oder weiter haben ihr Stufen-Dokument" % owed)
    return _rec("intel_stage_doc", "Quality · stage document", status, reason,
                "every process from Screening on has the document of its stage (Screening cheat sheet, Interviewing briefing, Final strategy)")


def check_fresh(positions, today):
    items = []
    for p in positions:
        if p["stage"] not in SLA_DAYS or not p.get("docs") or not p.get("inputs"):
            continue
        latest = max(d["date"] for d in p["docs"] if d.get("date")) if any(d.get("date") for d in p["docs"]) else ""
        newest = max(p["inputs"], key=lambda i: i.get("date") or "")
        if not latest or (newest.get("date") or "") <= latest:
            continue
        age = age_days(today, newest["date"])
        left = _deadline_soon(p, today)
        status = ACT if (age is not None and age > SLA_DAYS[p["stage"]]) or left is not None else WATCH
        items.append((status, "%s (%s): Eingang vom %s neuer als das Dokument vom %s%s" % (
            p["company"], p["stage"], newest["date"], latest, ", Frist in %d Tagen" % left if left is not None else "")))
    status, reason = _verdict(items, "kein Dokument ist älter als der neueste Eingang")
    return _rec("intel_fresh", "Freshness · documents versus inputs", status, reason,
                "no document is older than the newest input in 30 Verlauf (1 working day Interviewing/Final, 3 working days Screening)")


def check_orders(positions, today):
    items, total = [], 0
    for p in positions:
        if p["stage"] not in SLA_DAYS:
            continue
        for o in open_orders(p):
            age = age_days(today, o.get("date") or "")
            if age is None:
                continue
            total += 1
            label = DOC_LABEL.get(o["doc"], o["doc"]) + (" (nach Gespräch)" if o.get("after") else "")
            items.append((ACT if age > SLA_DAYS[p["stage"]] else WATCH, "%s (%s): %s-Auftrag seit %d Arbeitstagen offen" % (p["company"], p["stage"], label, age)))
    status, reason = _verdict(items, "kein offener Recherche-Auftrag")
    if total and status != OK:
        reason = "%d offen: %s" % (total, reason)
    return _rec("intel_orders", "Backlog · research orders", status, reason,
                "open research orders are done within 1 working day (Interviewing/Final) or 3 working days (Screening)")


def check_inputs(positions, today):
    items, total = [], 0
    for p in positions:
        if p["stage"] not in SLA_DAYS:
            continue
        dates = {i["name"]: i.get("date") for i in p.get("inputs") or []}
        for name in p.get("unacked") or []:
            total += 1
            age = age_days(today, dates.get(name) or "")
            items.append((ACT if age is not None and age > SLA_DAYS[p["stage"]] else WATCH, "%s (%s): %s nicht verarbeitet" % (p["company"], p["stage"], name[:40])))
    status, reason = _verdict(items, "alle Eingänge in 30 Verlauf sind von revisit erfasst")
    if total and status != OK:
        reason = "%d Datei(en): %s" % (total, reason)
    return _rec("intel_inputs", "Landing zone · unprocessed inputs", status, reason,
                "every input in 30 Verlauf is acknowledged by revisit within the threshold")


def check_quality(positions, today):
    items = []
    for p in positions:
        if not _has_stage_doc(p):
            continue
        q = p.get("quality")
        who = "%s (%s)" % (p["company"], p["stage"])
        if q is None:
            items.append((WATCH, "%s: Dokument nicht prüfbar (nur PDF oder HTML, keine .md-Datei)" % who))
        elif q.get("error"):
            items.append((ACT, "%s: Prüfung nicht möglich (%s)" % (who, q["error"][:60])))
        elif q.get("lint") == "fail":
            items.append((ACT, "%s: Lint-Fehler in %s (%s)" % (who, q.get("file", "Dokument"), ", ".join(q.get("lint_rules") or []))))
        elif q.get("lint") == "warn":
            near = _deadline_soon(p, today)
            items.append((ACT if near is not None else WATCH, "%s: Lint-Warnung in %s (%s)%s" % (who, q.get("file", "Dokument"), ", ".join(q.get("lint_rules") or []),
                                                                                              ", Frist in %d Tagen" % near if near is not None else "")))
    status, reason = _verdict(items, "alle aktuellen Dokumente bestehen den Lint ohne Befund")
    return _rec("intel_quality", "Quality · current document (lint)", status, reason,
                "the current document of every process passes intel_lint without a finding (a warning is Act when the date is within 3 days)")


def check_evidence(positions, today):
    items = []
    for p in positions:
        q = p.get("quality") if _has_stage_doc(p) else None
        if not isinstance(q, dict) or q.get("error"):
            continue
        who = "%s (%s)" % (p["company"], p["stage"])
        if q.get("dangling"):
            items.append((ACT, "%s: Verweis %s ohne Quelle in der Liste" % (who, ", ".join("[%d]" % n for n in q["dangling"]))))
        facts, bare = q.get("facts") or 0, q.get("facts_unsourced") or 0
        if facts and bare / float(facts) > 0.2:
            items.append((WATCH, "%s: %d von %d Fakten ohne Quellenverweis" % (who, bare, facts)))
        if (q.get("domains") or 0) < 2:
            items.append((WATCH, "%s: nur eine Quelle oder Domäne" % who))
        age, left = q.get("oldest_source_age"), _days_until(p, today)
        if age is not None and age > 14 and left is not None and 0 <= left <= 7:
            items.append((ACT if left <= DEADLINE_DAYS else WATCH, "%s: älteste Quelle %d Tage alt, Frist in %d Tagen" % (who, age, left)))
    status, reason = _verdict(items, "Verweise, Quellenzahl und Quellenalter sind unauffällig")
    return _rec("intel_evidence", "Evidence · sources and references", status, reason,
                "every fact carries a reference that exists, at least two source domains, no source older than 14 days when the date is within 7 days")


def check_prep(positions, today):
    items = []
    for p in positions:
        if p["stage"] not in PREP_STAGES or not p.get("folder"):
            continue
        pr, who, near = p.get("prep"), "%s (%s)" % (p["company"], p["stage"]), _deadline_soon(p, today)
        if not pr or not pr.get("file"):
            problems = ["Prep-Brief fehlt"]
        else:
            problems = []
            if pr.get("gaps"):
                problems.append("%d Lücke(n) im Prep-Brief" % pr["gaps"])
            if not pr.get("questions"):
                problems.append("Meine Fragen fehlen")
            newest = max((d.get("date") or "" for d in p.get("docs") or [] if d.get("kind") in ("briefing", "strategy")), default="")
            if newest and (pr.get("date") or "") < newest:
                problems.append("Prep-Brief (%s) älter als das Briefing (%s)" % (pr.get("date") or "?", newest))
        ck, newest_doc = p.get("cockpit"), max((d.get("date") or "" for d in p.get("docs") or [] if d.get("kind") in ("briefing", "strategy")), default="")
        if not ck or not ck.get("file"):
            problems.append("Cockpit fehlt")
        else:
            if ck.get("gaps"):
                problems.append("%d Lücke(n) im Cockpit" % ck["gaps"])
            if newest_doc and (ck.get("date") or "") < newest_doc:
                problems.append("Cockpit (%s) älter als das Briefing (%s)" % (ck.get("date") or "?", newest_doc))
        if problems:
            items.append((ACT if near is not None else WATCH, "%s: %s%s" % (who, ", ".join(problems), ", Frist in %d Tagen" % near if near is not None else "")))
    status, reason = _verdict(items, "Prep-Brief und Cockpit ab Interviewing sind vollständig (keine Lücken, Meine Fragen vorhanden)")
    return _rec("intel_prep", "Quality · prep brief complete", status, reason,
                "every process from Interviewing on has a prep brief and a cockpit without PREP GAP marks, with ranked questions for the panel, not older than the briefing (a gap is Act when the date is within 3 days)")


def checks(positions, today):
    return [check_stage_docs(positions, today), check_fresh(positions, today), check_orders(positions, today), check_inputs(positions, today),
            check_quality(positions, today), check_evidence(positions, today), check_prep(positions, today)]
