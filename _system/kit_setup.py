#!/usr/bin/env python3
"""Install the pilot kit for one customer: profile, empty pipeline, example files, first render. Never overwrites an existing file.

    python3 _system/kit_setup.py --name "Erika Muster" [--brand STAR] [--today YYYY-MM-DD]
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import date

import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_MD = """# STAR Pilot

Du bist der Assistent für die Bewerbungsvorbereitung in diesem Ordner.

1. Lies zuerst `_system/RUNBOOK.md`. Beim ersten Mal führe `ONBOARDING.md` Schritt für Schritt mit mir aus.
2. Erfinde keine Fakten. Die Bio entsteht nur aus `00 references/Bio_Bausteine.json`.
3. Befehle startest du mit `./star <name> [Argumente]` (Windows PowerShell: `.\\star <name> [Argumente]`), zum Beispiel `./star intel_queue --json`.
4. Recherchiere mit öffentlichen Quellen und nenne sie; ohne Websuche im Agenten sage das und frage mich.
5. Sende nichts und lösche nichts.
"""

HEADER = ["uid", "company", "role", "lane", "stage", "outcome", "applied", "last_event", "days_idle", "score", "boost", "salary_fit",
          "location", "contacts", "folder_id", "next_action", "due", "note", "ts_confidence", "ts_fit_score"]


def install(system_dir, name, brand="STAR", demo=False, today=None):
    system_dir = os.path.abspath(system_dir)
    base = os.path.dirname(system_dir)
    created, kept = [], []

    def put(path, writer):
        if os.path.exists(path):
            kept.append(path)
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        writer(path)
        created.append(path)

    def write_profile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "brand_name": brand, "photo": "", "exit_file": "", "exit_summary": {"de": "", "en": ""}, "proof_examples": []},
                      f, ensure_ascii=False, indent=2)

    def write_pipeline(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)

    put(os.path.join(system_dir, "profile.json"), write_profile)
    put(os.path.join(system_dir, "pipeline.csv"), write_pipeline)
    for example, target in (("Bio_Bausteine.example.json", "Bio_Bausteine.json"), ("Gespraechs_Playbook.example.json", "Gespraechs_Playbook.json")):
        put(os.path.join(base, "00 references", target), lambda p, e=example: shutil.copyfile(os.path.join(system_dir, "kit_examples", e), p))
    def write_agent_md(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(AGENT_MD)

    for fname in ("CLAUDE.md", "AGENTS.md"):
        put(os.path.join(base, fname), write_agent_md)
    if demo:
        import kit_demo
        res = kit_demo.add(system_dir, today)
        created += res["created"]
        kept += res["kept"]
    return {"created": created, "kept": kept}


def render(system_dir, today):
    system_dir = os.path.abspath(system_dir)
    proc = subprocess.run(kit_run.script_cmd(system_dir, "render") + ["--data", "pipeline.csv", "--out", os.path.dirname(system_dir), "--today", today],
                          cwd=system_dir, capture_output=True, text=True)
    return proc.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install the pilot kit for one customer.")
    ap.add_argument("--name", required=True)
    ap.add_argument("--brand", default="STAR")
    ap.add_argument("--no-demo", action="store_true", help="do not add the two fictional demo processes")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args(argv)
    res = install(HERE, a.name, a.brand, demo=not a.no_demo, today=a.today)
    for p in res["created"]:
        print("angelegt:", p)
    for p in res["kept"]:
        print("behalten:", p)
    subprocess.run(kit_run.script_cmd(HERE, "intel_index") + ["--data", "pipeline.csv"], cwd=HERE, capture_output=True, text=True)
    rc = render(HERE, a.today)
    print("Seiten gerendert" if rc == 0 else "render.py fehlgeschlagen (Code %s)" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
