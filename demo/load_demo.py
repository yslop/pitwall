#!/usr/bin/env python3
"""Load the fictional demo persona "Alex Muster" into this folder: 40 job-search processes in every stage and a few
Gedankenprotokolle (own notes written right after a conversation). Everything is invented; every company name starts
with "Beispiel" and every web address is a reserved example domain.

    python3 demo/load_demo.py            # add (dates are relative to today, so the cockpit looks current)
    python3 demo/load_demo.py --remove   # archive what was added to _Archiv/ and drop its rows (nothing of yours is touched)

Stdlib only, Python >= 3.9.
"""
import argparse
import csv
import datetime
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SYSTEM = os.path.join(ROOT, "_system")
MARKER = os.path.join(ROOT, ".star_demo_persona.json")
TAG = "DEMO Alex Muster"

# (company, role, status text, applied days ago, last contact days ago, location, note, protocol file or None)
ROWS = [
    ("Beispiel Rheinlogistik GmbH", "Head of Data & Analytics", "Zweites Vorstellungsgespräch", 34, 3, "Köln", "Panel mit Geschäftsführung und IT-Leitung, Fallstudie Datenplattform", "rheinlogistik.md"),
    ("Beispiel Energie West AG", "Leitung KI-Programm", "Vorstellungsgespräch Runde 1", 21, 5, "Düsseldorf / hybrid", "Fachbereich will schnell Ergebnisse, IT bremst", "energie_west.md"),
    ("Beispiel Medizintechnik SE", "Director Digital Transformation", "Angebot erhalten", 49, 1, "Aachen", "Angebot liegt vor, Verhandlung zu Gehalt und Homeoffice offen", "medizintechnik.md"),
    ("Beispiel Kommunaldienst", "Abteilungsleitung Digitalisierung", "Telefoninterview mit HR", 16, 4, "Bonn", "Öffentlicher Dienst, Eingruppierung noch unklar", "kommunaldienst.md"),
    ("Beispiel Handelsgruppe KG", "Head of IT", "Erstgespräch Recruiter", 12, 6, "Dortmund", "Personalberatung, Mandat exklusiv", "handelsgruppe.md"),
    ("Beispiel Beratungshaus", "Senior Manager Data Strategy", "Fachgespräch Runde 2", 28, 8, "Remote", "Hohe Reisebereitschaft gefragt", "beratungshaus.md"),
    ("Beispiel Maschinenwerke AG", "CDO", "Absage erhalten", 60, 31, "Stuttgart", "Absage nach Runde 1", None),
    ("Beispiel Binnenreederei", "IT-Leitung", "Absage erhalten", 55, 40, "Duisburg", "Interne Besetzung", None),
    ("Beispiel Software Solutions", "VP Engineering", "Absage erhalten", 47, 30, "München", "Ohne Begründung", None),
    ("Beispiel Versicherung Mitte", "Leiter Datenmanagement", "Absage erhalten", 44, 22, "Köln", "Gehaltsband zu niedrig", None),
    ("Beispiel Chemiepark GmbH", "Head of Digital", "Absage erhalten", 70, 45, "Leverkusen", "Standortpflicht 5 Tage", None),
    ("Beispiel Bank West", "Head of Data Governance", "Absage erhalten", 66, 50, "Münster", "Nach Assessment Center", None),
    ("Beispiel Telekom Services", "Director Platform", "Absage erhalten", 40, 26, "Bonn", "Stelle gestrichen", None),
    ("Beispiel Pharma Holding", "Global Head Analytics", "Absage erhalten", 58, 35, "Frankfurt", "Absage nach Runde 2", None),
    ("Beispiel Stadtwerke Süd", "Leitung IT-Strategie", "Absage erhalten", 52, 33, "Augsburg", "Branchenerfahrung bevorzugt", None),
    ("Beispiel Automotive Zulieferer", "Head of IT Operations", "Absage erhalten", 39, 20, "Wolfsburg", "Ohne Begründung", None),
    ("Beispiel Agentur Digital", "CTO", "Absage erhalten", 36, 18, "Köln", "Interner Kandidat", None),
    ("Beispiel Logistik Holding", "Program Director Data", "Bewerbung zurückgezogen", 30, 14, "Düsseldorf", "Selbst zurückgezogen: Reiseanteil 70 %", None),
    ("Beispiel FinTech AG", "Head of AI Engineering", "Bewerbung zurückgezogen", 25, 12, "Berlin", "Selbst zurückgezogen: reine Delivery-Rolle", None),
    ("Beispiel Lebensmittel AG", "IT-Leitung", "beworben", 9, 9, "Köln", "Über Karriereseite", None),
    ("Beispiel Windkraft Betrieb", "Head of Data", "beworben", 7, 7, "Münster / hybrid", "Empfehlung aus dem Netzwerk", None),
    ("Beispiel Klinikverbund", "Leitung Digitalisierung", "beworben", 11, 11, "Essen", "", None),
    ("Beispiel Bildungsträger", "Head of IT", "beworben", 14, 14, "Bonn", "", None),
    ("Beispiel Hafenbetriebe", "Enterprise Architect Data", "beworben", 5, 5, "Duisburg", "Fachrolle als Alternative", None),
    ("Beispiel Industrie Services", "Director Data Platform", "beworben", 18, 18, "Remote", "", None),
    ("Beispiel Versandhandel", "Head of BI", "beworben", 20, 20, "Köln", "", None),
    ("Beispiel Luftfahrttechnik", "Leitung Daten & Analytik", "beworben", 3, 3, "Köln/Bonn", "Initiativbewerbung", None),
    ("Beispiel Familienunternehmen", "Head of Digital Strategy", "beworben", 2, 2, "Bielefeld", "Initiativbewerbung", None),
    ("Beispiel Landesamt", "Referentin/Referent KI", "beworben", 24, 24, "Düsseldorf", "", None),
    ("Beispiel Gesundheitskasse", "Teamleitung Data Science", "Interessant, merken", 0, 0, "Köln", "Ausschreibung endet in 2 Wochen", None),
    ("Beispiel Mobilitätsdienst", "Head of Data", "Interessant, merken", 0, 0, "Berlin / remote", "", None),
    ("Beispiel Stahlwerk AG", "CIO", "Interessant, merken", 0, 0, "Duisburg", "Eher zu groß, Netzwerk fragen", None),
    ("Beispiel Rückversicherung", "Head of AI Governance", "Interessant, merken", 0, 0, "München", "", None),
    ("Beispiel Forschungsinstitut", "Leitung Forschungs-IT", "Interessant, merken", 0, 0, "Aachen", "", None),
    ("Beispiel Start-up Agentic", "Co-Founder CTO", "Interessant, merken", 0, 0, "Remote", "Equity statt Gehalt: prüfen", None),
    ("Beispiel Speditionsnetz", "Head of Data & AI", "keine Rückmeldung", 61, 61, "Dortmund", "", None),
    ("Beispiel Einzelhandel West", "IT-Leitung", "keine Rückmeldung", 57, 57, "Köln", "", None),
    ("Beispiel Verlag Medien", "Director Data", "keine Rückmeldung", 64, 64, "Köln", "", None),
    ("Beispiel Baukonzern", "Head of Digital Construction", "keine Rückmeldung", 59, 59, "Frankfurt", "", None),
    ("Beispiel Telematik GmbH", "Head of Data Products", "keine Rückmeldung", 63, 63, "Bochum", "", None),
]


