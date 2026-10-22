#!/usr/bin/env python3
"""Two fictional demo processes so that the pages are populated before the first real run.

Every file says DEMO and every source is a reserved example domain. `add` writes rows, folders, documents and the rendered prep pages;
`remove` archives only what `add` wrote (a marker file lists it) to <base>/_Archiv/ and never touches a file of the customer; the engine never deletes.

    python3 _system/kit_demo.py --add | --remove [--today YYYY-MM-DD]
"""
import argparse
import csv
import datetime
import json
import os
import shutil
import sys

import kit_run
from kit_profile import load_profile

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_UIDS = ("9001", "9002")
MARKER = ".star_demo"
HEADER_FALLBACK = ["uid", "company", "role", "lane", "stage", "outcome", "applied", "last_event", "days_idle", "score", "boost", "salary_fit",
                   "location", "contacts", "folder_id", "next_action", "due", "note", "ts_confidence", "ts_fit_score"]
NOTE = "DEMO: erfundene Beispieldaten. Entfernen mit ./star kit_demo --remove"

PROCESSES = [
    {"uid": "9001", "company": "Beispiel Maschinenbau AG", "role": "Head of Data", "stage": "Interviewing", "lane": "Data/AI Arch", "score": "72",
     "applied_ago": 21, "event_ago": 2, "due_in": 5, "next_action": "Gespräch mit Frau Beispiel vorbereiten (Demo)", "kind": "briefing"},
    {"uid": "9002", "company": "Beispiel Versicherung SE", "role": "Director IT Strategy", "stage": "Screening", "lane": "IT Leadership", "score": "58",
     "applied_ago": 8, "event_ago": 3, "due_in": 9, "next_action": "Antwort des Recruiters abwarten (Demo)", "kind": "cheat_sheet"},
]


def _briefing(today):
    return """# Briefing — Beispiel Maschinenbau AG · Head of Data (Demo)

**DEMO: Alle Inhalte sind erfunden und nur Anschauungsmaterial. Entfernen mit `./star kit_demo --remove`.**

## 1. Strategie und Finanzbild
- FACT: Die fiktive Beispiel Maschinenbau AG setzte 2025 rund 420 Mio. € um und beschäftigt etwa 1.800 Mitarbeitende [1].
- INFERENCE (aus [1]): Ein Hersteller dieser Größe hat meist gewachsene Datenlandschaften in Werken und Vertrieb.
- INFERENCE (aus [2]): Die Geschäftsführung will Daten für Qualität und Lieferfähigkeit nutzen, nicht für Berichte allein.

## 2. Markt und Wettbewerb
- FACT: Im Beispielmarkt für Fertigungsautomation wächst der Umsatz laut der erfundenen Branchenstudie um 4 % pro Jahr [3].
- INFERENCE (aus [3]): Wachstum bei knappen Fachkräften erhöht den Druck, Planung und Qualität über Daten zu steuern.

## 3. Organisation und Entscheider
- FACT: Die Stelle berichtet laut Anzeige an die Geschäftsführung Technik (Frau Beispiel) [2].
- INFERENCE (aus [2]): Frau Beispiel entscheidet über Budget und Zuschnitt; ein Folgegespräch mit ihr ist das Ziel dieser Runde.

## 4. Risiken
- INFERENCE (aus [2]): Das Datenteam ist neu, Budget und Teamgröße sind nicht genannt, das Mandat kann sich verschieben.
- INFERENCE (aus [3]): Ein Lieferantenwechsel im ERP bindet die Fachbereiche und kann Datenprojekte bremsen.

## 5. Was sie von dieser Rolle brauchen
- FACT: Die Anzeige verlangt Data Governance, Plattformaufbau und Übersetzung zwischen Technik und Geschäftsleitung [2].
- INFERENCE (aus [2]): Gesucht ist jemand, der erst Ordnung schafft und dann wenige sichtbare Anwendungsfälle liefert.

## 6. Mein Pitch und meine Agenda
- INFERENCE (Agenda): Erst zuhören, wie die Rolle zugeschnitten ist, dann einen Vorschlag für die ersten 90 Tage machen.
- INFERENCE (Pitch): Fundament vor Effekten: Datenqualität und Governance zuerst, dann zwei priorisierte Anwendungsfälle.

## Offen / nicht verifiziert
- INFERENCE (aus der Recherche): Budget und Teamgröße der Rolle sind nicht öffentlich.
- INFERENCE (aus der Recherche): Wer neben Frau Beispiel im Gespräch sitzt, ist nicht bestätigt.

## Quellen
[1] Beispiel Maschinenbau AG: Geschäftsbericht 2025 (erfunden) — https://example.org/beispiel-maschinenbau/geschaeftsbericht-2025 — abgerufen {today}
[2] Beispiel Maschinenbau AG: Stellenanzeige Head of Data (erfunden) — https://example.com/karriere/head-of-data — abgerufen {today}
[3] Beispiel-Branchenverband: Marktstudie Fertigungsautomation (erfunden) — https://example.net/studien/fertigungsautomation — abgerufen {today}
""".replace("{today}", today)


