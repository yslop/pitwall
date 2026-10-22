#!/usr/bin/env python3
"""
RUNBOOK Step 3b — Revisit (Interviewing/Final).

Closes the one structural gap the Kontextregel leaves open: interview
transcripts, summaries and briefing sheets get saved straight to Drive by
the user, never through Gmail, so Schritt 1/2 never see them and
pipeline.csv goes stale for exactly the opportunities moving fastest.

Scope is intentionally narrow and cheap, on purpose (see
feedback_typesafe_token_economy): only rows in stage Interviewing/Final
(plus Screening since 2026-10-02), only their "30 Verlauf" subfolder, only a filename+mtime
diff against the last run's state. Zero TypeSafe calls — this step
detects and surfaces new artifacts, it does not interpret their content
or guess an outcome. Nothing here overrides the Schutzregel: stage/outcome
are never touched by this script.

CLI:
    python3 revisit.py --pipeline _system/pipeline.csv --base-dir "$(pwd)" \
        --state _system/revisit_state.json --today YYYY-MM-DD [--dry-run]
"""
import argparse, csv, json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from folder_utils import locate_role_folder

WATCHED_STAGES = {"Screening", "Interviewing", "Final"}
NOTE_MAX = 300
# Files the system writes itself (debriefs, research and follow-up orders) are not new input from the owner: never report them.
GENERATED = re.compile(r"^(Debrief_|Nachbereitung|Recherche_Auftrag)", re.I)
STAMP = re.compile(r"\[Revisit [^\]]*\][^|]*(?:\|\s*|$)")


def is_generated(fname: str) -> bool:
    return bool(GENERATED.match(fname))


def compose_note(old: str, today: str, n: int, cats, latest: str) -> str:
    """The revisit stamp in front, what the note said before behind it (an older stamp is replaced, never stacked); cut at NOTE_MAX."""
    head = f"[Revisit {today}] {n} neue Datei(en) in 30 Verlauf ({', '.join(cats)}), juengstes {latest}. Status pruefen."
    rest = STAMP.sub("", old or "").strip(" |")
    return (head if not rest else head + " | " + rest)[:NOTE_MAX]

CATEGORY_PATTERNS = [
    (re.compile(r"transcript|vorstellungsgespr|interview|gespr[aä]ch", re.I), "Gespraech gefuehrt"),
    (re.compile(r"cheat.?sheet|cockpit|briefing", re.I), "Vorbereitungsmaterial aktualisiert"),
    (re.compile(r"^mail_", re.I), "Korrespondenz"),
    (re.compile(r"linkedin", re.I), "Kontakt-Recherche"),
    (re.compile(r"screenshot", re.I), "Sonstige Notiz"),
]

DATE_PATTERNS = [
    re.compile(r"(20\d{2})-(\d{2})-(\d{2})"),
    re.compile(r"^(\d{2})-(\d{2})[ _]"),
]


def classify(fname: str) -> str:
    for pat, label in CATEGORY_PATTERNS:
        if pat.search(fname):
            return label
    return "Neue Datei"


def extract_date(fname: str, today: str) -> str:
    m = DATE_PATTERNS[0].search(fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = DATE_PATTERNS[1].match(fname)
    if m:
        year = today.split("-")[0]
        return f"{year}-{m.group(1)}-{m.group(2)}"
    return ""


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", required=True)
    ap.add_argument("--base-dir", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--today", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    pipeline_path = Path(args.pipeline)
    state_path = Path(args.state)
    state = load_state(state_path)

    with open(pipeline_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    changed_uids = []
    flags = []

    for row in rows:
        if row.get("stage") not in WATCHED_STAGES:
            continue
        uid = row["uid"]
        role_folder, loc_flags = locate_role_folder(
            args.base_dir, uid, row.get("role", ""), row.get("folder_id", "")
        )
        flags.extend(f"[uid {uid}] {msg}" for msg in loc_flags)
        if role_folder is None:
            flags.append(f"[uid {uid}] {row.get('company','')}: no Drive folder found, skipped")
            continue

        verlauf = role_folder / "30 Verlauf"
        if not verlauf.is_dir():
            continue  # nothing filed yet, nothing to revisit

        current_files = sorted(f.name for f in verlauf.iterdir()
                                if f.is_file() and not f.name.startswith("."))
        uid_state = state.get(uid, {"known_files": []})
        known = set(uid_state.get("known_files", []))
        new_files = [f for f in current_files if f not in known and not is_generated(f)]

        if new_files:
            cats = sorted({classify(f) for f in new_files})
            dates = [d for d in (extract_date(f, args.today) for f in new_files) if d]
            latest = max(dates) if dates else "unbekannt"
            new_note = compose_note(row.get("note", ""), args.today, len(new_files), cats, latest)
            print(f"uid {uid} ({row.get('company','')}): {len(new_files)} new artifact(s) — {new_files}")
            if not args.dry_run:
                row["note"] = new_note
                if latest != "unbekannt" and latest > row.get("last_event", ""):
                    row["last_event"] = latest
                changed_uids.append(uid)

        state[uid] = {"known_files": sorted(set(current_files) | known),
                       "last_checked": args.today}

    if not args.dry_run:
        with open(pipeline_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    if changed_uids:
        print(f"\nUpdated pipeline.csv for uid(s): {', '.join(changed_uids)}")
    else:
        print("\nNo new artifacts since last revisit — pipeline.csv unchanged.")
    for fl in flags:
        print(f"FLAG: {fl}")


if __name__ == "__main__":
    main()
