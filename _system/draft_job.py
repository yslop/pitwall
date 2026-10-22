#!/usr/bin/env python3
"""
Draft job file (application path, stage 3): one self-contained brief so that any agent or model can write, or revise, the CV and cover letter.

`Entwurf_Auftrag_<Firma>.md` goes into the role's `20 Vorbereitung`. It names the goal, every input file (with a note when one is missing),
the language, the honesty rules, the output files, the exact lint command, an acceptance checklist and the v2 protocol. It contains no
personal documents, only paths and the requirement table of the coverage step. The system never writes the drafts itself and never sends anything.

CLI:
    python3 draft_job.py --uid 215 [--force]
    python3 draft_job.py --pinned          every pinned row that has a coverage table and no job file yet
    add --dry-run to print the job file and write nothing
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys

import coverage as C
import draft_lint as L

HERE = os.path.dirname(os.path.abspath(__file__))
NARRATIVE = os.path.join("00 references", "Exit_Narrative_AllForLabels_CANONICAL.md")
MASTERS = ("CV_Executive_v2_MASTER.docx", "CL_Executive_v2_MASTER.docx")


def safe(text, n=40):
    return re.sub(r"[^\w\-]", "_", (text or "").strip())[:n].strip("_") or "x"


def existing(path):
    return os.path.exists(path)


def _small(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 999 else 0


def coverage_rows(md):
    """[(Anforderung, Art, Einstufung, Fähigkeit)] from an Abdeckung table."""
    out = []
    for line in (md or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and len(cells) >= 6 and cells[0].isdigit():
            out.append((cells[1], cells[2], cells[3], cells[4]))
    return out


FEEDBACK = re.compile(r"^R(?:ü|ue|u)ckmeldung[ _-]?v(\d+)\.(?:md|txt|gdoc|docx)$", re.I)
NOT_POSTING = ("Rückmeldung", "Rueckmeldung", "Ruckmeldung", "Änderungen", "Aenderungen")


def find_feedback(folder, n):
    """Path of the feedback file for version n (Rückmeldung_v<n>.md/.txt/.gdoc/.docx, also 'Rueckmeldung v<n>'), or None."""
    bew = os.path.join(str(folder), "10 Bewerbung")
    try:
        for name in sorted(os.listdir(bew)):
            m = FEEDBACK.match(name)
            if m and int(m.group(1)) == n:
                return os.path.join(bew, name)
    except OSError:
        pass
    return None


def next_version(folder):
    """(next version number, latest number or 0, feedback path or None) from the drafts and the feedback file of the latest version."""
    drafts = L.find_drafts(folder)
    latest = max(drafts) if drafts else 0
    fb = find_feedback(folder, latest) if latest else None
    return (latest + 1 if fb else max(latest, 1)), latest, fb


def build_text(row, uid, folder, base_dir, system, today, language, prior_lint=None):
    company, role = row.get("company") or "", row.get("role") or ""
    vorb, bew = os.path.join(str(folder), "20 Vorbereitung"), os.path.join(str(folder), "10 Bewerbung")
    tag = "%s_%s" % (safe(company, 30), safe(role, 40))
    target, latest, feedback = next_version(folder)
    cov_files = sorted(n for n in (os.listdir(vorb) if os.path.isdir(vorb) else []) if n.startswith("Abdeckung_") and n.endswith(".md"))
    cov_path = os.path.join(vorb, cov_files[0]) if cov_files else ""
    rows = coverage_rows(L.read_text(cov_path)) if cov_path else []
    briefs = sorted(n for n in (os.listdir(vorb) if os.path.isdir(vorb) else []) if n.startswith("CV_CL_Input_Brief") and n.endswith(".md"))
    postings = sorted(n for n in (os.listdir(bew) if os.path.isdir(bew) else []) if not n.startswith((".", "CV_", "CL_") + NOT_POSTING))
    inputs = [("Ausschreibung (Original, nicht ändern)", [os.path.join(bew, n) for n in postings] or [os.path.join(bew, "(keine Datei gefunden)")]),
              ("Master-Lebenslauf und Master-Anschreiben", [os.path.join(base_dir, "01 templates", m) for m in MASTERS]),
              ("Input Brief (Positionierung, falls vorhanden)", [os.path.join(vorb, n) for n in briefs] or [os.path.join(vorb, "(noch kein CV_CL_Input_Brief)")]),
              ("Abdeckungstabelle", [cov_path or os.path.join(vorb, "(noch keine Abdeckung_*.md: zuerst coverage.py ausführen)")]),
              ("Fähigkeitsprofil (Stufen, Zertifikate, Belege)", [os.path.join(system, "capability_profile.md")]),
              ("Kanonische Austrittserzählung (Leitplanken)", [os.path.join(base_dir, NARRATIVE)])]
    sig_parts = [p for _, paths in inputs for p in paths] + ([feedback] if feedback else [])
    sig = hashlib.sha256("|".join("%s:%s" % (p, os.path.getsize(p) if os.path.isfile(p) else "-") for p in sig_parts).encode("utf-8")).hexdigest()
    out = ["# Entwurfsauftrag — %s · %s" % (company, role), "",
           "Stand %s · uid %s · Sprache der Entwürfe: **%s** (folgt der Ausschreibung)" % (today, uid, "Deutsch, Sie-Form" if language == "de" else "English"), "",
           "## Ziel", "Schreibe einen Lebenslauf und ein Anschreiben für diese Stelle als Markdown-Dateien. Sie sind ein erster Entwurf für den Bewerber; "
           "er überarbeitet und importiert sie selbst nach Google Docs. **Nichts wird gesendet oder eingereicht.**", "", "## Eingaben (alle Pfade absolut; lies sie, bevor du schreibst)"]
    for title, paths in inputs:
        out.append("- %s:" % title)
        for p in paths:
            out.append("  - `%s`%s" % (p, "" if existing(p) or "(" in os.path.basename(p) else "  ← FEHLT"))
    out += ["", "Die Master liegen als .docx vor (Text lesbar); .gdoc-Dateien sind nur Verweise und nicht lesbar. Hinweis: "
            "Das Original der Ausschreibung ist oft ein gedrucktes PDF; der Text steht zusätzlich in der Abdeckungstabelle.", "",
            "## Anforderungen und Einstufung (aus der Abdeckungstabelle)"]
    if rows:
        out += ["| Anforderung | Art | Einstufung | Fähigkeit |", "|---|---|---|---|"] + ["| %s | %s | %s | %s |" % r for r in rows]
    else:
        out.append("Keine Abdeckungstabelle vorhanden: Anforderungen selbst aus der Ausschreibung lesen und jede gegen das Fähigkeitsprofil prüfen. "
                   "Danach `python3 _system/coverage.py --uid %s` ausführen." % uid)
    out += ["", "## Ehrlichkeitsregeln (verbindlich)",
            "1. Jede Aussage muss durch ein Dokument, ein Master oder das Fähigkeitsprofil belegt sein. Nichts erfinden, keine Zahl ohne Beleg.",
            "2. **Gap** wird nicht behauptet: weglassen oder als Lernfeld nennen. **Adjacent**: verwandt benennen, nicht als gleich darstellen. "
            "**In progress**: nur mit dem echten Datum.",
            "3. Zertifikate zählen nur, wenn das Profil `held` sagt. Abgelaufene (z. B. PMP, bis 2019) entweder als abgelaufen benennen oder weglassen.",
            "4. Zum Ausscheiden bei Etikettenwerk nur die kanonische Erzählung verwenden; die Leitplanken „Never claim“ dort sind hart.",
            "5. Die Empfehlungsangebote (Referenzen) nur so, wie die kanonische Erzählung sie erlaubt.",
            "6. Gehalt und Homeoffice kommen im Anschreiben nicht vor.", "",
            "## Ausgabe",
            "- `%s` und `%s` in `%s`" % ("CV_%s_v%d.md" % (tag, target), "CL_%s_v%d.md" % (tag, target), bew),
            "- Anschreiben: eine Seite (unter %d Wörter), persönliche Anrede mit Namen, wenn auffindbar, kein „Hiermit bewerbe ich mich“." % L.CL_WARN_WORDS, "",
            "## Prüfen (vor der Übergabe)",
            "```bash", "cd \"%s\" && python3 _system/draft_lint.py --uid %s --version v%d" % (base_dir, uid, target), "```",
            "Exit-Code 0 = bestanden, 1 = Warnungen (jede prüfen und im Entwurf begründen oder beheben), 2 = Fehler (beheben, neu prüfen). "
            "Das Ergebnis wird in `draft_state.json` festgehalten.", "",
            "## Abnahme-Checkliste",
            "- [ ] Alle Muss-Anforderungen mit Einstufung Proven kommen im Lebenslauf oder Anschreiben mit Beleg vor",
            "- [ ] Keine Gap-Anforderung wird als vorhanden dargestellt",
            "- [ ] Zertifikate und Zahlen stimmen mit Profil und Master überein",
            "- [ ] Sprache und Anrede passen zur Ausschreibung",
            "- [ ] Lint ohne Fehler, Warnungen geprüft", "",
            "## Version 2 und höher",
            "Wenn `Rückmeldung_v<N>.md` neben den Entwürfen in `10 Bewerbung` oder `.gdoc`/`.docx` liegt (die Rückmeldung des Bewerbers zu v<N>): schreibe `_v<N+1>` und gehe "
            "auf jeden Punkt ein. **Überschreibe nie eine frühere Version.** Lege zusätzlich `Änderungen_v<N+1>.md` an: was geändert wurde, warum, "
            "und was bewusst nicht übernommen wurde.", "",
            "## Stand beim Erzeugen dieser Datei",
            "- Vorhandene Entwurfsversionen: %s" % (", ".join("v%d" % n for n in sorted(L.find_drafts(folder))) or "keine"),
            "- Rückmeldung vorhanden: %s" % (os.path.basename(feedback) if feedback else "nein"),
            "- Zu schreibende Version: **v%d**" % target]
    if latest == target and latest:
        out.append("- **v%d existiert bereits.** Nur überarbeiten, wenn der Bewerber es verlangt; eine neue Version erst, wenn `Rückmeldung_v%d` neben den Entwürfen liegt." % (latest, latest))
    if prior_lint:
        out.append("- Letztes Lint-Ergebnis: %s" % prior_lint)
    out += ["", "Die Datei kann jederzeit neu erzeugt werden: `python3 _system/draft_job.py --uid %s --force`." % uid, ""]
    return "\n".join(out), target, sig


def run_job(uid, system, base_dir, today, force=False, dry_run=False, locate=None):
    """{'status': 'written'|'current'|'skipped'|'error', ...}; a row needs a coverage table first (advice, not a block: 'skipped' names why)."""
    uid = C.norm_uid(uid)
    if locate is None:
        from folder_utils import locate_role_folder as locate
    try:
        row = None
        with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
            row = next((r for r in csv.DictReader(f) if C.norm_uid(r.get("uid")) == uid), None)
        if row is None:
            return {"status": "skipped", "reason": "uid %s nicht in pipeline.csv" % uid}
        folder, flags = locate(base_dir, uid, row.get("role") or "", row.get("folder_id") or "")
        if folder is None:
            return {"status": "error", "reason": "Rollenordner nicht gefunden: %s" % "; ".join(flags)}
        vorb = os.path.join(str(folder), "20 Vorbereitung")
        if not any(n.startswith("Abdeckung_") for n in (os.listdir(vorb) if os.path.isdir(vorb) else [])):
            return {"status": "skipped", "reason": "keine Abdeckungstabelle (zuerst coverage.py)"}
        cache = C._read_json(os.path.join(system, "jd_cache.json"), {})
        jd = next((v for k, v in cache.items() if C.norm_uid(k) == uid), "")
        from prep_engine import detect_language
        language = detect_language(jd if isinstance(jd, str) and jd.strip() else row.get("role", ""))
        state_path = os.path.join(system, "draft_state.json")
        state = C._read_json(state_path, {})
        entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
        versions = entry.get("versions") if isinstance(entry.get("versions"), dict) else {}
        key = entry.get("latest") if isinstance(entry.get("latest"), str) else ""
        latest = versions.get(key) if isinstance(versions.get(key), dict) else {}
        prior = None
        if isinstance(latest.get("result"), str):
            prior = "%s: %s (%s Fehler, %s Warnungen)" % (key, {"pass": "bestanden", "warn": "Warnungen", "fail": "Fehler"}.get(latest["result"], "unbekannt"),
                                                        _small(latest.get("fails")), _small(latest.get("warns")))
        text, target, sig = build_text(row, uid, folder, base_dir, system, today, language, prior)
        name = "Entwurf_Auftrag_%s.md" % safe(row.get("company", "") or uid, 40)
        path = os.path.join(vorb, name)
        if dry_run:
            return {"status": "written", "text": text, "file": "", "version": target}
        job_entry = entry.get("job") if isinstance(entry.get("job"), dict) else {}
        if not force and os.path.exists(path) and job_entry.get("version") == target and job_entry.get("sig") == sig:
            return {"status": "current", "file": path, "version": target}
        C._write_atomic(path, text)
        state = C._read_json(state_path, {})
        entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
        entry["job"] = {"file": name, "path": path, "date": today, "version": target, "language": language, "sig": sig}
        state[uid] = entry
        C._write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        return {"status": "written", "file": path, "version": target}
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the draft job file for a pinned row.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid")
    g.add_argument("--pinned", action="store_true")
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render", action="store_true", help="refresh the HTML pages afterwards")
    a = ap.parse_args(argv)
    today = a.today or datetime.date.today().isoformat()
    uids = [a.uid]
    if a.pinned:
        from top10 import load
        uids = [str(u) for u in load(os.path.join(a.system, "top10.json")).get("pinned", [])]
    rc = 0
    for uid in uids:
        res = run_job(uid, a.system, a.base_dir, today, force=a.force, dry_run=a.dry_run)
        print("draft_job uid %s: %s%s%s" % (uid, res["status"], " · v%d" % res["version"] if res.get("version") else "", " · " + res["reason"] if res.get("reason") else ""))
        if a.dry_run and res.get("text"):
            print(res["text"])
        if res["status"] == "error":
            rc = 1
    if a.render and not a.dry_run and rc == 0:
        import subprocess
        r_cmd = [sys.executable, os.path.join(a.system, "render.py"), "--data", os.path.join(a.system, "pipeline.csv"),
                 "--prep", os.path.join(a.system, "prep.json"), "--folders", os.path.join(a.system, "folders.tsv"),
                 "--today", today, "--out", a.base_dir]
        r = subprocess.run(r_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("  ! render.py fehlgeschlagen (Code %s): %s" % (r.returncode, (r.stderr or "").strip()[-400:]), file=sys.stderr)
            return 2
        print("  Seiten aktualisiert")
    return rc


if __name__ == "__main__":
    sys.exit(main())
