#!/usr/bin/env python3
"""Load the customer's job-search history from a CSV into pipeline.csv: preview first, append only, never overwrite.

    python3 _system/kit_import.py verlauf.csv                # preview (writes nothing)
    python3 _system/kit_import.py verlauf.csv --apply        # append the new rows, create the folders, rebuild the pages

Columns are found by name (German or English): company/Firma, role/Position, status, applied/Beworben am, last contact/Letzter Kontakt,
location/Ort, note/Notiz. company and role are required. Excel, Notion, e-mails or notes are turned into this CSV by the AI application
(see ONBOARDING.md); the template is kit_examples/history_import.example.csv. Python 3.9 compatible.
"""
import argparse
import csv
import datetime
import os
import re
import sys

import kit_demo
import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))
SYNONYMS = {
    "company": ("company", "firma", "unternehmen", "arbeitgeber", "employer"),
    "role": ("role", "rolle", "position", "stelle", "titel", "jobtitel", "title", "job"),
    "status": ("status", "stufe", "stage", "stand"),
    "applied": ("applied", "appliedon", "applieddate", "beworbenam", "beworben", "bewerbungsdatum", "bewerbungam"),
    "last_event": ("lastevent", "lastcontact", "letzterkontakt", "letztekontakt", "letzteaktivitaet", "letzteaktivität"),
    "location": ("location", "ort", "standort"),
    "note": ("note", "notes", "notiz", "notizen", "bemerkung", "kommentar"),
}
HEADER_FALLBACK = ["uid", "company", "role", "lane", "stage", "outcome", "applied", "last_event", "days_idle", "score", "boost", "salary_fit",
                   "location", "contacts", "folder_id", "next_action", "due", "note", "ts_confidence", "ts_fit_score"]
WITHDRAWN = ("zurückgezogen", "zurueckgezogen", "withdrawn", "selbst abgesagt", "habe abgesagt", "declined")
REJECTED = ("absage", "rejected", "abgelehnt", "nicht berücksichtigt", "nicht beruecksichtigt", "rejection", "negativ")
FINAL = ("angebot", "offer", "vertrag", "zusage")
SCREENING = ("telefon", "screening", "recruiter", "erstgespr", "vorgespr", "kennenlern", "hr-", "phone")
INTERVIEWING = ("interview", "vorstellungsgespr", "gespräch", "gespraech", "assessment", "runde", "fachgespr", "panel")
APPLIED = ("beworben", "applied", "eingereicht", "versendet", "bewerbung", "abgeschickt")
WATCHLIST = ("interessant", "merk", "watch", "idee", "später", "spaeter", "beobacht")


class ImportError_(Exception):
    pass


def _norm_header(h):
    return re.sub(r"[\s_\-./]+", "", (h or "").strip().lower())


def _has(text, words):
    t = text.lower()
    t2 = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return any(w in t or w in t2 for w in words)


def map_status(text):
    """(stage, outcome, unknown): closed first, then the deepest stage the words name."""
    t = (text or "").strip()
    if not t:
        return "Applied", "", True
    if _has(t, WITHDRAWN):
        return "Closed", "withdrawn", False
    if _has(t, REJECTED):
        return "Closed", "rejected", False
    if _has(t, FINAL):
        return "Final", "", False
    if _has(t, SCREENING):
        return "Screening", "", False
    if _has(t, INTERVIEWING):
        return "Interviewing", "", False
    if _has(t, APPLIED):
        return "Applied", "", False
    if _has(t, WATCHLIST):
        return "Watchlist", "", False
    return "Applied", "", True


