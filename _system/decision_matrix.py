#!/usr/bin/env python3
"""Decision matrix: after a conversation, rate a handful of criteria green / amber / red and get a plain recommendation
(Go / Prüfen / Stopp), measured against your own yardstick (goal, deadline, salary band, constraints).

Where the criteria come from, most specific first:
  1. the process's own content (`Prep_Inhalt.json` -> "entscheidung": {"massstab": "...", "kriterien": [{label, go, stop}]}),
     written for that role by your AI, like the decision box of an interview battlecard;
  2. your own list from setup (`preferences.json` -> "decision_criteria": ["Budget & Freigabe", ...] or [{label, go, stop}]);
  3. five sensible defaults.
Ratings live where everything else lives: the conversation cockpit saves `Entscheidung_<Firma>_<Datum>.json`, you put the file
into `30 Verlauf` of the process, and the next sync shows the verdict on the cockpit page. Nothing leaves your computer.

    python3 _system/decision_matrix.py --uid 41 [--data pipeline.csv] [--base-dir ..]     # prints the latest verdict as JSON
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "de": [
        ("budget", "Budget & Freigabe", "Stelle ist budgetiert und freigegeben.", "Freigabe offen oder abhängig von einer Budgetrunde."),
        ("role", "Rollen-Zuschnitt", "Echte Gestaltungsrolle mit klarem Mandat.", "Vor allem Verwaltung, unklares Mandat oder Parallelstruktur."),
        ("chemistry", "Chemie mit der Führungskraft", "Dialog auf Augenhöhe, eigenes Urteil ist gefragt.", "Streng hierarchisch, wenig Raum für eigenes Urteil."),
        ("pay", "Gehalt & Entwicklung", "Im Zielband, Review oder Entwicklungspfad zugesagt.", "Unter dem Band, keine schriftliche Perspektive."),
        ("work", "Arbeitsmodell & Präsenz", "Präsenz und Reisen passen zu deinem Leben.", "Starre Präsenz, die nicht zu deinem Rahmen passt."),
    ],
    "en": [
        ("budget", "Budget & approval", "The role is budgeted and approved.", "Approval open or depending on a budget round."),
        ("role", "Scope of the role", "A real shaping role with a clear mandate.", "Mostly admin, unclear mandate or a parallel structure."),
        ("chemistry", "Chemistry with the manager", "Dialogue at eye level, your judgement is wanted.", "Strictly hierarchical, little room for your judgement."),
        ("pay", "Pay & growth", "Within your band, review or growth path agreed.", "Below your band, nothing in writing."),
        ("work", "Work model & presence", "Office days and travel fit your life.", "Rigid presence that does not fit your situation."),
    ],
}
VERDICTS = {
    "de": {"go": "Go", "check": "Prüfen", "stop": "Stopp prüfen", "open": "Offen"},
    "en": {"go": "Go", "check": "Check", "stop": "Consider stopping", "open": "Open"},
}
RATINGS = ("go", "check", "stop")
FILE_RE = re.compile(r"^Entscheidung_.*\.json$", re.I)


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:40] or "kriterium"


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_prefs(system_dir=None):
    p = _load_json(os.path.join(system_dir or HERE, "preferences.json"), {})
    return p if isinstance(p, dict) else {}


def _norm(items):
    out, seen = [], set()
    for it in items or []:
        if isinstance(it, str):
            it = {"label": it}
        if not isinstance(it, dict) or not str(it.get("label") or "").strip():
            continue
        label = str(it["label"]).strip()
        key = str(it.get("key") or _slug(label))
        while key in seen:
            key += "-2"
        seen.add(key)
        out.append({"key": key, "label": label, "go": str(it.get("go") or "").strip(), "stop": str(it.get("stop") or "").strip()})
    return out


def criteria(content=None, prefs=None, lang="de"):
    """-> [{key, label, go, stop}], most specific source first (see module docstring)."""
    own = ((content or {}).get("entscheidung") or {}).get("kriterien") if isinstance(content, dict) else None
    for source in (own, (prefs or {}).get("decision_criteria")):
        crit = _norm(source)
        if crit:
            return crit
    return [{"key": k, "label": l, "go": g, "stop": s} for k, l, g, s in DEFAULTS.get(lang, DEFAULTS["de"])]


def yardstick(prefs=None, content=None, lang="de"):
    """The user's own yardstick in one or two lines: the process-specific one if the content has it, else built from setup."""
    own = ((content or {}).get("entscheidung") or {}).get("massstab") if isinstance(content, dict) else None
    if own:
        return str(own).strip()
    p = prefs or {}
    en = lang == "en"
    parts = []
    if p.get("goal_label") or p.get("goal_date"):
        parts.append(("Goal: %s by %s" if en else "Ziel: %s bis %s") % (p.get("goal_label") or ("your goal" if en else "dein Ziel"), p.get("goal_date") or ("open" if en else "offen")))
    band = p.get("salary_band") if isinstance(p.get("salary_band"), dict) else {}
    lo, hi, cur = band.get("floor") or p.get("salary_floor"), band.get("target"), band.get("currency") or "€"
    if lo:
        k = lambda v: "%s %dk" % (cur, round(float(v) / 1000))
        try:
            parts.append(("Pay: at least %s" if en else "Gehalt: mindestens %s") % k(lo) + ((", target %s" if en else ", Ziel %s") % k(hi) if hi else ""))
        except (TypeError, ValueError):
            pass
    if p.get("work_mode"):
        parts.append(("Work model: %s" if en else "Arbeitsmodell: %s") % p["work_mode"])
    if p.get("decision_context"):
        parts.append(str(p["decision_context"]).strip())
    return " · ".join(parts)