def _cheat_sheet(today):
    return """# Cheat Sheet — Beispiel Versicherung SE · Director IT Strategy (Demo)

**DEMO: Alle Inhalte sind erfunden und nur Anschauungsmaterial. Entfernen mit `./star kit_demo --remove`.**

## Das Unternehmen in Zahlen
- FACT: Die fiktive Beispiel Versicherung SE hat rund 2,1 Mio. Kunden und etwa 3.400 Mitarbeitende [1].
- INFERENCE (aus [1]): Eine Versicherung dieser Größe betreibt viele Altsysteme neben neuen Plattformen.

## Eigentümer und Führung
- FACT: Das Unternehmen gehört zu einer erfundenen Beispiel-Holding, der Vorstand IT heißt Herr Muster [2].
- INFERENCE (aus [2]): Die Rolle liegt nahe am Vorstand, die Entscheidung trifft Herr Muster.

## Warum jetzt
- INFERENCE (aus [2]): Die Anzeige ist neu; eine Neuorganisation der IT-Strategie wird vorbereitet.

## Mein Blickwinkel
- INFERENCE (Pitch): Strategie in prüfbare Schritte übersetzen: Zielbild, Roadmap und zwei schnelle Ergebnisse.

## Fünf Fragen an sie
1. INFERENCE (Frage): Welches Problem soll die Rolle in den ersten sechs Monaten lösen?
2. INFERENCE (Frage): Wie ist die IT-Strategie heute mit dem Vorstand verbunden?
3. INFERENCE (Frage): Welche Altsysteme bremsen am meisten?
4. INFERENCE (Frage): Wie sieht der weitere Prozess aus und wer entscheidet?
5. INFERENCE (Frage): Woran messen Sie den Erfolg nach einem Jahr?

## Offen / nicht verifiziert
- INFERENCE (aus der Recherche): Die Berichtslinie der Rolle ist nicht bestätigt.

## Quellen
[1] Beispiel Versicherung SE: Unternehmensprofil (erfunden) — https://example.org/beispiel-versicherung/profil — abgerufen {today}
[2] Beispiel Versicherung SE: Stellenanzeige Director IT Strategy (erfunden) — https://example.com/karriere/director-it-strategy — abgerufen {today}
""".replace("{today}", today)