def parse_date(text):
    t = (text or "").strip()
    for pattern, order in ((r"^(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"), (r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", "dmy"), (r"^(\d{1,2})/(\d{1,2})/(\d{4})$", "dmy")):
        m = re.match(pattern, t)
        if m:
            a, b, c = (int(x) for x in m.groups())
            try:
                d = datetime.date(a, b, c) if order == "ymd" else datetime.date(c, b, a)
            except ValueError:
                return ""
            return d.isoformat()
    return ""


def _key(company, role):
    return (re.sub(r"[^a-z0-9äöüß]", "", (company or "").lower()), re.sub(r"[^a-z0-9äöüß]", "", (role or "").lower()))


def _safe(text, n=60):
    t = re.sub(r'[\\/:*?"<>|]+', "-", (text or "").strip())
    return re.sub(r"\s+", " ", t).strip(" .-")[:n] or "x"


def _read_pipeline(system_dir):
    path = os.path.join(system_dir, "pipeline.csv")
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader.fieldnames or HEADER_FALLBACK), list(reader)
    except OSError:
        return list(HEADER_FALLBACK), []


def _read_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise ImportError_("Datei nicht lesbar: %s" % e)
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise ImportError_("Die Datei ist leer.")
    columns = {}
    for h in reader.fieldnames:
        for canon, names in SYNONYMS.items():
            if _norm_header(h) in names and canon not in columns:
                columns[canon] = h
    missing = [c for c in ("company", "role") if c not in columns]
    if missing:
        raise ImportError_("Pflichtspalten fehlen: %s (gefunden: %s). Siehe kit_examples/history_import.example.csv." % (", ".join(missing), ", ".join(reader.fieldnames)))
    return columns, list(reader)


def plan(csv_path, system_dir, today):
    system_dir = os.path.abspath(system_dir)
    columns, lines = _read_csv(csv_path)
    header, existing = _read_pipeline(system_dir)
    seen = {_key(r.get("company"), r.get("role")) for r in existing}
    nums = [int(r["uid"]) for r in existing if str(r.get("uid", "")).strip().isdigit() and int(r["uid"]) < 9000 and not kit_demo.is_demo_row(r)]
    next_uid = (max(nums) if nums else 0) + 1
    rows, skipped, warnings = [], [], []
    day = datetime.date.fromisoformat(today)
    for n, line in enumerate(lines, 2):
        get = lambda c: (line.get(columns[c]) or "").strip() if c in columns else ""
        company, role = get("company"), get("role")
        if not company or not role:
            warnings.append("Zeile %d übersprungen: Firma oder Rolle fehlt" % n)
            continue
        if _key(company, role) in seen:
            skipped.append("%s · %s (schon vorhanden)" % (company, role))
            continue
        seen.add(_key(company, role))
        stage, outcome, unknown = map_status(get("status"))
        if unknown:
            warnings.append("Zeile %d: Status „%s“ nicht erkannt, als Applied angelegt" % (n, get("status")))
        applied, last = parse_date(get("applied")), parse_date(get("last_event"))
        for label, raw, parsed in (("Beworben-am", get("applied"), applied), ("Letzter Kontakt", get("last_event"), last)):
            if raw and not parsed:
                warnings.append("Zeile %d: %s „%s“ nicht lesbar, leer gelassen" % (n, label, raw))
        last = last or applied
        idle = str((day - datetime.date.fromisoformat(last)).days) if last else ""
        rows.append({"uid": str(next_uid), "company": company, "role": role, "lane": "", "stage": stage, "outcome": outcome, "applied": applied, "last_event": last,
                     "days_idle": idle, "score": "0", "boost": "0", "salary_fit": "", "location": get("location"), "contacts": "", "folder_id": "",
                     "next_action": "", "due": "", "note": get("note")[:500], "ts_confidence": "", "ts_fit_score": ""})
        next_uid += 1
    return {"rows": rows, "skipped": skipped, "warnings": warnings, "header": header}


def apply(csv_path, system_dir, today):
    system_dir = os.path.abspath(system_dir)
    base = os.path.dirname(system_dir)
    p = plan(csv_path, system_dir, today)
    if p["rows"]:
        path = os.path.join(system_dir, "pipeline.csv")
        with open(path, "a+", newline="", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(f.tell() - 1)
                if f.read(1) != "\n":
                    f.write("\n")
            w = csv.DictWriter(f, fieldnames=p["header"], extrasaction="ignore")
            for r in p["rows"]:
                w.writerow(r)
        for r in p["rows"]:
            role_dir = os.path.join(base, "%s %s" % (r["uid"], _safe(r["company"])), _safe(r["role"]))
            for sub in ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf"):
                os.makedirs(os.path.join(role_dir, sub), exist_ok=True)
    return {"added": len(p["rows"]), "skipped": p["skipped"], "warnings": p["warnings"], "rows": p["rows"]}


def main(argv=None):
    import subprocess
    ap = argparse.ArgumentParser(description="Import the job-search history from a CSV (preview unless --apply).")
    ap.add_argument("csv")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    try:
        res = apply(a.csv, HERE, a.today) if a.apply else dict(plan(a.csv, HERE, a.today), added=0)
    except ImportError_ as e:
        print("Abbruch:", e, file=sys.stderr)
        return 2
    rows = res["rows"]
    print("%s: %d neue Zeilen" % ("Angelegt" if a.apply else "Vorschau (nichts geschrieben)", len(rows)))
    for r in rows:
        print("  %-5s %-36s %-30s %s%s" % (r["uid"], r["company"][:36], r["role"][:30], r["stage"], "/" + r["outcome"] if r["outcome"] else ""))
    for s in res["skipped"]:
        print("  übersprungen:", s)
    for w in res["warnings"]:
        print("  Hinweis:", w)
    if not a.apply:
        print("Zum Übernehmen: ./pitwall kit_import %s --apply" % a.csv)
        return 0
    subprocess.run(kit_run.script_cmd(HERE, "intel_index") + ["--data", "pipeline.csv"], cwd=HERE, capture_output=True, text=True)
    import kit_setup
    print("Seiten gerendert" if kit_setup.render(HERE, a.today) == 0 else "render.py fehlgeschlagen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