def _today(s):
    return datetime.date.fromisoformat(s) if s else datetime.date.today()


def add(today):
    sys.path.insert(0, SYSTEM)
    import kit_import
    if os.path.exists(MARKER):
        print("Demo-Persona ist schon geladen (%s). Erst --remove." % os.path.basename(MARKER))
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Firma", "Position", "Status", "Beworben am", "Letzter Kontakt", "Ort", "Notiz"])
        for c, r, st, ap, last, loc, note, _ in ROWS:
            d = lambda n: (today - datetime.timedelta(days=n)).isoformat() if n else ""
            w.writerow([c, r, st, d(ap), d(last), loc, ("%s: %s" % (TAG, note)).strip(": ")])
        tmp = f.name
    try:
        res = kit_import.apply(tmp, SYSTEM, today.isoformat())
    finally:
        os.remove(tmp)
    folders, notes = [], 0
    by_key = {(x["company"], x["role"]): x for x in res["rows"]}
    for c, r, *_rest in ROWS:
        row = by_key.get((c, r))
        if not row:
            continue
        folder = os.path.join(ROOT, "%s %s" % (row["uid"], kit_import._safe(c)))
        folders.append(os.path.relpath(folder, ROOT))
        proto = _rest[-1]
        if proto:
            src = os.path.join(HERE, "gedankenprotokolle", proto)
            day = (today - datetime.timedelta(days=_rest[2])).isoformat()
            dst = os.path.join(folder, kit_import._safe(r), "30 Verlauf", "%s_Gedankenprotokoll.md" % day)
            with open(src, encoding="utf-8") as fi, open(dst, "w", encoding="utf-8") as fo:
                fo.write(fi.read().replace("{{DATUM}}", day).replace("{{FIRMA}}", c).replace("{{ROLLE}}", r))
            notes += 1
    with open(MARKER, "w", encoding="utf-8") as f:
        json.dump({"uids": [x["uid"] for x in res["rows"]], "folders": folders, "added": today.isoformat()}, f, ensure_ascii=False, indent=1)
    print("Demo-Persona Alex Muster: %d Verfahren, %d Gedankenprotokolle angelegt." % (res["added"], notes))
    _render(today)
    return 0


def remove(today):
    try:
        with open(MARKER, encoding="utf-8") as f:
            m = json.load(f)
    except OSError:
        print("Keine Demo-Persona geladen.")
        return 0
    arch = os.path.join(ROOT, "_Archiv", "Demo-Persona-%s" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(arch, exist_ok=True)
    for rel in m["folders"]:
        src = os.path.join(ROOT, rel)
        if os.path.isdir(src):
            shutil.move(src, os.path.join(arch, os.path.basename(rel)))
    path = os.path.join(SYSTEM, "pipeline.csv")
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        header, rows = rd.fieldnames, list(rd)
    keep = [r for r in rows if not (r.get("uid") in set(m["uids"]) and (r.get("note") or "").startswith(TAG))]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(keep)
    os.replace(MARKER, os.path.join(arch, os.path.basename(MARKER)))
    print("Demo-Persona archiviert nach %s (%d Zeilen entfernt)." % (os.path.relpath(arch, ROOT), len(rows) - len(keep)))
    _render(today)
    return 0


def _render(today):
    sys.path.insert(0, SYSTEM)
    import subprocess
    import kit_run
    import kit_setup
    subprocess.run(kit_run.script_cmd(SYSTEM, "intel_index") + ["--data", "pipeline.csv"], cwd=SYSTEM, capture_output=True, text=True)
    print("Seiten gerendert" if kit_setup.render(SYSTEM, today.isoformat()) == 0 else "render.py fehlgeschlagen")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Demo persona Alex Muster (fictional)")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    return remove(_today(a.today)) if a.remove else add(_today(a.today))


if __name__ == "__main__":
    sys.exit(main())
