"""Pitwall: turn the setup answers into a working folder. Called by setup/xlrte_setup.py after saving; never overwrites your files."""
import datetime
import json
import os
import subprocess
import sys


def apply(root, settings):
    a = settings.get("answers") or {}
    system = os.path.join(root, "_system")
    sys.path.insert(0, system)
    import kit_run
    import kit_setup
    today = datetime.date.today().isoformat()
    msgs = []
    prefs = {k: a.get(k) for k in ("goal_label", "goal_date", "language", "current_role", "target_roles", "industries", "locations", "work_mode", "salary_floor",
                                   "weekly_budget", "available_from", "notes_hint", "decision_criteria", "decision_context")}
    if a.get("salary_floor") or a.get("salary_target"):
        prefs["salary_band"] = {"floor": a.get("salary_floor") or 0, "target": a.get("salary_target") or 0, "currency": "€"}
    prefs["ui_language"] = settings.get("language") or "de"
    os.makedirs(system, exist_ok=True)                 # goals first: the demo pages are rendered during install and read them
    with open(os.path.join(system, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    res = kit_setup.install(system, a.get("name") or "Bewerber:in", a.get("brand_name") or "Pitwall", demo=bool(a.get("demo")), today=today)
    msgs.append("Ordner eingerichtet: %d neu, %d behalten" % (len(res["created"]), len(res["kept"])))

    ref = os.path.join(root, "00 references")
    os.makedirs(ref, exist_ok=True)
    zb = os.path.join(ref, "Zielbild.md")
    if not os.path.exists(zb):
        lines = ["# Zielbild", "", "_Aus der Einrichtung. Deine KI liest diese Datei vor jeder Recherche. Ändere sie jederzeit._", ""]
        for label, key in (("Zielrollen", "target_roles"), ("Branchen", "industries"), ("Orte", "locations")):
            vals = a.get(key) or []
            lines += ["## " + label] + ["- " + v for v in vals] + [""]
        lines += ["## Zielmarke", "- %s bis %s" % (a.get("goal_label") or "offen", a.get("goal_date") or "offen"), ""]
        lines += ["## Rahmen", "- Arbeitsmodell: %s" % (a.get("work_mode") or "offen"),
                  "- Neue Bewerbungen pro Woche höchstens: %s" % (a.get("weekly_budget") or 3),
                  "- Verfügbar ab: %s" % (a.get("available_from") or "offen"),
                  "- Gehalts-Untergrenze: %s" % ("hinterlegt (lokal)" if a.get("salary_floor") else "nicht angegeben"), ""]
        with open(zb, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        msgs.append("Zielbild angelegt: 00 references/Zielbild.md")
    else:                                   # setup run again: keep the user's own text, only refresh the goal line
        import re
        with open(zb, encoding="utf-8") as f:
            text = f.read()
        goal = "## Zielmarke\n- %s bis %s\n" % (a.get("goal_label") or "offen", a.get("goal_date") or "offen")
        new = re.sub(r"## Zielmarke\n(?:- [^\n]*\n?)*", goal, text, count=1) if "## Zielmarke" in text else text.rstrip("\n") + "\n\n" + goal
        if new != text:
            with open(zb, "w", encoding="utf-8") as f:
                f.write(new)
            msgs.append("Zielmarke im Zielbild aktualisiert")

    if a.get("demo") and not settings.get("_rerun"):
        r = subprocess.run([sys.executable, os.path.join(root, "demo", "load_demo.py")], cwd=root, capture_output=True, text=True)
        msgs.append((r.stdout.strip().splitlines() or ["Demo-Persona geladen"])[0])
    subprocess.run(kit_run.script_cmd(system, "intel_index") + ["--data", "pipeline.csv"], cwd=system, capture_output=True, text=True)
    msgs.append("Seiten gerendert: 01_cockpit.html" if kit_setup.render(system, today) == 0 else "Rendern fehlgeschlagen: ./pitwall render prüfen")
    return msgs