def _prep_inhalt():
    return {
        "lang": "de", "source": "Demo",
        "company_snapshot": "DEMO: Beispiel Maschinenbau AG (erfunden), rund 420 Mio. € Umsatz, etwa 1.800 Mitarbeitende. Wachsende Fertigungsautomation mit gewachsener Datenlandschaft.",
        "strategic_context": "DEMO: Die Rolle Head of Data baut ein neues Datenteam auf und soll erst Ordnung schaffen, dann wenige sichtbare Anwendungsfälle liefern.",
        "contacts": [
            {"name": "Frau Beispiel", "title": "Geschäftsführung Technik (erfunden)", "background": "Entscheidet über Budget und Zuschnitt; ein Folgegespräch mit ihr ist das Ziel.",
             "language_note": "Sachlich, konkret, Zahlen vor Folien.", "open_question": "Wie sehen Sie die ersten zwölf Monate der Rolle?"},
            {"name": "Herr Muster", "title": "Leiter Personal (erfunden)", "background": "Organisiert den Prozess, kein Fachgespräch.", "open_question": "Wie läuft der weitere Prozess?"}],
        "keyfacts": {"diagnosed_pain": "Daten sind in Werken und Vertrieb verteilt; es fehlt ein gemeinsames Fundament.",
                   "value_statement": "Governance und Datenqualität zuerst, danach zwei priorisierte Anwendungsfälle. Ihre Metrik: Lieferfähigkeit und Ausschussquote.",
                   "followup_sent": "Nein — nach dem Gespräch ein kurzes Follow-up mit Diagnose und Vorschlag.", "agenda_artifact": "Agenda in vier Schritten: Rolle, Mandat, erste Priorität, nächster Schritt."},
        "open_hook": "Bevor ich etwas erzähle, würde ich gern verstehen, wie Sie die Rolle zuschneiden.",
        "close_hook": "Gern vertiefe ich das in einem Folgegespräch mit einem konkreten Beispiel.",
        "questions": [
            {"rank": 1, "question": "Wie ist die Rolle organisatorisch verankert, und woran berichte ich?", "to": "Frau Beispiel", "why": "Mandat und Budget bestimmen den Erfolg."},
            {"rank": 2, "question": "Welche Datenprobleme kosten heute am meisten Zeit oder Geld?", "to": "Frau Beispiel", "why": "Zeigt die erste Priorität."},
            {"rank": 3, "question": "Wie ist das Datenteam heute aufgestellt?", "to": "Frau Beispiel", "why": "Teamgröße ist nicht öffentlich."},
            {"rank": 4, "question": "Woran messen Sie den Erfolg nach zwölf Monaten?", "to": "beide", "why": "Macht den Erfolgsmaßstab sichtbar."}],
        "open_items": ["DEMO: Budget und Teamgröße der Rolle sind nicht öffentlich.", "DEMO: Wer neben Frau Beispiel im Gespräch sitzt, ist nicht bestätigt."],
        "intel": {"snapshot": [{"label": "Stufe", "value": "Interviewing (Demo)"}, {"label": "Umsatz", "value": "rund 420 Mio. € (erfunden)"}],
                  "diagnosed_pain": "Verteilte Daten ohne gemeinsames Fundament. (Demo)", "decision_maker": "Frau Beispiel (erfunden)", "scope_signal": "Neues Datenteam, Größe offen",
                  "salary_estimate": "nicht öffentlich", "anchoring_note": "Erst Mandat und Wert klären.",
                  "jd_bullets": ["Data Governance und Plattformaufbau", "Übersetzung zwischen Technik und Geschäftsleitung", "Priorisierung datengetriebener Anwendungsfälle"]},
        "cockpit": {
            "termin": "DEMO: in fünf Tagen, Videogespräch",
            "lage": {"lede": "DEMO: Erstes Fachgespräch mit der Geschäftsführung Technik. Es geht um Zuschnitt und Mandat der neuen Rolle.",
                     "karten": [{"titel": "Was gewonnen ist", "text": "Die Einladung steht, die Rolle ist neu."}, {"titel": "Was offen ist", "text": "Budget, Teamgröße, Berichtslinie."},
                                {"titel": "Was entscheidet", "text": "Ob dein Vorschlag für die ersten 90 Tage trägt."}]},
            "vorschlag": {"satz": "Für die ersten 90 Tage: Datenqualität und Governance zuerst, danach zwei priorisierte Anwendungsfälle mit sichtbarem Nutzen."},
            "fuehrung": {"einstieg": "Bevor ich etwas erzähle, würde ich gern verstehen, wie Sie die Rolle zuschneiden.",
                         "bewegungen": [{"titel": "Zuhören", "text": "Mandat und Budget verstehen."}, {"titel": "Vorschlag", "text": "Die ersten 90 Tage skizzieren."},
                                        {"titel": "Landen", "text": "Folgegespräch anbieten."}]},
            "flanken": [{"titel": "Zeitdruck", "problem": "Verfügbarkeit nicht mehrfach anbieten.", "stattdessen": "Ein Satz, nur auf Nachfrage."}],
            "faktenhygiene": {"belegt": ["Alle Angaben in diesem Beispiel sind erfunden (Demo)."], "unbelegt": ["Budget und Teamgröße der Rolle"]},
            "vorher": [{"titel": "Technik prüfen", "text": "Kamera, Ton, zehn Minuten vorher im Raum."}, {"titel": "Bio lesen", "text": "30-Sekunden-Vorstellung aus deinen Bausteinen."}],
            "bio": {"kurz": "DEMO: Hier steht deine 30-Sekunden-Vorstellung, gebaut nur aus deinen geprüften Bausteinen in 00 references/Bio_Bausteine.json.",
                    "lang": "DEMO: Hier steht deine 90-Sekunden-Vorstellung für diese Rolle.", "anker": ["Ordnung in verteilte Daten", "Governance von Anfang an", "Wenige sichtbare Ergebnisse"],
                    "bezug": "Auf die Erwartung der Geschäftsführung Technik eingehen: Fundament zuerst.", "nicht_sagen": ["Keine Erfahrung behaupten, die nicht belegt ist."]},
            "panik": [{"frage": "„Warum diese Rolle?“", "antwort": "Weil Daten hier Fundament für Qualität und Lieferfähigkeit sind."},
                      {"frage": "„Was erwartest du finanziell?“", "antwort": "Die vorher festgelegte Spanne einmal nennen, dann schweigen."}]}}


