#!/usr/bin/env python3
"""
Draft lint (application path, stage 3): checks a CV / cover-letter draft against what the profile can honestly back.

The lint advises the drafter and the reviewer; it does not replace reading the draft. It checks what can be checked mechanically:
  - certifications named in the draft against the profile (held / lapsed / in progress / not listed)
  - the canonical exit narrative's "Never claim" phrases
  - terms of Gap requirements from the coverage table appearing as claims
  - numbers with units that appear in none of the evidence texts (masters, brief, profile, coverage table, narrative)
  - placeholders left in the text, cover-letter length, and the draft language against the posting's

Levels: fail (must be fixed) and warn (check it). Exit code of the CLI: 0 pass, 1 warnings, 2 fail. Nothing is sent or changed except
`draft_state.json` (version, files, result, date).

CLI:
    python3 draft_lint.py --uid 215 [--version v1] [--dry-run]
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import tempfile
import zipfile

import coverage as C

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL, WARN = "fail", "warn"
FILE_RE = re.compile(r"^(CV|CL)_.+_v(\d+)\.md$")
HEDGE_YEAR = re.compile(r"(?:until|bis)\s+(\d{4})|\d{4}\s*[-–]\s*(\d{4})", re.I)
HEDGE = re.compile(r"\b(?:lapsed|expired|abgelaufen|until \d{4}|bis \d{4}|\d{4}\s*[-–]\s*\d{4}|in progress|in arbeit|in vorbereitung|geplant|planned|angestrebt|requested|beantragt|exam|prüfung|ehemals|formerly)\b", re.I)
FORBIDDEN_DEFAULT = ("personally led the restructuring", "architect of the elimination")
FORBIDDEN_DE = (r"restrukturierung\w*\s+(?:\w+\s+){0,3}(?:geleitet|verantwortet|gesteuert)", r"(?:persönlich|selbst)\s+(?:\w+\s+){0,4}restrukturierung",
                r"(?:architekt|urheber)\w*\s+(?:\w+\s+){0,3}(?:stellenabbau|stellenstreichung|abbauentscheidung|entscheidung)",
                r"auflösung\s+(?:\w+\s+){0,2}(?:meines|meiner|seines|seiner)\s+(?:bereichs|division|abteilung)")     # the narrative's guardrail, in German
PLACEHOLDER = re.compile(r"\[[A-ZÄÖÜ][^\]\n]{2,}\](?!\()|<(?![^>\n]*(?:@|://|\.))[A-Za-zÄÖÜ][^>\n]{2,}>|\b(?:TODO|TBD|XXX)\b|(?i:lorem ipsum)")
STOCK_GREETING = re.compile(r"sehr geehrte damen und herren", re.I)
NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)")
UNIT_STEMS = (r"Standort\w*", r"Mitarbeit\w*", r"Mitarbeiter\w*", r"Nutzer\w*", r"Länd\w*", r"System\w*", r"Projekt\w*", r"Quell\w*", r"Person\w*", r"Jahr\w*",
              r"Prozent", r"Mio\b\.?", r"Mrd\b\.?", r"FTE", r"Gesellschaft\w*", r"Entit\w*", r"Niederlassung\w*", r"Kund\w*", r"Berichte?\b",
              r"sites?\b", r"entit(?:y|ies)\b", r"employees?\b", r"users?\b", r"countries\b", r"years?\b", r"million\b", r"billion\b", r"people\b", r"systems?\b",
              r"sources?\b", r"projects?\b", r"reports?\b", r"direct reports?\b", r"engineers?\b", r"%", r"€")
CLAIM = re.compile(r"(?<![\w.,])(?:"
                   r"(?:EUR|€|\$|USD|CHF|GBP)\s?\d[\d.,]*\s?(?:[KkMmBb]n?\b|Mio\.?|Mrd\.?|million\b|billion\b)?"
                   r"|\d[\d.,]*\+?\s?(?:[KkMmBb]n\b|(?:" + "|".join(UNIT_STEMS) + r"))"
                   r"|(?:team of|team von|teams von|leitete|led|managed)\s+\d[\d.,]*)", re.I)
CL_WARN_WORDS, CL_FAIL_WORDS = 400, 700
STOP = {"erfahrung", "kenntnisse", "experience", "knowledge", "ability", "understanding", "demonstrated", "strong", "including", "business",
        "leadership", "analytics", "enterprise", "management", "through", "across", "within", "verantwortung", "fähigkeit", "sowie", "durch", "praktische", "praktisch", "mehrjährige", "nachweisliche", "ability", "proven", "years"}


# ── reading ──────────────────────────────────────────────────────────────────
def docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))


def read_text(path):
    """Text of a .md/.txt/.docx file; '' when it cannot be read (a .gdoc pointer or PDF is not text)."""
    if path.lower().endswith(".docx"):
        return docx_text(path)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def find_drafts(role_folder):
    """{version_number: {'CV': path, 'CL': path}} for CV_*_v<N>.md and CL_*_v<N>.md in the role's 10 Bewerbung."""
    out = {}
    folder = os.path.join(str(role_folder), "10 Bewerbung")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for n in names:
        m = FILE_RE.match(n)
        if m and os.path.isfile(os.path.join(folder, n)):
            out.setdefault(int(m.group(2)), {})[m.group(1)] = os.path.join(folder, n)
    return out


