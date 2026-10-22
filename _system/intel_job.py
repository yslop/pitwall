#!/usr/bin/env python3
"""
Intel job files (Phase 3 stage B): what a research session must write for a process, in the depth its stage deserves.

  Applied, Screening -> Cheat Sheet (1 page)     Interviewing -> Briefing (3-4 pages)     Final -> Strategy document (2-3 pages)

The job file `Recherche_Auftrag_<Firma>_<Dokument>[_<Person>].md` (in `20 Vorbereitung`) is self-contained, so a Claude session, another agent or
another model can do the research: document type and required sections, inputs (posting, coverage table, earlier intel), research rules (public
sources only, URL and access date for every fact, FACT or INFERENCE for every statement), output names and the lint command.
After an interview, `--after-interview` writes `Nachbereitung_Auftrag_...`: a debrief and the next version of the intel from transcripts and notes.
The system never researches or writes the intel itself and never sends anything.

    python3 intel_job.py --uid 133 [--person "Vorname Nachname"] [--after-interview] [--doc briefing] [--force] [--dry-run]
    python3 intel_job.py --live        every process whose stage needs an intel document that does not exist yet
    python3 intel_job.py --held        every Interviewing/Final process whose conversation date (`due`) has passed and has no debrief yet: writes the after-interview order
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
import intel_index as II
from kit_profile import load_profile
import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = {"cheat_sheet": {"label": "Cheat Sheet", "token": "CheatSheet", "pages": "1 Seite (unter 550 Wörter)", "min_sources": 2, "words_warn": 700,
                        "sections": ["Das Unternehmen in Zahlen", "Eigentümer und Führung", "Warum jetzt", "Mein Blickwinkel", "Fünf Fragen an sie", "Quellen"]},
        "briefing": {"label": "Briefing", "token": "Briefing", "pages": "3 bis 4 Seiten (unter 1800 Wörter)", "min_sources": 3, "words_warn": 2200,
                     "sections": ["Strategie und Finanzbild", "Markt und Wettbewerb", "Organisation und Entscheider", "Risiken", "Was sie von dieser Rolle brauchen",
                                  "Mein Pitch und meine Agenda", "Quellen"]},
        "strategy": {"label": "Strategy-Dokument", "token": "Strategy_Doc", "pages": "2 bis 3 Seiten (unter 1400 Wörter)", "min_sources": 3, "words_warn": 1800,
                     "sections": ["Hypothese für die ersten 100 Tage", "Betriebsmodell", "KPI- und Wertbeitrag", "Risiken und Abhängigkeiten", "Quellen"]}}
JOB_TOKEN = {"cheat_sheet": "Kurzprofil", "briefing": "Lagebild", "strategy": "Konzept"}      # job files must never look like intel files to the intel index
STAGE_DOC = {"Screening": "cheat_sheet", "Interviewing": "briefing", "Final": "strategy"}      # automatic orders start at Screening (owner decision 2026-10-02)
ON_REQUEST_STAGES = {"Applied": "cheat_sheet"}                                                      # Applied: only when asked for (--uid N --doc cheat_sheet)
RANK = {"cheat_sheet": 1, "briefing": 2, "strategy": 3}
KIND_TO_DOC = {"cheat_sheet": "cheat_sheet", "briefing": "briefing", "strategy": "strategy"}
INTEL_NAME = re.compile(r"^(?P<firma>.+?)_(?P<token>CheatSheet|Briefing|Strategy_Doc)(?:_(?P<person>.+?))?_(?P<date>\d{4}-\d{2}-\d{2})_v(?P<v>\d+)\.md$")
TRANSCRIPT = re.compile(r"transkript|transcript|notiz|(?<![a-z])notes?(?![a-z])|protokoll|debrief|(?<![a-z])memo(?![a-z])", re.I)
LIVE_MAX_AGE_DAYS = 30
HELD_STAGES = ("Interviewing", "Final")
HELD_MAX_AGE_DAYS = 14                      # an older date is stale data, not a conversation waiting for its debrief
TALK_WORDS = re.compile(r"gespr(?:[aä]|ae)ch|interview|abendessen|call|termin|treffen|vorstellung", re.I)
DEBRIEF_NAME = re.compile(r"^Debrief_.*?(\d{4}-\d{2}-\d{2})\.md$")


def safe(text, n=40):
    return re.sub(r"[^\w\-]", "_", (text or "").strip())[:n].strip("_") or "x"


def role_files(folder, sub):
    d = os.path.join(str(folder), sub)
    try:
        return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)) and not n.startswith("."))
    except OSError:
        return []


def existing_docs(folder):
    """{doc type: [file names]} of intel files already in the role folder (yours and generated ones), by the same name rules as the intel index."""
    found = {}
    for base in (str(folder), os.path.dirname(str(folder))):                 # the role folder and its employer folder, as the intel index looks
        for sub in ("", "20 Vorbereitung", "30 Verlauf"):
            d = os.path.join(base, sub) if sub else base
            try:
                names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)) and not n.startswith("."))
            except OSError:
                continue
            for n in names:
                doc = KIND_TO_DOC.get(II.classify(n))
                if doc and not n.startswith(("Recherche_Auftrag", "Nachbereitung_Auftrag")):
                    found.setdefault(doc, []).append(n)
    return found


def current_doc(stage, existing):
    """After an interview: the deepest document that exists (it is what the interview informs), else the one the stage calls for."""
    if existing:
        return max(existing, key=lambda d: RANK[d])
    return STAGE_DOC.get(stage)


def needed_doc(stage, existing):
    """The document type this stage calls for, or None when a document of that depth (or a deeper one) is already there."""
    want = STAGE_DOC.get(stage)
    if not want:
        return None
    if any(RANK[d] >= RANK[want] for d in existing):
        return None
    return want


def next_intel_version(folder, doc, person):
    """Next version number for this document (and person) from the generated files' names."""
    import unicodedata
    best, tag = 0, unicodedata.normalize("NFC", safe(person, 30) if person else "")
    for n in role_files(folder, "20 Vorbereitung"):
        m = INTEL_NAME.match(n)
        if m and m.group("token") == DOCS[doc]["token"] and unicodedata.normalize("NFC", m.group("person") or "") == tag:
            best = max(best, int(m.group("v")))
    return best + 1


