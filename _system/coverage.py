#!/usr/bin/env python3
"""
Coverage table (application path, stage 2): what a posting asks for against what the capability profile can honestly back.

For a pinned row it writes `Abdeckung_<Firma>.md` into the role's `20 Vorbereitung`: one line per requirement, classified as
Proven / Adjacent / In progress / Gap, with the profile capability and its evidence. The table advises; nothing is blocked.

Requirements are read from the posting deterministically (Jev cannot write text). Certifications named in the posting are checked
against the profile's certification table without any model call. Jev only judges the remaining requirements, and receives capability
names, levels and evidence names, never documents. Without a key or connection nothing is written (the row is reported, never guessed).

CLI:
    python3 coverage.py --uid 215 [--force]     one row
    python3 coverage.py --pinned                every pinned row without a current table
    add --dry-run to print the table and write nothing
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request

from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call
import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
PROVEN, ADJACENT, IN_PROGRESS, GAP = "Proven", "Adjacent", "In progress", "Gap"
BATCH = 5                     # requirements per Jev call (two questions each)
MAX_REQS = 15
REQ_MIN, REQ_MAX = 12, 300    # characters of a line that counts as a requirement
DEFAULT_THRESHOLD = 0.60
JD_MAX = 20000

MUST_HEAD = ("anforderung", "qualifikation", "ihr profil", "dein profil", "profil", "was sie mitbringen", "was du mitbringst", "mitbringen",
             "requirements", "qualifications", "what you bring", "what you'll bring", "must have", "must-have", "your profile", "about you",
             "ihre erfahrung", "voraussetzung", "who you are", "wer sie sind", "wer du bist", "you bring", "looking for", "was wir suchen",
             "your background", "das bringst du", "das bringen sie", "skills", "expertise", "capabilities", "knowledge", "education", "ausbildung")
NICE_HEAD = ("nice to have", "nice-to-have", "preferred", "von vorteil", "wünschenswert", "wuenschenswert", "bonus", "plus")
OFF_HEAD = ("aufgabe", "ihre rolle", "deine rolle", "responsibilities", "what you will do", "what you'll do", "your role", "wir bieten",
            "we offer", "benefits", "über uns", "ueber uns", "about us", "bewerbung", "kontakt", "unser angebot", "das erwartet",
            "unternehmen", "über das", "wer wir sind", "who we are", "about the company", "company", "salary", "gehalt", "about", "apply", "register", "find out")
HEAD_MAX_WORDS = 3               # a line without a trailing colon is a heading only when this short
NOISE = re.compile(r"https?://|www\.|linkedin|\d{1,2}\.\d{1,2}\.\d{2,4},? \d{1,2}:\d{2}|^\s*\d+\s*/\s*\d+\s*$", re.I)      # printed-page footers
NICE_MARK = re.compile(r"nice[- ]to[- ]have|wünschenswert|von vorteil|idealerweise|preferred|is a plus|is an asset|ein plus|bonus", re.I)
BULLET = re.compile(r"^\s*(?:[-•*–‒·▪●◦]|\d+[.)])\s+(.*\S)\s*$")
CERT_RANK = {GAP: 0, IN_PROGRESS: 1, PROVEN: 2}
CERT_TERMS = ("PMP", "PRINCE2", "ITIL", "ISO 42001", "ISO 27001", "CISSP", "CISM", "CISA", "TOGAF", "COBIT", "SAFe", "Scrum Master",
              "Splunk", "AWS Certified", "Azure Certified", "Google Cloud Certified")     # acronyms match case-sensitively: 'safe' is a word
CERT_WORD = re.compile(r"zertifi|certif|lizenz|licen[cs]e|akkreditier|accredit|prüfung|\bexam\b", re.I)          # a term counts as a requirement only with this nearby


# ── profile ──────────────────────────────────────────────────────────────────
def _table_rows(text, heading):
    """Rows (cell lists) of the first markdown table after `## <heading>`."""
    out, on, seen_table = [], False, False
    for line in text.splitlines():
        if line.startswith("## "):
            if on:
                break
            on = line[3:].strip().lower().startswith(heading.lower())
            continue
        if on and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not seen_table:
                seen_table = True                      # header row
                continue
            out.append(cells)
    return out


def _int(value):
    m = re.match(r"\s*(\d)", value or "")
    return int(m.group(1)) if m else 0


def load_profile(path):
    """{'threshold', 'reviewed', 'capabilities': [...], 'certs': [...], 'text'} from capability_profile.md; None when unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r"^proven_share_must_haves:\s*([0-9.]+)", text, re.M)
    r = re.search(r"^reviewed:\s*(\S+)", text, re.M)
    caps = [{"name": c[0], "level": _int(c[1]), "target": _int(c[2]), "direction": c[3], "evidence": c[4]}
            for c in _table_rows(text, "Capabilities") if len(c) >= 5]
    certs = [{"name": c[0], "status": c[1].lower(), "note": c[2]} for c in _table_rows(text, "Certifications") if len(c) >= 3]
    return {"threshold": float(m.group(1)) if m else DEFAULT_THRESHOLD, "reviewed": r.group(1) if r else "", "capabilities": caps,
            "certs": certs, "text": text}


