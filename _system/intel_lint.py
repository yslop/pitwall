#!/usr/bin/env python3
"""
Intel lint (Phase 3 stage B): checks a cheat sheet, briefing or strategy document written from an intel job file.

fail (fix before it becomes a PDF): required sections missing, no source list, fewer sources than the document type needs, no source with a URL,
placeholders left, a new version without "Änderungen seit v<N>".
warn (check it): a source without an access date, sources older than 30 days, statements without FACT/INFERENCE, a number without a source in
its paragraph, an INFERENCE that became FACT without naming its source, too long.
Exit code: 0 pass, 1 warnings, 2 fail. Results go to `intel_state.json` (per document, person and version).

    python3 intel_lint.py --uid 133 [--file NAME.md] [--dry-run]
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

import coverage as C
import intel_job as J

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL, WARN = "fail", "warn"
SECTION_PATTERNS = {
    "Das Unternehmen in Zahlen": r"zahlen|kennzahlen|numbers|facts|at a glance|company in",
    "Eigentümer und Führung": r"eigentümer|führung|leitung|ownership|leadership|management",
    "Warum jetzt": r"warum jetzt|why now|anlass|trigger",
    "Mein Blickwinkel": r"blickwinkel|mein ansatz|my angle|anknüpfung|meine sicht",
    "Fünf Fragen an sie": r"fragen|questions",
    "Strategie und Finanzbild": r"strategie|finanz|strategy|financial",
    "Markt und Wettbewerb": r"markt|wettbewerb|market|competit",
    "Organisation und Entscheider": r"organisation|entscheider|organi[sz]ation|decision",
    "Risiken": r"risiken|risks",
    "Was sie von dieser Rolle brauchen": r"brauchen|(?<![a-zäöü])rolle|need|require",
    "Mein Pitch und meine Agenda": r"pitch|agenda",
    "Hypothese für die ersten 100 Tage": r"hypothese|hypothesis|erste[nr]? (?:100|90)|first (?:100|90)",
    "Betriebsmodell": r"betriebsmodell|operating model",
    "KPI- und Wertbeitrag": r"kpi|wertbeitrag|value",
    "Risiken und Abhängigkeiten": r"risiken|risks|abhängigkeit|dependenc",
    "Quellen": r"^(?:quellen|sources)\b",
}
OPEN_HEAD = re.compile(r"offen|nicht verifiziert|unverified|open points|unresolved", re.I)
HEADING = re.compile(r"^\s*#{2,4}\s+(.*\S)\s*$", re.M)          # ## and deeper: the H1 is the title, not a section
URL = re.compile(r"https?://[^\s)>\]]+")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b")
TAG = re.compile(r"\b(FACT|INFERENCE)\b")
ANGLE_OK = {"sup", "sub", "br", "b", "i", "u", "em", "strong", "a", "p", "ul", "ol", "li", "span", "div", "code", "pre", "hr", "img", "table", "tr", "td", "th", "small", "mark",
            "h1", "h2", "h3", "h4", "h5", "h6"}


def placeholders(line):
    """Placeholder-looking text on one line: [FIRMA], [Company name], <Rolle>, TODO/TBD/XXX. Tags such as [FACT], [1], [Text][1], links and HTML are not."""
    out = []
    for m in re.finditer(r"\[([^\]\n]{2,40})\](?![\(\[])", line):
        g = m.group(1).strip()
        if (re.fullmatch(r"[A-ZÄÖÜ][A-ZÄÖÜ ]{2,}", g) and g not in ("FACT", "INFERENCE")) or (re.match(r"(?:Firma|Rolle|Name|Datum|Platzhalter|hier|Company|Role)\b", g, re.I) and len(g) < 25):
            out.append(m.group(0))
    for m in re.finditer(r"<([A-Za-zÄÖÜ][A-Za-zÄÖÜ ]{1,20})>", line):
        if m.group(1).split()[0].lower() not in ANGLE_OK:
            out.append(m.group(0))
    out += re.findall(r"\b(?:TODO|TBD|XXX)\b|(?i:lorem ipsum)", line)
    return out


NUMBER_CLAIM = re.compile(r"(?<![\w.,])\d[\d.,]*\s?(?:%|Mio\.?|Mrd\.?|million|billion|bn|m\b|k\b|EUR|€|\$|Mitarbeit\w*|employees|Standort\w*|sites|Jahre|years|Kunden|customers|Länder|countries)|(?:EUR|€|\$)\s?\d", re.I)
CHANGES_HEAD = re.compile(r"^(?:änderungen|aenderungen|changes)\s+(?:seit|since)\s+v(\d+)", re.I)
ACCESS = re.compile(r"(?:abgerufen|abruf|accessed|retrieved|zugriff)[^\d\n]{0,20}(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})", re.I)
STAMP = re.compile(r"\[\d+\]|https?://|Transkript|transcript|Notiz|Quelle", re.I)


def sections(text):
    """[(heading, body)] in document order."""
    heads = list(HEADING.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((_norm_heading(m.group(1)), text[m.end():end]))
    return out


def _norm_heading(h):
    """Heading text without numbering, bold and other markup: '**7. Quellen**' -> 'Quellen'."""
    return re.sub(r"^[\d.)\s]+", "", re.sub(r"[*_`]", "", h)).strip()


def _parse_date(s):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def lint_text(name, text, doc, version, today):
    """Findings [{'level','rule','file','text'}] for one intel document."""
    found = []

    def add(level, rule, msg):
        found.append({"level": level, "rule": rule, "file": name, "text": msg})
    spec = J.DOCS[doc]
    secs = sections(text)
    heads = [h for h, _ in secs]
    for req in spec["sections"]:
        pat = SECTION_PATTERNS.get(req, re.escape(req.lower()))
        if not any(re.search(pat, h.lower()) for h in heads):
            add(FAIL, "section", "Pflichtabschnitt fehlt: %s" % req)
    src_body = next((b for h, b in reversed(secs) if re.search(SECTION_PATTERNS["Quellen"], h.lower())), "")
    urls = URL.findall(src_body)
    if not src_body.strip():
        add(FAIL, "sources", "kein Abschnitt Quellen")
    elif len(set(urls)) < spec["min_sources"]:
        add(FAIL, "sources", "%d verschiedene Quellen-URLs, nötig sind mindestens %d" % (len(set(urls)), spec["min_sources"]))
    ref = _parse_date(today) or datetime.date.today()
    for line in [l for l in src_body.splitlines() if URL.search(l)]:
        acc = ACCESS.search(line)
        dates = [acc.group(1)] if acc else DATE.findall(URL.sub(" ", line))          # the access date; else a date outside the URL
        if not dates:
            add(WARN, "sources", "Quelle ohne Abrufdatum: %s" % line.strip()[:80])
        else:
            dd = _parse_date(dates[-1])
            if dd and (ref - dd).days > J.LIVE_MAX_AGE_DAYS:
                add(WARN, "stale", "Quelle älter als %d Tage (%s): %s" % (J.LIVE_MAX_AGE_DAYS, dates[-1], line.strip()[:60]))
    body = "\n".join(b for h, b in secs if not re.search(SECTION_PATTERNS["Quellen"], h.lower()) and not CHANGES_HEAD.match(h))
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith("#")]
    items = [x for p in paras for x in (p.splitlines() if re.match(r"\s*[-*•\d]", p) else [p]) if len(x.strip()) > 25]
    untagged = [x for x in items if not TAG.search(x)]
    if items and len(untagged) / len(items) > 0.2:
        add(WARN, "tags", "%d von %d Aussagen ohne FACT oder INFERENCE (Beispiel: %s)" % (len(untagged), len(items), untagged[0].strip()[:60]))
    for p in paras:
        if NUMBER_CLAIM.search(p) and not STAMP.search(p):
            add(WARN, "number", "Zahl ohne Quelle im selben Absatz: %s" % p[:70])
    for n, line in enumerate(text.splitlines(), 1):
        for ph in placeholders(line[:2000]):
            add(FAIL, "placeholder", "Platzhalter nicht ersetzt (Zeile %d): %s" % (n, ph))
    if version >= 2:
        chunk = next((b for h, b in secs if CHANGES_HEAD.match(h)), None)
        if chunk is None:
            add(FAIL, "changes", "Version v%d braucht den Abschnitt „Änderungen seit v%d“ (oder „Changes since v%d“)" % (version, version - 1, version - 1))
        else:
            for line in chunk.splitlines():
                if re.search(r"inference\s*(→|->|zu)\s*fact|jetzt fact|bestätigt", line, re.I) and not STAMP.search(line):
                    add(WARN, "changes", "INFERENCE→FACT ohne genannte Quelle: %s" % line.strip()[:70])
    if not any(re.search(OPEN_HEAD, h) for h in heads):
        add(WARN, "open", "Abschnitt „Offen / nicht verifiziert“ fehlt (auch „keine“ ist eine Antwort): was sich nicht belegen oder abrufen ließ, gehört dorthin, nicht in einen FACT")
    words = len(re.findall(r"\w+", URL.sub(" ", text)))
    if words > spec["words_warn"]:
        add(WARN, "length", "%d Wörter (Rahmen: %s)" % (words, spec["pages"]))
    return found


def status(findings):
    return "fail" if any(f["level"] == FAIL for f in findings) else "warn" if findings else "pass"


def find_docs(folder):
    """[{'file','path','doc','person','date','version'}] of generated intel documents in 20 Vorbereitung."""
    out = []
    for n in J.role_files(folder, "20 Vorbereitung"):
        m = J.INTEL_NAME.match(n)
        if m:
            doc = next(k for k, v in J.DOCS.items() if v["token"] == m.group("token"))
            out.append({"file": n, "path": os.path.join(str(folder), "20 Vorbereitung", n), "doc": doc, "person": (m.group("person") or "").replace("_", " "),
                        "date": m.group("date"), "version": int(m.group("v")), "key": doc + ":" + (m.group("person") or "")})
    return out


def latest_per_key(docs):
    best = {}
    for d in docs:
        if d["key"] not in best or (d["version"], d["date"]) > (best[d["key"]]["version"], best[d["key"]]["date"]):
            best[d["key"]] = d
    return list(best.values())


def _write_state(system, uid, d, st, findings, today):
    path = os.path.join(system, "intel_state.json")
    state = C._read_state(path)
    entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
    docs = entry.get("docs") if isinstance(entry.get("docs"), dict) else {}
    rec = docs.get(d["key"]) if isinstance(docs.get(d["key"]), dict) else {}
    versions = rec.get("versions") if isinstance(rec.get("versions"), dict) else {}
    versions = {k: v for k, v in versions.items() if re.fullmatch(r"v\d{1,3}", str(k)) and isinstance(v, dict)}
    versions["v%d" % d["version"]] = {"file": d["file"], "date": d["date"], "result": st, "fails": sum(f["level"] == FAIL for f in findings),
                                       "warns": sum(f["level"] == WARN for f in findings), "linted": today}
    rec.update(doc=d["doc"], person=d["person"], versions=versions, latest="v%d" % max(int(k[1:]) for k in versions))
    docs[d["key"]] = rec
    entry["docs"] = docs
    state[uid] = entry
    C._write_atomic(path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))


def run_lint(uid, system, base_dir, today, file=None, dry_run=False, locate=None):
    """{'status': 'pass'|'warn'|'fail'|'skipped'|'error', 'results': [{doc, version, status, findings}], 'reason'}."""
    uid = C.norm_uid(uid)
    if locate is None:
        from folder_utils import locate_role_folder as locate
    try:
        row = J._row(system, uid)
        if row is None:
            return {"status": "skipped", "reason": "uid %s nicht in pipeline.csv" % uid}
        folder, flags = locate(base_dir, uid, row.get("role") or "", row.get("folder_id") or "")
        if folder is None:
            return {"status": "error", "reason": "Rollenordner nicht gefunden: %s" % "; ".join(flags)}
        docs = find_docs(folder)
        picked = [d for d in docs if d["file"] == file] if file else latest_per_key(docs)
        if not picked:
            return {"status": "skipped", "reason": "keine Intel-Dokumente (<Firma>_CheatSheet|Briefing|Strategy_Doc_<Datum>_v<N>.md) in 20 Vorbereitung"}
        results, overall = [], "pass"
        for d in picked:
            text = _read(d["path"])
            if not text.strip():
                findings = [{"level": FAIL, "rule": "unreadable", "file": d["file"], "text": "Dokument leer oder nicht lesbar (UTF-8?)"}]
            else:
                findings = lint_text(d["file"], text, d["doc"], d["version"], today)
            st = status(findings)
            if not dry_run:
                _write_state(system, uid, d, st, findings, today)
            results.append({"doc": d["doc"], "file": d["file"], "version": d["version"], "status": st, "findings": findings})
            overall = "fail" if st == "fail" or overall == "fail" else "warn" if st == "warn" or overall == "warn" else "pass"
        return {"status": overall, "results": results}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint intel documents (cheat sheet, briefing, strategy document).")
    ap.add_argument("--uid", required=True)
    ap.add_argument("--file", default=None)
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    res = run_lint(a.uid, a.system, a.base_dir, a.today or datetime.date.today().isoformat(), a.file, a.dry_run)
    if res["status"] in ("skipped", "error"):
        print("intel_lint uid %s: %s · %s" % (a.uid, res["status"], res.get("reason", "")), file=sys.stderr)
        return 3 if res["status"] == "error" else 4
    for r in res["results"]:
        print("Lint %s v%d: %s" % (J.DOCS[r["doc"]]["label"], r["version"], {"pass": "bestanden", "warn": "Warnungen", "fail": "Fehler"}[r["status"]]))
        for f in sorted(r["findings"], key=lambda f: f["level"] != FAIL):
            print("  %s %s: %s" % ("FEHLER" if f["level"] == FAIL else "warn  ", f["rule"], f["text"]))
    return {"pass": 0, "warn": 1, "fail": 2}[res["status"]]


if __name__ == "__main__":
    sys.exit(main())