def build_text(row, uid, folder, base_dir, system, today, language, doc, person, after, target_version):
    exit_path = load_profile(system)["exit_file"] or "00 references/Exit_Narrative.md"
    company, role = row.get("company") or "", row.get("role") or ""
    d = DOCS[doc]
    vorb, bew, verlauf = (os.path.join(str(folder), s) for s in ("20 Vorbereitung", "10 Bewerbung", "30 Verlauf"))
    person_tag = "_" + safe(person, 30) if person else ""
    out_name = "%s_%s%s_%s_v%d.md" % (safe(company or uid, 30), d["token"], person_tag, today, target_version)
    postings = [os.path.join(bew, n) for n in role_files(folder, "10 Bewerbung") if not n.startswith(("CV_", "CL_")) and not re.search(r"_(ATS|CI)\.", n)]
    cov = [os.path.join(vorb, n) for n in role_files(folder, "20 Vorbereitung") if n.startswith("Abdeckung_")]
    earlier = [os.path.join(vorb, n) for n in role_files(folder, "20 Vorbereitung") if II.classify(n) and n.lower().endswith((".md", ".pdf", ".html"))]
    earlier += [os.path.join(verlauf, n) for n in role_files(folder, "30 Verlauf") if II.classify(n)]
    sources = [os.path.join(verlauf, n) for n in role_files(folder, "30 Verlauf") if TRANSCRIPT.search(n) or n.lower().endswith((".txt", ".vtt", ".srt"))]
    head = "Nachbereitungsauftrag" if after else "Rechercheauftrag"
    lang = "Deutsch" if language == "de" else "English"
    o = ["# %s — %s · %s" % (head, company, role), "",
         "Stand %s · uid %s · Stufe **%s** · Dokument: **%s**%s · Sprache: **%s** (folgt der Ausschreibung)" % (today, uid, row.get("stage", ""), d["label"],
                                                                                                  (" für **%s**" % person) if person else "", lang), "",
         "## Ziel"]
    if after:
        o += ["Nach einem Gespräch: (a) einen Debrief schreiben und (b) die nächste Version von %s erstellen, mit dem, was das Gespräch gebracht hat. "
              "Grundlage sind Transkript und Notizen (unten), nicht Vermutungen. **Nichts wird gesendet.**" % d["label"]]
    else:
        o += ["Schreibe %s (%s) so, dass der Bewerber ein Gespräch auf Augenhöhe über Organisation und Markt führen kann. Recherchiere selbst im Web mit öffentlichen Quellen. "
              "**Nichts wird gesendet.**" % (d["label"], d["pages"])]
    o += ["", "## Eingaben (absolute Pfade; lies sie, bevor du schreibst)",
          "- Zeilennotiz (Ansprechpartner, Aufnahmen, Termine): " + ((row.get("note") or "").strip()[:300] or "(keine)"),
          "- Ausschreibung: " + (", ".join("`%s`" % p for p in postings) or "(keine Datei gefunden)"),
          "- Abdeckungstabelle: " + (", ".join("`%s`" % p for p in cov) or "(noch keine)"),
          "- Input Brief (Positionierung des Bewerbers, falls vorhanden): " + (", ".join("`%s`" % os.path.join(vorb, n) for n in role_files(folder, "20 Vorbereitung") if n.startswith("CV_CL_Input_Brief")) or "(keiner)"),
          "- Frühere Intel-Dokumente (nicht wiederholen, weiterentwickeln): " + (", ".join("`%s`" % p for p in earlier) or "(keine)")]
    if after:
        o += ["- Transkripte und Notizen zum Gespräch: " + (", ".join("`%s`" % p for p in sources) or "(keine Datei in 30 Verlauf gefunden: Transkript dort ablegen oder Aufnahme benennen)"),
              "  Eine Aufnahme kann auch ein Gedankenprotokoll oder eine eigene Mitschrift sein. Transkripte und Notizen bleiben in Drive, zitiere sparsam.",
              "- E-Mails und Terminhinweise dieses Verfahrens (Gmail, Kalender), soweit die Sitzung Zugriff hat"]
    o += ["", "## Pflichtabschnitte (Überschriften genau so oder sinngemäß)"] + ["%d. %s" % (i, s) for i, s in enumerate(d["sections"], 1)]
    o += ["Zusätzlich immer: **Offen / nicht verifiziert** (was du nicht belegen oder abrufen konntest, z. B. gesperrte Seiten, Bezahlschranken, fehlende Treffer, ungeprüfte Personen oder Rollen; steht nichts offen, schreibe „keine“)."]
    if after and target_version >= 2:
        o += ["", "Zusätzlich im neuen Dokument: **Änderungen seit v%d** (was neu ist, welche INFERENCE jetzt FACT ist mit Quelle: Transkript und Zeitpunkt oder Notiz, "
              "das Profil des nächsten Gesprächspartners, aktualisierte Fragen)." % (target_version - 1)]
    o += ["", "## Recherche- und Schreibregeln (verbindlich)",
          "1. Nur öffentliche Quellen und die Eingaben oben. Zu Einzelpersonen nur öffentliche berufliche Informationen (Funktion, Werdegang, öffentliche Äußerungen), nichts Privates.",
          "2. **Jede Tatsachenbehauptung mit Quelle:** URL und Abrufdatum (JJJJ-MM-TT) im Abschnitt Quellen, im Text mit [1], [2] verknüpft. Zahlen stehen im selben Absatz wie ihre Quelle.",
          "3. **Jede Aussage im Text ist mit FACT oder INFERENCE gekennzeichnet.** FACT nur mit Quelle; alles andere ist INFERENCE, und sie sagt, worauf sie beruht.",
          "4. Keine erfundenen Zahlen. „Keine Quelle gefunden“ ist eine gültige Antwort. Was sich nicht abrufen oder belegen ließ, steht im Abschnitt „Offen / nicht verifiziert“, nie als FACT.",
          "5. Kein Gehalt, keine Verhandlungstaktik gegen Personen; die Agenda des Bewerbers (Mandat, Wert, Diagnose vor Pitch) steht im Abschnitt Pitch bzw. Hypothese.",
          "6. Die Erzählung zum Ausscheiden nur aus der kanonischen Datei (`%s`), falls sie existiert; sonst dazu nichts erfinden." % exit_path, "",
          "## Ausgabe"]
    if after:
        o += ["- `Debrief_%s_%s.md` in `%s`: was gefragt wurde, was die Gegenseite signalisiert hat, Zusagen und offene Punkte, Nachfassen." % (safe(company, 30), today, verlauf),
              "- **Lernpunkte:** `%s` um wiederkehrende Muster aus dem Gespräch ergänzen (eigenes Verhalten, nicht Fakten über Dritte): Eintrag in `items` mit `id`, `titel`, `problem`, `stattdessen`, `quelle` (Gespräch und Datum). "
              "Bestehende Einträge nur ergänzen, nie löschen; sie speisen „Offene Flanken“ jedes Cockpits." % os.path.join(base_dir, "00 references", "Gespraechs_Playbook.json")]
    o += ["- `%s` in `%s` (Version v%d%s; frühere Versionen nie überschreiben)" % (out_name, vorb, target_version, ", Stand heute" if not after else "")]
    o += ["", "## Prüfen und als PDF ablegen",
          "```bash", "cd \"%s\" && python3 _system/intel_lint.py --uid %s" % (base_dir, uid), "python3 _system/intel_pdf.py --uid %s" % uid, "```",
          "Lint: Exit 0 bestanden, 1 Warnungen (jede prüfen), 2 Fehler (beheben). Das PDF entsteht erst, wenn der Lint keinen Fehler hat.", "",
          "## Abnahme-Checkliste",
          "- [ ] Alle Pflichtabschnitte vorhanden, Länge im Rahmen",
          "- [ ] Jede Aussage mit FACT oder INFERENCE, jedes FACT mit Quelle und Abrufdatum",
          "- [ ] Keine Zahl ohne Quelle im selben Absatz",
          "- [ ] Nur öffentliche berufliche Informationen zu Personen",
          "- [ ] Abschnitt „Offen / nicht verifiziert“ vorhanden (auch „keine“)",
          "- [ ] Lint ohne Fehler, Warnungen geprüft", "",
          "Die Datei kann jederzeit neu erzeugt werden: `python3 _system/intel_job.py --uid %s%s%s --force`." % (uid, (' --person "%s"' % person) if person else "", " --after-interview" if after else ""), ""]
    return "\n".join(o), out_name