# ── requirements from the posting ────────────────────────────────────────────
def _has_kw(s, kws):
    return any(re.search(r"(?<!\w)" + re.escape(k), s) for k in kws)


def _heading_kind(line):
    s = line.strip()
    colon = s.endswith(":")
    s = s.rstrip(":").strip().lower()
    if not s or len(s) > 60 or BULLET.match(line) or (not colon and len(re.findall(r"\w+", s)) > HEAD_MAX_WORDS):
        return None
    if _has_kw(s, ("about you",)):
        return "must"
    if _has_kw(s, OFF_HEAD):                                  # tasks, offers and company text before anything else ('Salary, Bonus & Benefits')
        return "off"
    if _has_kw(s, NICE_HEAD):
        return "nice"
    if _has_kw(s, MUST_HEAD):
        return "must"
    return None


def extract_requirements(jd_text):
    """[{'text', 'kind': 'must'|'nice'}] from headed sections (bullets or lines); bullets anywhere only when the posting has no recognisable
    structure at all. Footers are skipped. Capped."""
    lines = (jd_text or "")[:JD_MAX].splitlines()
    found, mode, structured = [], None, False
    item = None                                            # [text, kind] being built: printed PDFs wrap items over several lines

    def flush():
        nonlocal item
        if item and len(item[0]) >= REQ_MIN:
            text = item[0] if len(item[0]) <= REQ_MAX else item[0][:REQ_MAX - 1].rstrip() + "…"
            found.append((text, "nice" if item[1] == "nice" or NICE_MARK.search(text) else "must"))
        item = None

    for line in lines:
        kind = _heading_kind(line)
        if kind:
            flush()
            structured = True
            mode = None if kind == "off" else kind
            continue
        if NOISE.search(line):
            continue
        b = BULLET.match(line)
        text = (b.group(1) if b else line).strip()
        if not text:
            flush()
            continue
        if not mode:
            continue
        if item and not b and text[0].islower():           # a wrapped line continues the item before it
            item[0] += " " + text
        else:
            flush()
            item = [text, mode]
    flush()
    if not found and not structured:                       # no recognisable section at all: any bullet counts
        for line in lines:
            b = BULLET.match(line)
            if b and REQ_MIN <= len(b.group(1)) <= REQ_MAX and not NOISE.search(line):
                found.append((b.group(1).strip(), "nice" if NICE_MARK.search(b.group(1)) else "must"))
    seen, out = set(), []
    for text, kind in found:
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if key not in seen:
            seen.add(key)
            out.append({"text": text, "kind": kind})
    out.sort(key=lambda r: r["kind"] != "must")            # stable: must-haves first, then the cap keeps them
    return out[:MAX_REQS]


# ── certifications (no model) ────────────────────────────────────────────────
def _iso(text):
    return text.replace("ISO/IEC", "ISO")


CASE_FREE = {"PRINCE2"}          # written 'Prince2' as often as 'PRINCE2'