def _header(system_dir):
    path = os.path.join(system_dir, "pipeline.csv")
    try:
        with open(path, newline="", encoding="utf-8") as f:
            head = next(csv.reader(f), None)
        return head or list(HEADER_FALLBACK)
    except OSError:
        return list(HEADER_FALLBACK)


def _read_rows(system_dir):
    try:
        with open(os.path.join(system_dir, "pipeline.csv"), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _write_rows(system_dir, header, rows):
    with open(os.path.join(system_dir, "pipeline.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def is_demo_row(row):
    return str(row.get("uid", "")).strip() in DEMO_UIDS and str(row.get("note", "")).startswith("DEMO")


def is_demo_uid(uid):
    return str(uid).strip() in DEMO_UIDS


def _iso(today, days):
    return (datetime.date.fromisoformat(today) + datetime.timedelta(days=days)).isoformat()


def add(system_dir, today=None):
    system_dir = os.path.abspath(system_dir)
    base = os.path.dirname(system_dir)
    today = today or datetime.date.today().isoformat()
    header, rows = _header(system_dir), _read_rows(system_dir)
    have = {r.get("uid") for r in rows}
    created, kept = [], []
    for p in PROCESSES:
        folder = os.path.join(base, "%s %s (Demo)" % (p["uid"], p["company"]))
        marker = os.path.join(folder, MARKER)
        if p["uid"] in have or os.path.exists(marker):
            kept.append(folder)
            continue
        role_dir = os.path.join(folder, p["role"])
        for sub in ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf"):
            os.makedirs(os.path.join(role_dir, sub), exist_ok=True)
        vor = os.path.join(role_dir, "20 Vorbereitung")
        files = []
        token = p["company"].replace(" ", "_")
        if p["kind"] == "briefing":
            name = "%s_Briefing_%s_v1.md" % (token, today)
            text = _briefing(today)
        else:
            name = "%s_CheatSheet_%s_v1.md" % (token, today)
            text = _cheat_sheet(today)
        with open(os.path.join(vor, name), "w", encoding="utf-8") as f:
            f.write(text)
        files.append(os.path.join(vor, name))
        if p["kind"] == "briefing":
            with open(os.path.join(vor, "Prep_Inhalt.json"), "w", encoding="utf-8") as f:
                json.dump(_prep_inhalt(), f, ensure_ascii=False, indent=2)
            files.append(os.path.join(vor, "Prep_Inhalt.json"))
        rows.append({"uid": p["uid"], "company": p["company"], "role": p["role"], "lane": p["lane"], "stage": p["stage"], "applied": _iso(today, -p["applied_ago"]),
                     "last_event": _iso(today, -p["event_ago"]), "days_idle": str(p["event_ago"]), "score": p["score"], "boost": "0", "salary_fit": "mid",
                     "next_action": p["next_action"], "due": _iso(today, p["due_in"]), "note": NOTE, "ts_fit_score": "0.6"})
        created.append(folder)
        _write_rows(system_dir, header, rows)
        if p["kind"] == "briefing":
            import prep_engine
            res = prep_engine.render_from_content(p["uid"], os.path.join(system_dir, "pipeline.csv"), base, today, profile=load_profile(system_dir))
            files += res["files"]
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"files": [os.path.relpath(x, folder).replace(os.sep, "/") for x in files], "uid": p["uid"]}, f, ensure_ascii=False, indent=2)
    return {"created": created, "kept": kept}


def archive(system_dir):
    """Take the demo out of the working folder by archiving (the engine never deletes): a demo folder that holds only demo files moves
    as a whole to <base>/_Archiv/Demo-<time>/; if the customer put files into it, only the demo's own files move and the rest stays."""
    system_dir = os.path.abspath(system_dir)
    base = os.path.dirname(system_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = os.path.join(base, "_Archiv", "Demo-" + stamp)
    archived, kept = [], []
    for name in sorted(os.listdir(base)):
        folder = os.path.join(base, name)
        marker = os.path.join(folder, MARKER)
        if not (name[:4] in DEMO_UIDS and name.endswith("(Demo)") and os.path.isfile(marker)):
            continue
        try:
            with open(marker, encoding="utf-8") as f:
                listed = {os.path.normpath(os.path.join(folder, rel)) for rel in json.load(f).get("files", [])}
        except (OSError, ValueError):
            listed = set()
        listed = {p for p in listed if p.startswith(folder + os.sep) and os.path.isfile(p)}
        others = [os.path.join(dp, n) for dp, _, ns in os.walk(folder) for n in ns
                  if os.path.join(dp, n) not in listed and os.path.join(dp, n) != marker]
        os.makedirs(archive, exist_ok=True)
        if not others:
            shutil.move(folder, os.path.join(archive, name))
            archived.append(folder)
            continue
        for path in sorted(listed) + [marker]:
            dest = os.path.join(archive, name, os.path.relpath(path, folder))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(path, dest)
            archived.append(path)
        kept.append(folder)
    header, rows = _header(system_dir), _read_rows(system_dir)
    left = [r for r in rows if not is_demo_row(r)]
    if len(left) != len(rows):
        _write_rows(system_dir, header, left)
    return {"archived": archived, "kept": kept}


def main(argv=None):
    import subprocess
    ap = argparse.ArgumentParser(description="Add or remove the fictional demo processes.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--add", action="store_true")
    g.add_argument("--remove", action="store_true")
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    res = add(HERE, a.today) if a.add else archive(HERE)
    for key, vals in res.items():
        for v in vals:
            print("%s: %s" % (key, v))
    subprocess.run(kit_run.script_cmd(HERE, "intel_index") + ["--data", "pipeline.csv"], cwd=HERE, capture_output=True, text=True)
    import kit_setup
    print("Seiten gerendert" if kit_setup.render(HERE, a.today) == 0 else "render.py fehlgeschlagen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