def _row(system, uid):
    with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
        return next((r for r in csv.DictReader(f) if C.norm_uid(r.get("uid")) == uid), None)


def run_job(uid, system, base_dir, today, person="", after=False, doc=None, force=False, dry_run=False, locate=None):
    """{'status': 'written'|'current'|'skipped'|'error', 'file', 'doc', 'version'}; never raises for data problems."""
    uid = C.norm_uid(uid)
    if locate is None:
        from folder_utils import locate_role_folder as locate
    try:
        row = _row(system, uid)
        if row is None:
            return {"status": "skipped", "reason": "uid %s nicht in pipeline.csv" % uid}
        stage = (row.get("stage") or "").strip()
        folder, flags = locate(base_dir, uid, row.get("role") or "", row.get("folder_id") or "")
        if folder is None:
            return {"status": "error", "reason": "Rollenordner nicht gefunden: %s" % "; ".join(flags)}
        existing = existing_docs(folder)
        if doc:
            if doc not in DOCS:
                return {"status": "skipped", "reason": "unbekanntes Dokument %s (cheat_sheet, briefing, strategy)" % doc}
            want = doc
        else:
            want = current_doc(stage, existing) if after else needed_doc(stage, existing)
        if not want:
            return {"status": "skipped", "reason": ("Stufe %s: Cheat Sheet nur auf Zuruf (intel_job.py --uid %s --doc cheat_sheet)" % (stage, uid)) if stage in ON_REQUEST_STAGES else ("Stufe %s: kein Intel-Dokument vorgesehen" % stage) if not STAGE_DOC.get(stage) else "Dokument dieser Tiefe ist schon vorhanden"}
        cache = C._read_json(os.path.join(system, "jd_cache.json"), {})
        jd = next((v for k, v in cache.items() if C.norm_uid(k) == uid), "")
        from prep_engine import detect_language
        language = detect_language(jd if isinstance(jd, str) and jd.strip() else row.get("role", ""))
        version = next_intel_version(folder, want, person)
        text, out_name = build_text(row, uid, folder, base_dir, system, today, language, want, person, after, version)
        sig = hashlib.sha256((text.replace(today, "")).encode("utf-8")).hexdigest()
        prefix = "Nachbereitung_Auftrag" if after else "Recherche_Auftrag"
        name = "%s_%s_%s%s.md" % (prefix, safe(row.get("company") or uid, 30), JOB_TOKEN[want], ("_" + safe(person, 30)) if person else "")
        path = os.path.join(str(folder), "20 Vorbereitung", name)
        if dry_run:
            return {"status": "written", "text": text, "file": "", "doc": want, "version": version}
        state_path = os.path.join(system, "intel_state.json")
        state = C._read_state(state_path)
        entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
        jobs = entry.get("jobs") if isinstance(entry.get("jobs"), dict) else {}
        old = jobs.get(name) if isinstance(jobs.get(name), dict) else {}
        if not force and os.path.exists(path) and old.get("sig") == sig:
            return {"status": "current", "file": path, "doc": want, "version": version}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        C._write_atomic(path, text)
        state = C._read_state(state_path)
        entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
        jobs = entry.get("jobs") if isinstance(entry.get("jobs"), dict) else {}
        jobs[name] = {"file": name, "path": path, "date": today, "doc": want, "person": person, "after": bool(after), "version": version, "language": language, "sig": sig}
        entry["jobs"] = jobs
        state[uid] = entry
        C._write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        return {"status": "written", "file": path, "doc": want, "version": version}
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _row_safe(system, uid):
    try:
        return _row(system, C.norm_uid(uid))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def channel_uids(system):
    """Uids that are channels (headhunters) in channels.json: there is no interview to prepare for them."""
    data = C._read_json(os.path.join(system, "channels.json"), {})
    chans = data.get("channels") if isinstance(data, dict) else None
    return {C.norm_uid(k) for k in chans} if isinstance(chans, dict) else set()