def cert_matches(text):
    """[(term, start, end)] of certification terms in text, in order of appearance (acronyms case-sensitive: 'safe' is a word)."""
    text = _iso(text)
    out = []
    for t in CERT_TERMS:
        flags = re.I if (t in CASE_FREE or " " in t) else 0
        for m in re.finditer(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, flags):
            out.append((t, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


def _cert_terms_in(text):
    seen = []
    for t, _, _ in cert_matches(text):
        if t not in seen:
            seen.append(t)
    return [t for t in CERT_TERMS if t in seen]


def _entry_verdict(entry):
    s = entry["status"]
    if s.startswith("held"):
        return PROVEN, entry["name"], entry["note"]
    if s.startswith(("in progress", "planned", "requested")):
        return IN_PROGRESS, entry["name"], entry["status"] + ": " + entry["note"]
    return GAP, entry["name"], entry["status"] + ": " + entry["note"]              # lapsed, to decide, unknown


def cert_verdict(text, profile):
    """(state, capability label, evidence) when the requirement asks for a certification (a known term AND certificate wording), else None.
    'A or B' and several matching profile entries take the best of them. Never guessed: a certification without a profile entry is a Gap."""
    if not CERT_WORD.search(text):
        return None
    best = None
    for term in _cert_terms_in(text):
        entries = [c for c in profile["certs"] if term.lower() in _iso(c["name"]).lower()]
        options = [_entry_verdict(c) for c in entries] or [(GAP, term, "nicht im Profil")]
        for v in options:
            if best is None or CERT_RANK[v[0]] > CERT_RANK[best[0]]:
                best = v
    return best


# ── classification ───────────────────────────────────────────────────────────
NO_EVIDENCE = re.compile(r"evidence to add|to add\b|missing|fehlt|qualitative only|nachzureichen|\btbd\b", re.I)


def has_evidence(text):
    """Named evidence: a non-empty cell that does not say the evidence is still missing."""
    return bool((text or "").strip()) and not NO_EVIDENCE.search(text)


def classify(cap, cover):
    """Proven / Adjacent / Gap from the matched capability (dict or None) and the coverage score 0-3. Level 2 with named evidence is the bar."""
    if cap is None or cover <= 0:
        return GAP
    if cap["level"] >= 2 and has_evidence(cap["evidence"]) and cover >= 2:
        return PROVEN
    return ADJACENT


# ── table ────────────────────────────────────────────────────────────────────
def build_rows(reqs, profile, judge=None):
    """Rows [{'text','kind','state','cap','evidence'}] or {'error': str}. Certifications first (no model), the rest through `judge`."""
    judge = judge or jev_judge
    rows, todo = {}, []
    for i, r in enumerate(reqs):
        v = cert_verdict(r["text"], profile)
        if v:
            rows[i] = dict(r, state=v[0], cap=v[1], evidence=v[2], cert=True)
        else:
            todo.append((i, r["text"]))
    if todo:
        verdicts = judge(todo, profile)
        if "error" in verdicts:
            return {"error": verdicts["error"]}
        for i, text in todo:
            v = verdicts.get(i) or {"cap": None, "cover": 0}
            cap = profile["capabilities"][v["cap"]] if v["cap"] is not None else None
            rows[i] = dict(reqs[i], state=classify(cap, v["cover"]), cap=cap["name"] if cap else "", evidence=cap["evidence"] if cap else "")
    return [rows[i] for i in range(len(reqs))]


def summarise(rows, threshold):
    must = [r for r in rows if r["kind"] == "must"]
    proven = [r for r in must if r["state"] == PROVEN]
    share = (len(proven) / len(must)) if must else None
    hard = [r for r in must if r["state"] == GAP and r.get("cert")]
    return {"must": len(must), "proven": len(proven), "share": share, "threshold": threshold,
            "below": share is not None and share < threshold, "hard_gaps": [r["text"] for r in hard]}


def _cell(s):
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def render_markdown(company, role, today, profile, rows, summary):
    share = "keine Muss-Anforderungen erkannt" if summary["share"] is None else "%d %% der Muss-Anforderungen belegt (%d von %d)" % (
        round(summary["share"] * 100), summary["proven"], summary["must"])
    lines = ["# Abdeckung — %s · %s" % (company, role), "",
             "Stand %s · Profil geprüft %s · Schwelle %d %% · berät, blockiert nicht." % (today, profile["reviewed"] or "?", round(summary["threshold"] * 100)),
             "", "**%s.**" % share]
    if summary["below"]:
        lines.append("Unter der Schwelle: der Entwurf bleibt ehrlich bei den Lücken, die Bewerbung ist deine Entscheidung.")
    if summary["hard_gaps"]:
        lines += ["", "Hinweis, harte Lücken (Zertifikat gefordert, nicht gehalten):"] + ["- " + _cell(t) for t in summary["hard_gaps"]]
    lines += ["", "| # | Anforderung | Art | Einstufung | Fähigkeit | Beleg |", "|---|---|---|---|---|---|"]
    for n, r in enumerate(rows, 1):
        lines.append("| %d | %s | %s | %s | %s | %s |" % (n, _cell(r["text"]), "Muss" if r["kind"] == "must" else "Nice", r["state"], _cell(r["cap"]), _cell(r["evidence"])))
    lines += ["", "Einstufung: Proven = Fähigkeit Stufe 2+ mit benanntem Beleg und passend; Adjacent = verwandt oder nur teilweise; "
              "In progress = Zertifikat in Arbeit oder geplant (mit echtem Datum); Gap = nichts Belegbares. Nichts davon wird im Entwurf als vorhanden dargestellt, wenn es Gap ist.", ""]
    return "\n".join(lines)


# ── Jev ──────────────────────────────────────────────────────────────────────
_COVER = ["Not covered: the candidate profile shows nothing relevant to this requirement",
          "Partly covered: related experience, but not the same scope, depth or domain",
          "Largely covered: the listed capability matches in substance",
          "Fully covered: the listed capability matches directly and at the scope asked"]


def jev_judge(items, profile, api_key=None):
    """{index: {'cap': int|None, 'cover': 0-3}} for items [(index, text)] or {'error': str}. Sends names, levels and evidence names only."""
    api_key = api_key or get_typesafe_api_key()
    if not api_key:
        return {"error": "TYPESAFE_API_KEY not set"}
    caps = profile["capabilities"]
    criteria = {"c%d" % i: "%s (level %d)" % (c["name"], c["level"]) for i, c in enumerate(caps)}
    criteria["none"] = "None of the listed capabilities fits this requirement"
    out = {}
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        questions = {}
        for idx, text in chunk:
            questions["cap%d" % idx] = {"type": "choice", "criteria": criteria,
                                        "instructions": "Which single capability of the candidate best fits this job requirement? Requirement: " + text}
            questions["cover%d" % idx] = {"type": "score", "criteria": _COVER,
                                          "instructions": "How completely does the candidate's capability profile cover this job requirement? Requirement: " + text}
        state = "Candidate capabilities (level 0-3, whether evidence exists):\n" + "\n".join(
            "%s: %s | level %d | evidence: %s" % ("c%d" % i, c["name"], c["level"], "yes" if has_evidence(c["evidence"]) else "no") for i, c in enumerate(caps))
        payload = json.dumps({"state": state, "model": "jev-latest", "questions": questions}).encode()
        req = urllib.request.Request(TYPESAFE_URL, data=payload,
                                     headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            log_call("coverage", data)
            answers = data["answers"]
            for idx, _ in chunk:
                choice = answers["cap%d" % idx]["choice"]
                out[idx] = {"cap": int(choice[1:]) if re.fullmatch(r"c\d+", str(choice)) and int(choice[1:]) < len(caps) else None,
                            "cover": max(0, min(3, int(float(answers["cover%d" % idx]["score"]) + 0.5)))}
        except Exception as exc:
            return {"error": str(exc)}
    return out


# ── run ──────────────────────────────────────────────────────────────────────
def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _read_state(path):
    """A state file as a dict. A file that exists but cannot be parsed is copied to '<name>.corrupt-<timestamp>' before the caller rewrites it,
    so a bad byte never silently costs other entries; a missing file is just {}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        reason = True
    except OSError:
        return {}
    except (ValueError, UnicodeDecodeError):
        reason = True
    if reason:
        import shutil
        import time
        try:
            shutil.copyfile(path, "%s.corrupt-%s" % (path, time.strftime("%Y%m%d-%H%M%S")))
        except OSError:
            pass
    return {}


def _write_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _write_bytes_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".", suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _digest(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def norm_uid(uid):
    """'09', 9 and '9' are the same row (pipeline.csv pads some uids; the pins are integers)."""
    s = str(uid if uid is not None else "").strip()
    return str(int(s)) if s.isdigit() else s


def run_uid(uid, system, base_dir, today, force=False, dry_run=False, judge=None, locate=None):
    """One row: {'status': 'written'|'current'|'skipped'|'error', 'reason', 'summary', 'file'}. Reports file and data problems, never raises for them."""
    try:
        return _run_uid(norm_uid(uid), system, base_dir, today, force, dry_run, judge, locate)
    except (OSError, ValueError) as exc:                      # Drive offline, unreadable or non-UTF-8 files
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _run_uid(uid, system, base_dir, today, force, dry_run, judge, locate):
    if locate is None:
        from folder_utils import locate_role_folder as locate
    row = None
    try:
        with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
            row = next((r for r in csv.DictReader(f) if norm_uid(r.get("uid")) == uid), None)
    except OSError as exc:
        return {"status": "error", "reason": "pipeline.csv: %s" % exc}
    if row is None:
        return {"status": "skipped", "reason": "uid %s nicht in pipeline.csv" % uid}
    cache = _read_json(os.path.join(system, "jd_cache.json"), {})
    jd = next((v for k, v in cache.items() if norm_uid(k) == uid), "")
    if not isinstance(jd, str) or not jd.strip():
        return {"status": "skipped", "reason": "kein Ausschreibungstext"}
    profile = load_profile(os.path.join(system, "capability_profile.md"))
    if profile is None or not profile["capabilities"]:
        return {"status": "skipped", "reason": "capability_profile.md fehlt oder ist leer"}
    reqs = extract_requirements(jd)
    if not reqs:
        return {"status": "skipped", "reason": "keine Anforderungen im Text erkannt"}
    state_path = os.path.join(system, "coverage_state.json")
    state = _read_json(state_path, {})
    digest = _digest(jd, profile["text"])
    entry = state.get(uid)
    if not force and isinstance(entry, dict) and entry.get("hash") == digest and os.path.exists(str(entry.get("path", ""))):
        return {"status": "current", "summary": state[uid]}
    rows = build_rows(reqs, profile, judge)
    if isinstance(rows, dict):
        return {"status": "error", "reason": rows["error"]}
    summary = summarise(rows, profile["threshold"])
    text = render_markdown(row.get("company", ""), row.get("role", ""), today, profile, rows, summary)
    if dry_run:
        return {"status": "written", "summary": summary, "text": text, "file": ""}
    folder, flags = locate(base_dir, uid, row.get("role", ""), row.get("folder_id", ""))
    if folder is None:
        return {"status": "error", "reason": "Rollenordner nicht gefunden: %s" % "; ".join(flags)}
    target = os.path.join(str(folder), "20 Vorbereitung")
    os.makedirs(target, exist_ok=True)
    name = "Abdeckung_%s.md" % re.sub(r"[^\w\-]", "_", row.get("company", "") or uid)
    path = os.path.join(target, name)
    _write_atomic(path, text)
    state = _read_json(state_path, {})                       # re-read: another run may have written while the model was busy
    state[uid] = {"date": today, "hash": digest, "share": summary["share"], "proven": summary["proven"], "must": summary["must"],
                  "below": summary["below"], "hard_gaps": len(summary["hard_gaps"]), "file": name, "path": path}
    _write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return {"status": "written", "summary": summary, "file": path}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Coverage table for pinned rows.")
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
    import datetime
    today = a.today or datetime.date.today().isoformat()
    uids = [a.uid]
    if a.pinned:
        from top10 import load
        uids = [str(u) for u in load(os.path.join(a.system, "top10.json")).get("pinned", [])]
    rc = 0
    for uid in uids:
        res = run_uid(uid, a.system, a.base_dir, today, force=a.force, dry_run=a.dry_run)
        s = res.get("summary") or {}
        share = s.get("share")
        detail = "" if share is None else " · %d %% (%d von %d Muss)" % (round(share * 100), s.get("proven", 0), s.get("must", 0))
        print("coverage uid %s: %s%s%s" % (uid, res["status"], detail, " · " + res["reason"] if res.get("reason") else ""))
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
