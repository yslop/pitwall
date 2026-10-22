#!/usr/bin/env python3
"""
career_check.py — Integritätsprüfer für die Job-Search-Pipeline.

Vorbild: scripts/structure-check.sh aus Governance-VorlageOSS. Der Prüfer repariert nichts.
Er meldet, was gegen den eigenen Vertrag verstösst — SCHEMA.md, RUNBOOK.md und
die Stufen-Gates aus ~/notes-vault/career/ontology.yaml.

    python3 career_check.py                      # Bericht auf stdout
    python3 career_check.py --today 2026-09-08
    python3 career_check.py --quiet               # nur Verstösse

Exit-Code: 0 = sauber, 1 = Verstösse gefunden. Damit im geplanten Lauf verwendbar.
"""
import argparse, csv, os, re, sys
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ONTOLOGY = os.path.expanduser("~/notes-vault/career/ontology.yaml")

NOTE_MAX = 300                      # SCHEMA.md
STALE_DAYS = 45                     # Cockpit-Schwelle
LAPSE_DAYS = 60                     # RUNBOOK Schritt 2
LAPSE_STAGES = {"Applied", "Screening", "Watchlist"}   # ADR-001 V3 (heute: nur Applied)
NEVER_AUTO_LAPSE = {"Interviewing", "Final"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

findings = []   # (schwere, code, titel, [zeilen])

def flag(sev, code, title, lines):
    if lines:
        findings.append((sev, code, title, lines))

def i(x, default=None):
    try:
        return int(str(x).strip())
    except Exception:
        return default

def load_gates(path):
    """Stufen-Gates aus der Ontologie. Ohne PyYAML: minimaler, gezielter Parser."""
    if not path:
        return {}
    try:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            lines = list(f)
    except (OSError, PermissionError):
        return {}
    gates, stage, in_stages, in_req = {}, None, False, False
    for raw in lines:
        ln = raw.rstrip("\n")
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        if ln.startswith("Stages:"):
            in_stages = True; continue
        if in_stages and ln[0] not in " \t":
            break
        if not in_stages:
            continue
        ind = len(ln) - len(ln.lstrip())
        t = ln.strip()
        if ind == 2 and t.endswith(":"):
            stage = t[:-1]; gates[stage] = []; in_req = False
        elif ind == 4 and t.startswith("requires:"):
            in_req = True
        elif ind == 4 and t.endswith(":"):
            in_req = False
        elif in_req and t.startswith("- "):
            gates[stage].append(t[2:].strip())
    return gates

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--ontology", default=DEFAULT_ONTOLOGY)
    ap.add_argument("--pursuits", default=os.path.expanduser("~/notes-vault/career/pursuits"))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.data, encoding="utf-8")))
    cols = list(rows[0].keys()) if rows else []
    openr = [r for r in rows if r.get("stage") != "Closed"]

    def label(r):
        return f'{(r.get("uid") or "—"):>4}  {(r.get("company") or "")[:34]:<34} {r.get("stage",""):<12}'

    # ---- C1  Schlüssel ---------------------------------------------------
    flag("FEHLER", "C1", "Zeilen ohne uid — der Join zum Drive-Ordner fehlt (SCHEMA: 'stabil, ändert sich nie')",
         [f'      {(r.get("company") or "")[:60]}' for r in rows if not (r.get("uid") or "").strip()])

    # uid ist ein ARBEITGEBER-Schluessel (ein Drive-Ordner), kein Zeilenschluessel.
    # Mehrere Rollen beim selben Arbeitgeber teilen ihn zu Recht. Echte Dubletten sind
    # gleiche uid UND gleiche Rolle — die gibt es auch.
    by_uid = defaultdict(list)
    for r in rows:
        u = (r.get("uid") or "").strip()
        if u:
            by_uid[u].append(r)
    multi = {u: rs for u, rs in by_uid.items() if len(rs) > 1}
    twins = []
    for u, rs in sorted(multi.items()):
        seen = defaultdict(list)
        for r in rs:
            seen[(r.get("role") or "").strip().lower()[:40]].append(r)
        for role, group in seen.items():
            if len(group) > 1:
                twins.append(f'      uid {u} — {len(group)}x identische Rolle: {(group[0].get("company") or "")[:28]} / {role[:40]}')
    flag("FEHLER", "C2", "echte Dubletten — gleiche uid UND gleiche Rolle", twins)
    if multi:
        flag("HINWEIS", "C2b",
             "uid ist ein Arbeitgeber-Schluessel, kein Zeilenschluessel — es gibt keinen eindeutigen Zeilenschluessel",
             [f"      {len(multi)} uids tragen mehrere Rollen "
              f"({sum(len(rs) for rs in multi.values())} Zeilen). Beispiel: uid "
              + max(multi, key=lambda u: len(multi[u]))
              + f" mit {max(len(rs) for rs in multi.values())} Rollen.",
              "      Folge: eine Zeile laesst sich nicht eindeutig adressieren — siehe ADR-001 V2 (row_id)."])

    flag("WARNUNG", "C3", "offene Zeilen ohne folder_id",
         [label(r) for r in openr if not (r.get("folder_id") or "").strip()])

    # ---- C4  Freitextfeld ------------------------------------------------
    longn = sorted(((len(r.get("note") or ""), r) for r in rows if len(r.get("note") or "") > NOTE_MAX),
                   key=lambda t: -t[0])
    flag("FEHLER", "C4", f"note länger als {NOTE_MAX} Zeichen (SCHEMA-Vertrag)",
         [f"{label(r)} {n:>5} Zeichen" for n, r in longn[:12]]
         + ([f"      … und {len(longn)-12} weitere"] if len(longn) > 12 else [])
         + ([f"      Summe Freitext: {sum(len(r.get('note') or '') for r in rows):,} Zeichen — liegt in jedem Lauf im Kontext"] if longn else []))

    pii = [r for r in rows if EMAIL_RE.search(r.get("note") or "")]
    flag("FEHLER", "C5", "Mailadressen Dritter im Freitextfeld — wird als JSON in jede HTML-Ansicht eingebettet",
         [f'{label(r)} {len(EMAIL_RE.findall(r.get("note") or ""))} Adresse(n)' for r in pii[:10]]
         + ([f"      … und {len(pii)-10} weitere Zeilen"] if len(pii) > 10 else []))

    # ---- C6  tote Spalten ------------------------------------------------
    BY_DESIGN_EMPTY = {"outcome"}   # laut SCHEMA.md nur bei stage=Closed gesetzt
    dead = [c for c in cols if c not in BY_DESIGN_EMPTY and openr
            and all(not (r.get(c) or "").strip() for r in openr)]
    flag("WARNUNG", "C6", "Spalten, die auf KEINER offenen Zeile gefüllt sind",
         [f"      {c}" for c in dead])

    # ---- C7  Cockpit-Blindheit -------------------------------------------
    no_act = [r for r in openr if not (r.get("next_action") or "").strip()]
    if no_act:
        flag("WARNUNG", "C7",
             f"offene Verfahren ohne next_action — das Cockpit ist für {len(no_act)}/{len(openr)} des offenen Bestands blind",
             [f"      {len(no_act)} von {len(openr)} offenen Zeilen; "
              f'{sum(1 for r in openr if not (r.get("due") or "").strip())} ohne due'])

    # ---- C8  Stillstand und Lapse ---------------------------------------
    stale = sorted(((i(r.get("days_idle"), 0), r) for r in openr if i(r.get("days_idle"), 0) > STALE_DAYS),
                   key=lambda t: -t[0])
    flag("WARNUNG", "C8", f"offen und über {STALE_DAYS} Tage ohne Signal",
         [f"{label(r)} {d:>4} Tage" for d, r in stale[:10]]
         + ([f"      … und {len(stale)-10} weitere ({len(stale)} von {len(openr)} offenen)"] if len(stale) > 10 else []))

    # Active auto-lapse candidates: Applied or Screening >= LAPSE_DAYS, excluding protected
    cand = [(d, r) for d, r in stale if d >= LAPSE_DAYS and r.get("stage") in ("Applied", "Screening")]
    watchlist_stale = [(d, r) for d, r in stale if d >= LAPSE_DAYS and r.get("stage") == "Watchlist"]
    if cand:
        flag("WARNUNG", "C9",
             f"Verfahren >= {LAPSE_DAYS} Tage in Applied/Screening ohne Signal — laut RUNBOOK Schritt 2 zu schliessen (outcome=lapsed)",
             [f"{label(r)} {d:>4} Tage" for d, r in cand])
    if watchlist_stale:
        flag("HINWEIS", "C9b",
             f"Watchlist-Einträge >= {LAPSE_DAYS} Tage ohne Signal (Beobachtungsbestand, kein Auto-Lapse)",
             [f"{label(r)} {d:>4} Tage" for d, r in watchlist_stale[:6]])

    live = [(d, r) for d, r in stale if r.get("stage") in NEVER_AUTO_LAPSE]
    flag("HINWEIS", "C10", "still, aber NIE automatisch schliessen — dort steht ein Mensch dahinter",
         [f"{label(r)} {d:>4} Tage" for d, r in live])

    # ---- C11 Lanes gegen die Ontologie ----------------------------------
    known = set()
    ontology_accessible = False
    if a.ontology:
        try:
            if os.path.exists(a.ontology):
                with open(a.ontology, encoding="utf-8") as f:
                    for ln in f:
                        m = re.match(r'\s+label:\s*"(.+)"', ln)
                        if m:
                            known.add(m.group(1))
                ontology_accessible = True
        except (OSError, PermissionError):
            ontology_accessible = False
    if known:
        bad = sorted({(r.get("lane") or "").strip() for r in rows} - known - {""})
        flag("WARNUNG", "C11", "lane-Werte, die die Ontologie nicht kennt (Datenfehler, keine neue Lane)",
             [f"      {b!r} — {sum(1 for r in rows if (r.get('lane') or '').strip() == b)}x" for b in bad])
    elif not ontology_accessible and a.ontology:
        flag("HINWEIS", "C11b", "Ontologie nicht gefunden oder nicht lesbar — Lane-Abgleich übersprungen",
             [f"      erwartet unter {a.ontology}"])

    # ---- C12 Gates -------------------------------------------------------
    gates = load_gates(a.ontology)
    if gates:
        gl = []
        have_pages = False
        pages = set()
        if a.pursuits:
            try:
                if os.path.isdir(a.pursuits):
                    pages = {f[:-3].lower() for f in os.listdir(a.pursuits)}
                    have_pages = True
            except (OSError, PermissionError):
                have_pages = False
        for r in openr:
            req = gates.get(r.get("stage"), [])
            if not req:
                continue
            comp = re.sub(r"[^a-z0-9]+", "-", (r.get("company") or "").lower()).strip("-")
            page = next((p for p in pages if p and (p in comp or comp.startswith(p))), None)
            if r.get("stage") in ("Interviewing", "Final") and not page:
                gl.append(f'{label(r)} keine Synthese-Seite in career/pursuits/ — Gate-Artefakte nicht prüfbar')
        flag("WARNUNG", "C12",
             "Gate-Prüfung (ontology.yaml → Stages.requires): Verfahren in Gesprächsstufen ohne Synthese-Seite", gl)
        if not have_pages:
            flag("HINWEIS", "C12b", "career/pursuits/ nicht gefunden oder nicht lesbar — Gate-Prüfung übersprungen",
                 [f"      erwartet unter {a.pursuits}"])

    # ---- Bericht ---------------------------------------------------------
    W = 78
    print("=" * W)
    print(f"  career_check — Stand {a.today}")
    print(f"  {len(rows)} Zeilen · {len(openr)} offen · {len(rows)-len(openr)} geschlossen")
    print("=" * W)
    order = {"FEHLER": 0, "WARNUNG": 1, "HINWEIS": 2}
    icon = {"FEHLER": "✗", "WARNUNG": "!", "HINWEIS": "·"}
    for sev, code, title, lines in sorted(findings, key=lambda f: order[f[0]]):
        if a.quiet and sev == "HINWEIS":
            continue
        print(f"\n{icon[sev]} [{code}] {sev} — {title}")
        for l in lines:
            print(f"    {l}")
    errs = sum(1 for f in findings if f[0] == "FEHLER")
    warns = sum(1 for f in findings if f[0] == "WARNUNG")
    print("\n" + "=" * W)
    if not findings:
        print("  sauber — keine Verstösse")
    else:
        print(f"  {errs} Fehler · {warns} Warnungen · {len(findings)-errs-warns} Hinweise")
        print("  Der Prüfer repariert nichts. Massnahmen siehe ADR-001-schema-v2.md")
    print("=" * W)
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
