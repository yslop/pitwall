#!/usr/bin/env python3
"""XLRTE leak guard: refuses a tree that would publish personal data, secrets or private tooling traces.

    python3 leak_guard.py <dir>                                  # generic rules only (public CI)
    python3 leak_guard.py <dir> --terms private_terms.txt        # plus a private term list (owner machine, export)
    python3 leak_guard.py <dir> --allow .leakguard-allow --json

Fail-closed: exit 1 on any finding, exit 2 on a usage error (e.g. a --terms file that does not exist).
Stdlib only, Python >= 3.9. It never prints a private term in full: findings show the rule and a masked excerpt,
so the report itself can be pasted into an issue without leaking.

Allow file: one entry per line, `<glob>  <rule>  # reason`. A reason is mandatory; entries without one are ignored.
"""
import argparse
import fnmatch
import json
import os
import re
import sys

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".html", ".htm", ".js", ".mjs", ".css",
                 ".csv", ".tsv", ".sh", ".command", ".cmd", ".ps1", ".iss", ".svg", ".xml", ".excalidraw", ".env", ""}
FORBIDDEN_SUFFIXES = {".pyc", ".dmg", ".pkg", ".exe", ".msi", ".pdf", ".docx", ".xlsx", ".pptx", ".key", ".pem", ".p12", ".sqlite",
                      ".db", ".m4a", ".mp3", ".wav", ".mp4", ".mov", ".zip", ".tgz", ".gz"}
FORBIDDEN_NAMES = {".env", "pipeline.csv", "events.csv", "transitions.csv", "profile.json", "config.json", "capability_profile.md",
                   "Bio_Bausteine.json", "Gespraechs_Playbook.json", ".DS_Store", "deployed.json", "llm_calls.jsonl", "decisions.jsonl"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", "dist", "runtime"}
MAX_BYTES = 1_500_000

ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "example.de", "users.noreply.github.com", "anthropic.com")
GENERIC = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\w.])(?:\+49|0049)[\s/-]?\(?\d{2,4}\)?[\s/-]?\d{3,}[\s/-]?\d{0,6}|(?<![\w.])01[5-7]\d[\s/-]?\d{6,8}(?!\d)")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]{4}){3,7}\b")),
    ("api_key", re.compile(r"\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}"
                           r"|xox[abpr]-[A-Za-z0-9-]{20,}|hf_[A-Za-z0-9]{30,})")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("home_path", re.compile(r"/Users/(?!you\b|name\b|example\b|<)[A-Za-z0-9._-]+/|C:\\\\?Users\\\\?(?!you\b|name\b)[A-Za-z0-9._-]+")),
    ("cloud_drive", re.compile(r"CloudStorage/Google[D]rive-|Google[D]rive-[^/\s\"']+@")),
]


def _mask(s):
    s = s.strip()
    return s[:2] + "…" + s[-1:] if len(s) > 4 else "…"


def load_terms(path):
    """One term per line. `term | README.md, LICENSE` allows that term only in those files (e.g. the author credit)."""
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            body = "" if line.lstrip().startswith("# ") or line.strip() == "#" else line.split(" # ", 1)[0]
            t, _, where = body.partition("|")
            t = t.strip()
            if len(t) >= 3:
                terms.append((t, [g.strip() for g in where.split(",") if g.strip()]))
    if not terms:
        raise SystemExit("leak_guard: term file %s is empty; refusing to run without terms" % path)
    # whole-word, case-insensitive; umlaut-insensitive for German names
    pats = []
    for t, where in terms:
        esc = re.escape(t).replace("ae", "(?:ae|ä)").replace("oe", "(?:oe|ö)").replace("ue", "(?:ue|ü)")
        pats.append(("private_term", re.compile(r"(?<![A-Za-z0-9])" + esc + r"(?![A-Za-z0-9])", re.I), where))
    return pats


def load_allow(path):
    out = []
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            body, _, reason = line.partition("#")
            parts = body.split()
            if len(parts) >= 2 and reason.strip():
                out.append((parts[0], parts[1]))
    return out


def allowed(rel, rule, allow):
    return any(fnmatch.fnmatch(rel, g) and (r == rule or r == "*") for g, r in allow)


def scan(root, term_rules=(), allow=()):
    findings = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            suffix = os.path.splitext(name)[1].lower()
            def add(rule, line=0, excerpt=""):
                if not allowed(rel, rule, allow):
                    findings.append({"file": rel, "rule": rule, "line": line, "excerpt": excerpt})
            if name in FORBIDDEN_NAMES or name.startswith(".env."):
                add("forbidden_file")
                continue
            if suffix in FORBIDDEN_SUFFIXES:
                add("forbidden_type")
                continue
            if os.path.getsize(path) > MAX_BYTES:
                add("too_large")
                continue
            if suffix not in TEXT_SUFFIXES:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except UnicodeDecodeError:
                add("binary_in_text_type")
                continue
            for i, line in enumerate(lines, 1):
                for rule, rx in GENERIC:
                    for m in rx.finditer(line):
                        hit = m.group(0)
                        if rule == "email" and hit.lower().split("@")[-1].endswith(ALLOWED_EMAIL_DOMAINS):
                            continue
                        add(rule, i, _mask(hit))
                for rule, rx, where in term_rules:
                    m = rx.search(line)
                    if m and not any(fnmatch.fnmatch(rel, g) for g in where):
                        add(rule, i, _mask(m.group(0)))
            # names of files and folders can leak too
        for d in list(dirnames) + filenames:
            rel = os.path.relpath(os.path.join(dirpath, d), root).replace(os.sep, "/")
            for rule, rx, where in term_rules:
                if rx.search(d) and not allowed(rel, "private_term_in_path", allow):
                    findings.append({"file": rel, "rule": "private_term_in_path", "line": 0, "excerpt": _mask(d)})
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("--terms", help="private term list (one per line); missing file = error")
    ap.add_argument("--allow", help="allow list (glob rule # reason)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.terms and not os.path.exists(a.terms):
        print("leak_guard: --terms %s does not exist (fail-closed)" % a.terms, file=sys.stderr)
        return 2
    rules = load_terms(a.terms) if a.terms else []
    allow = load_allow(a.allow or os.path.join(a.root, ".leakguard-allow"))
    found = scan(a.root, rules, allow)
    if a.json:
        print(json.dumps({"findings": found, "count": len(found)}, ensure_ascii=False, indent=1))
    else:
        for f in found:
            print("%-22s %s:%s  %s" % (f["rule"], f["file"], f["line"], f["excerpt"]))
        print("leak_guard: %d finding(s) in %s" % (len(found), a.root))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