def live_uids(system):
    skip = channel_uids(system)
    try:
        with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
            return [C.norm_uid(r.get("uid")) for r in csv.DictReader(f) if (r.get("stage") or "").strip() in STAGE_DOC and C.norm_uid(r.get("uid")) not in skip]
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def held_uids(system, base_dir, today, locate=None):
    """Uids whose conversation took place (`due` before today, at most HELD_MAX_AGE_DAYS ago, `next_action` names a conversation) and
    that have no debrief dated on or after that day. Only the day after counts: on the day itself the conversation may still be ahead."""
    if locate is None:
        from folder_utils import locate_role_folder as locate
    skip = channel_uids(system)
    out = []
    try:
        with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        t = datetime.date.fromisoformat(today)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError):
        return out
    for r in rows:
        uid = C.norm_uid(r.get("uid"))
        if (r.get("stage") or "").strip() not in HELD_STAGES or uid in skip or not TALK_WORDS.search(r.get("next_action") or ""):
            continue
        try:
            due = datetime.date.fromisoformat((r.get("due") or "").strip())
        except ValueError:
            continue
        if not 0 < (t - due).days <= HELD_MAX_AGE_DAYS:
            continue
        folder, _flags = locate(base_dir, uid, r.get("role") or "", r.get("folder_id") or "")
        if folder is None:
            continue
        debriefs = [m.group(1) for n in role_files(folder, "30 Verlauf") for m in [DEBRIEF_NAME.match(n)] if m]
        if not any(d >= due.isoformat() for d in debriefs):
            out.append(uid)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write intel job files for processes that need a cheat sheet, briefing or strategy document.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid")
    g.add_argument("--live", action="store_true")
    g.add_argument("--held", action="store_true", help="after-interview orders for conversations whose date has passed and that have no debrief")
    ap.add_argument("--person", default="")
    ap.add_argument("--after-interview", action="store_true")
    ap.add_argument("--doc", default=None, choices=list(DOCS))
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render", action="store_true", help="refresh the HTML pages afterwards")
    a = ap.parse_args(argv)
    today = a.today or datetime.date.today().isoformat()
    if a.held:
        a.after_interview = True
        a.live = True                                       # a sweep names only rows that need something
        uids = held_uids(a.system, a.base_dir, today)
    else:
        uids = live_uids(a.system) if a.live else [a.uid]
    rc = 0
    for uid in uids:
        results = [run_job(uid, a.system, a.base_dir, today, a.person, a.after_interview, a.doc, a.force, a.dry_run)]
        first = results[0]
        if a.after_interview and not a.doc and first.get("doc"):
            row = _row_safe(a.system, uid)
            deeper = STAGE_DOC.get(((row or {}).get("stage") or "").strip())
            if deeper and RANK[deeper] > RANK[first["doc"]]:            # e.g. Final: update the briefing and also start the strategy document
                results.append(run_job(uid, a.system, a.base_dir, today, a.person, True, deeper, a.force, a.dry_run))
        for res in results:
            if a.live and res["status"] == "skipped":
                continue                                   # a live sweep names only rows that need something
            print("intel_job uid %s: %s%s%s" % (uid, res["status"], " · %s v%d" % (DOCS[res["doc"]]["label"], res["version"]) if res.get("doc") else "",
                                                " · " + res["reason"] if res.get("reason") else ""))
            if a.dry_run and res.get("text"):
                print(res["text"])
            if res["status"] == "error":
                rc = 1
    if a.render and not a.dry_run and rc == 0:
        import subprocess
        r_cmd = [sys.executable, kit_run.script_path(a.system, "render"), "--data", os.path.join(a.system, "pipeline.csv"),
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