def verdict(ratings, keys=None, lang="de"):
    """ratings {key: 'go'|'check'|'stop'|''} -> {code, label, go, check, stop, open, total}.
    Any red -> 'stop' (a red criterion is a deal breaker until it is resolved); everything rated, no red, at most one amber -> 'go';
    nothing rated -> 'open'; otherwise 'check'."""
    keys = list(keys) if keys is not None else list((ratings or {}).keys())
    vals = [(ratings or {}).get(k) if (ratings or {}).get(k) in RATINGS else "" for k in keys]
    n = {r: vals.count(r) for r in RATINGS}
    n["open"] = vals.count("")
    if n["stop"]:
        code = "stop"
    elif not any(vals):
        code = "open"
    elif not n["open"] and n["check"] <= 1:
        code = "go"
    else:
        code = "check"
    return dict(code=code, label=VERDICTS.get(lang, VERDICTS["de"])[code], total=len(keys), **n)


def latest_file(role_folder):
    """Newest Entscheidung_*.json in `30 Verlauf` of a role folder -> (path, data) or (None, None)."""
    verlauf = os.path.join(str(role_folder), "30 Verlauf")
    try:
        names = [n for n in os.listdir(verlauf) if FILE_RE.match(n)]
    except OSError:
        return None, None
    best = None
    for n in names:
        p = os.path.join(verlauf, n)
        data = _load_json(p, None)
        if not isinstance(data, dict) or not isinstance(data.get("ratings"), dict):
            continue
        stamp = (str(data.get("saved") or ""), os.path.getmtime(p))
        if best is None or stamp > best[0]:
            best = (stamp, p, data)
    return (best[1], best[2]) if best else (None, None)


def summary(data, lang="de"):
    """A saved matrix file -> verdict over the criteria it was saved with."""
    keys = [c.get("key") for c in data.get("criteria") or [] if isinstance(c, dict) and c.get("key")] or list(data["ratings"].keys())
    v = verdict(data["ratings"], keys, lang)
    v.update(saved=str(data.get("saved") or "")[:10], note=str(data.get("note") or "")[:280])
    return v


def overview(rows, base_dir, lang="de", finder=None):
    """{uid: verdict} for open processes that have a saved matrix in their role folder. Never raises."""
    out = {}
    if finder is None:
        try:
            from folder_utils import locate_role_folder as finder
        except Exception:
            return out
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("stage") == "Closed":
            continue
        try:
            folder, _ = finder(base_dir, str(r.get("uid") or "").strip(), r.get("role") or "", r.get("folder_id") or "")
            if folder is None:
                continue
            path, data = latest_file(folder)
            if data:
                v = summary(data, lang)
                v["file"] = os.path.basename(path)
                out[str(r.get("uid")).strip()] = v
        except Exception:
            continue
    return out


def cockpit_context(row, content=None, prefs=None, lang="de", today=""):
    """What the conversation cockpit needs to render the matrix."""
    crit = criteria(content, prefs, lang)
    company = re.sub(r"[^\w\-]", "_", str((row or {}).get("company") or "Firma"))[:30]
    return {"criteria": crit, "yardstick": yardstick(prefs, content, lang), "lang": lang,
            "filename": "Entscheidung_%s_%s.json" % (company, today or "datum"),
            "uid": str((row or {}).get("uid") or ""), "company": (row or {}).get("company") or "", "role": (row or {}).get("role") or ""}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Latest decision-matrix verdict of a process")
    ap.add_argument("--uid", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--lang", default="de", choices=["de", "en"])
    a = ap.parse_args(argv)
    with open(a.data, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if str(r.get("uid") or "").strip() == str(a.uid).strip()]
    print(json.dumps(overview(rows, a.base_dir, a.lang).get(str(a.uid).strip(), {}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