def forbidden_phrases(narrative_text):
    """Quoted phrases of the canonical narrative's 'Never claim' lines, plus the built-in ones."""
    found = list(FORBIDDEN_DEFAULT)
    for line in (narrative_text or "").splitlines():
        if re.search(r"never claim", line, re.I):
            for q in re.findall(r"[\"“„]([^\"”“]{8,}?)[\"”“]", line):
                found.append(q.strip(" ,.;").lower())
    return sorted(set(p.lower() for p in found))


def coverage_evidence(coverage_md):
    """Fähigkeit and Beleg columns of an Abdeckung table: what the profile says backs the requirements. The row numbers and the
    posting's own requirement text are not evidence."""
    out = []
    for line in (coverage_md or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and len(cells) >= 6 and cells[0].isdigit():
            out += cells[4:6]
    return "\n".join(out)


def gap_terms(coverage_md):
    """{requirement text: requirement text} for the Gap rows of an Abdeckung table."""
    out = {}
    for line in (coverage_md or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[3] == C.GAP and line.strip().startswith("|"):
            out[cells[1]] = cells[1]
    return out


def _words(text):
    return {w for w in re.findall(r"[A-Za-zÄÖÜäöüß]{5,}", text.lower())}


def distinctive_gap_terms(gaps, evidence_text):
    """Words of Gap requirements that appear nowhere in the evidence texts: claiming one of them is not backed."""
    known = _words(evidence_text)
    return {req: sorted(w for w in _words(req) - known - STOP) for req in gaps}


def _norm_number(token):
    return re.sub(r"\D", "", token)


DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}")


def profile_evidence(profile):
    """Capability names, evidence cells and certification notes: the profile's own claims (not its level numbers or review dates)."""
    if not profile:
        return ""
    return "\n".join([c["name"] + " " + c["evidence"] for c in profile["capabilities"]] + [c["name"] + " " + c["note"] for c in profile["certs"]])


def numbers_in(text):
    text = DATE.sub(" ", text)
    return {_norm_number(m.group(1)) for m in NUMBER.finditer(text) if _norm_number(m.group(1))}


def load_context(system, base_dir, uid, role_folder, language=None):
    """Everything the lint compares a draft with. Inputs that are missing or unreadable are listed in ctx['missing'] (the lint then warns instead of guessing)."""
    missing = []
    profile = C.load_profile(os.path.join(system, "capability_profile.md"))
    if profile is None:
        missing.append("capability_profile.md")
    narrative_path = os.path.join(base_dir, "00 references", "Exit_Narrative_AllForLabels_CANONICAL.md")
    narrative = read_text(narrative_path)
    if not narrative:
        missing.append("Exit_Narrative_AllForLabels_CANONICAL.md")
    coverage_md = ""
    vorb = os.path.join(str(role_folder), "20 Vorbereitung")
    try:
        cov_files = sorted(n for n in os.listdir(vorb) if n.startswith("Abdeckung_") and n.endswith(".md"))
    except OSError:
        cov_files = []
    if cov_files:
        coverage_md = read_text(os.path.join(vorb, cov_files[0]))
        if not coverage_md:
            missing.append("Abdeckung_*.md (nicht lesbar)")
    else:
        missing.append("Abdeckung_*.md")
    evidence = [narrative, coverage_evidence(coverage_md), profile_evidence(profile)]
    masters = 0
    tdir = os.path.join(base_dir, "01 templates")
    try:
        for n in sorted(os.listdir(tdir)):
            if "MASTER" in n and n.lower().endswith((".docx", ".md")):
                text = read_text(os.path.join(tdir, n))
                if text:
                    masters += 1
                    evidence.append(text)
    except OSError:
        pass
    if not masters:
        missing.append("Master-Lebenslauf/-Anschreiben (01 templates/*MASTER*.docx)")
    try:
        for n in sorted(os.listdir(vorb)):
            if n.startswith("CV_CL_Input_Brief") and n.endswith(".md"):
                evidence.append(read_text(os.path.join(vorb, n)))
    except OSError:
        pass
    evidence_text = "\n".join(evidence)
    return {"profile": profile, "forbidden": forbidden_phrases(narrative), "evidence_text": evidence_text,
            "evidence_numbers": numbers_in(evidence_text), "gap_terms": distinctive_gap_terms(gap_terms(coverage_md), evidence_text),
            "language": language, "missing": missing}


# ── rules ────────────────────────────────────────────────────────────────────
def _sentences(text):
    """[(line number, sentence)] split on line ends and sentence ends."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for part in re.split(r"(?<=[.!?;])\s+", line):
            if part.strip():
                out.append((n, part.strip()))
    return out


def _hedged(window):
    """A status word right next to the certificate. 'bis 2030' is a plan, not a lapse: a year counts only when it is not in the future."""
    now = datetime.date.today().year
    for m in HEDGE.finditer(window):
        y = HEDGE_YEAR.search(m.group(0))
        if y:
            year = int(y.group(1) or y.group(2))
            if year > now:
                continue
        return True
    return False


def _cert_context_lines(text):
    """Line numbers under a certification heading ('Zertifizierungen:'): a bare 'PMP' bullet there is a claim without the word in the line."""
    ctx, on = set(), False
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            on = False
        elif len(s) <= 60 and C.CERT_WORD.search(s) and (s.endswith(":") or s.startswith("#") or len(s.split()) <= 3):
            on = True
        elif s.startswith("#"):
            on = False
        if on:
            ctx.add(n)
    return ctx


def _cert_findings(sent, n, in_context, profile, add):
    """A certification named where certificate wording is near (or under a certification heading) must match the profile status;
    a hedge counts only right next to its own term, never for its neighbours."""
    matches = C.cert_matches(sent)
    if re.match(r"\s*(?:[-*•]\s*)?[^:]{0,40}(?:zertifi|certif|lizenz|licen[cs]e)[^:]*:", sent, re.I):
        in_context = True                                                   # 'Zertifikate: PMP, ITIL, …' lists certificates
    for k, (term, start, end) in enumerate(matches):
        left = matches[k - 1][2] if k else 0
        right = matches[k + 1][1] if k + 1 < len(matches) else len(sent)
        near = sent[max(left, start - 40):min(right, end + 60)]
        if not (in_context or C.CERT_WORD.search(near)):
            continue                                                        # a method named in prose, not a certificate
        entry = next((c for c in profile["certs"] if term.lower() in C._iso(c["name"]).lower()), None)
        if entry is None:
            add(FAIL, "certification", n, "„%s“ steht nicht im Profil; nicht als vorhanden nennen" % term)
        elif not entry["status"].startswith("held") and not _hedged(sent[max(left, start - 15, max(sent.rfind(ch, 0, start) for ch in ",;)") + 1):min(right, end + 60)]):
            add(FAIL, "certification", n, "„%s“ ist im Profil „%s“; nur mit Datum oder Status nennen (%s)" % (term, entry["status"], entry["note"]))


def lint_text(name, text, ctx, kind):
    """Findings [{'level', 'rule', 'file', 'line', 'text'}] for one draft ('CV' or 'CL')."""
    found = []

    def add(level, rule, line, msg):
        found.append({"level": level, "rule": rule, "file": name, "line": line, "text": msg})

    profile = ctx["profile"]
    cert_lines = _cert_context_lines(text) if profile else set()
    for n, sent in _sentences(text):
        low = sent.lower()
        if profile:
            _cert_findings(sent, n, n in cert_lines, profile, add)
        words = set(re.findall(r"\w+", low))
        for req, terms in ctx["gap_terms"].items():
            hit = [w for w in terms if w in words]
            if hit:
                add(WARN, "gap-claim", n, "Begriff „%s“ aus einer Lücke der Abdeckungstabelle; nur behaupten, wenn belegt (%s)" % (hit[0], req[:60]))
        for m in CLAIM.finditer(sent):
            d = re.search(r"\d[\d.,]*", m.group(0))
            digits = _norm_number(d.group(0)) if d else ""
            if digits and digits not in ctx["evidence_numbers"]:
                add(WARN, "number", n, "Zahl „%s“ steht in keinem Belegtext (Master, Brief, Profil, Abdeckung)" % m.group(0).strip())
    flat = re.sub(r"\s+", " ", text).lower()                              # phrases may be broken over lines
    for phrase in ctx["forbidden"]:
        pos = flat.find(re.sub(r"\s+", " ", phrase))
        if pos >= 0:
            add(FAIL, "exit-narrative", 0, "verbotene Formulierung aus der Leitplanke: „%s“" % phrase)
    for pat in FORBIDDEN_DE:
        m = re.search(pat, flat)
        if m:
            add(FAIL, "exit-narrative", 0, "verbotene Formulierung aus der Leitplanke (deutsch): „%s“" % m.group(0))
    for n, line in enumerate(text.splitlines(), 1):
        for m in PLACEHOLDER.finditer(line):
            add(FAIL, "placeholder", n, "Platzhalter nicht ersetzt: %s" % m.group(0))
        if kind == "CL" and STOCK_GREETING.search(line):
            add(WARN, "greeting", n, "Standardanrede: mit Namen anreden, wenn auffindbar")
    if kind == "CL":
        words_n = len(re.findall(r"\w+", re.sub(r"\S+@\S+|https?://\S+|\+?\d[\d ]{6,}", "", text)))
        if words_n > CL_FAIL_WORDS:
            add(FAIL, "length", 0, "Anschreiben hat %d Wörter (mehr als %d)" % (words_n, CL_FAIL_WORDS))
        elif words_n > CL_WARN_WORDS:
            add(WARN, "length", 0, "Anschreiben hat %d Wörter (über eine Seite, ab %d)" % (words_n, CL_WARN_WORDS))
    if ctx.get("language"):
        try:
            from prep_engine import detect_language
            got = detect_language(text)
            if got != ctx["language"]:
                add(WARN, "language", 0, "Entwurf wirkt %s, die Ausschreibung ist %s" % (got, ctx["language"]))
        except Exception:
            pass
    return found


def lint_drafts(texts, ctx):
    """texts {'CV_x_v1.md': text, ...} -> (status 'pass'|'warn'|'fail', findings). Missing inputs add a warning each."""
    findings = []
    for name in sorted(texts):
        if not texts[name].strip():
            findings.append({"level": FAIL, "rule": "unreadable", "file": name, "line": 0, "text": "Entwurf leer oder nicht lesbar (UTF-8?); nichts geprüft"})
            continue
        findings += lint_text(name, texts[name], ctx, "CL" if name.startswith("CL") else "CV")
    for m in ctx["missing"]:
        findings.append({"level": WARN, "rule": "input", "file": "", "line": 0, "text": "nicht geprüft, weil %s fehlt" % m})
    status = "fail" if any(f["level"] == FAIL for f in findings) else "warn" if findings else "pass"
    return status, findings


def render_report(version, status, findings):
    head = {"pass": "bestanden", "warn": "Warnungen", "fail": "Fehler"}[status]
    lines = ["Lint %s: %s (%d Fehler, %d Warnungen)" % (version, head, sum(f["level"] == FAIL for f in findings), sum(f["level"] == WARN for f in findings))]
    for f in sorted(findings, key=lambda f: (f["level"] != FAIL, f["file"], f["line"])):
        lines.append("  %s %s %s%s: %s" % ("FEHLER" if f["level"] == FAIL else "warn  ", f["rule"], f["file"], (":%d" % f["line"]) if f["line"] else "", f["text"]))
    return "\n".join(lines)


# ── state and run ────────────────────────────────────────────────────────────
def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def record(system, uid, version, status, findings, files, today):
    """Add or replace one version in draft_state.json (re-read first, so a concurrent job-file entry is kept)."""
    path = os.path.join(system, "draft_state.json")
    state = _read_json(path, {})
    entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
    versions = entry.get("versions") if isinstance(entry.get("versions"), dict) else {}
    versions = {k: v for k, v in versions.items() if re.fullmatch(r"v\d{1,3}", str(k)) and isinstance(v, dict)}
    versions[version] = {"files": files, "result": status, "fails": sum(f["level"] == FAIL for f in findings),
                         "warns": sum(f["level"] == WARN for f in findings), "date": today}
    entry["versions"] = versions
    entry["latest"] = max((v for v in versions if re.fullmatch(r"v\d{1,3}", str(v))), key=lambda v: int(v[1:]))
    state[uid] = entry
    _write_atomic(path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))


def run_lint(uid, system, base_dir, today, version=None, dry_run=False, locate=None):
    """{'status': 'pass'|'warn'|'fail'|'skipped'|'error', 'version', 'findings', 'report'}; reports file problems instead of raising."""
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
        drafts = find_drafts(folder)
        if not drafts:
            return {"status": "skipped", "reason": "keine Entwürfe (CV_*_v<N>.md / CL_*_v<N>.md) in 10 Bewerbung"}
        num = int(version.lstrip("vV")) if version else max(drafts)
        if num not in drafts:
            return {"status": "skipped", "reason": "Version v%d nicht vorhanden" % num}
        cache = _read_json(os.path.join(system, "jd_cache.json"), {})
        jd = next((v for k, v in cache.items() if C.norm_uid(k) == uid), "")
        language = None
        if isinstance(jd, str) and jd.strip():
            from prep_engine import detect_language
            language = detect_language(jd)
        ctx = load_context(system, base_dir, uid, folder, language)
        files = drafts[num]
        texts = {os.path.basename(p): read_text(p) for p in files.values()}
        status, findings = lint_drafts(texts, ctx)
        version = "v%d" % num
        if not dry_run:
            record(system, uid, version, status, findings, sorted(os.path.basename(p) for p in files.values()), today)
        return {"status": status, "version": version, "findings": findings, "report": render_report(version, status, findings)}
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint a CV / cover-letter draft against the profile and the coverage table.")
    ap.add_argument("--uid", required=True)
    ap.add_argument("--version", default=None, help="e.g. v1; default: the latest version found")
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--dry-run", action="store_true", help="print the report, do not record it in draft_state.json")
    a = ap.parse_args(argv)
    res = run_lint(a.uid, a.system, a.base_dir, a.today or datetime.date.today().isoformat(), a.version, a.dry_run)
    if res["status"] in ("skipped", "error"):
        print("draft_lint uid %s: %s · %s" % (a.uid, res["status"], res.get("reason", "")), file=sys.stderr)
        return 3 if res["status"] == "error" else 4
    print(res["report"])
    return {"pass": 0, "warn": 1, "fail": 2}[res["status"]]


if __name__ == "__main__":
    sys.exit(main())
