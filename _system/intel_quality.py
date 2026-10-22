"""Evidence metrics of one intel document: form and verifiability (counts, sources, ages), never the truth of a statement.

Used by the warranty checks (warranty.py) and the quality strip of the reading pane (intel_reader.py). No model calls.
Python 3.9 compatible.
"""
import datetime
import re
from urllib.parse import urlparse

import intel_lint as L

REF = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
STATEMENT = re.compile(r"\b(FACT|INFERENCE)\b\s*:?\s*(.+?)(?=\b(?:FACT|INFERENCE)\b|\n\s*\n|\Z)", re.S)
SRC_NUMBER = re.compile(r"^\s*(?:[-*]\s*)?\[?(\d+)[\].):]")
OPEN_HEAD = re.compile(r"offen|nicht verifiziert|unverified|open points|unresolved", re.I)
UNVERIFIED = re.compile(r"nicht verifiziert|unverified|nicht abrufbar|nicht best[aä]tigt|could not be verified", re.I)


def _day(s):
    return L._parse_date(s) if s else None


def metrics(text, doc, version, today, name="document.md"):
    text = "" if text is None else str(text)
    ref = _day(today) or datetime.date.today()
    secs = L.sections(text)
    src_body = next((b for h, b in reversed(secs) if re.search(L.SECTION_PATTERNS["Quellen"], h.lower())), "")
    body = "\n".join(b for h, b in secs if not re.search(L.SECTION_PATTERNS["Quellen"], h.lower()) and not L.CHANGES_HEAD.match(h))
    numbers, urls, ages = set(), [], []
    for line in src_body.splitlines():                      # numbered sources count even without a URL (recordings, notes, conversations)
        m = SRC_NUMBER.match(line)
        if m:
            numbers.add(int(m.group(1)))
    for i, line in enumerate([l for l in src_body.splitlines() if L.URL.search(l)], 1):
        if not SRC_NUMBER.match(line):
            numbers.add(i)
        urls.extend(L.URL.findall(line))
        acc = L.ACCESS.search(line)
        dates = [acc.group(1)] if acc else L.DATE.findall(L.URL.sub(" ", line))
        d = _day(dates[-1]) if dates else None
        if d:
            ages.append((ref - d).days)
    cited = set()
    for m in REF.finditer(body):
        cited.update(int(n) for n in re.findall(r"\d+", m.group(1)))
    facts = unsourced = inferences = 0
    for tag, stmt in STATEMENT.findall(body):
        if tag == "FACT":
            facts += 1
            unsourced += 0 if REF.search(stmt) else 1
        else:
            inferences += 1
    domains = {(urlparse(u).hostname or "").lower().replace("www.", "") for u in urls}
    domains.discard("")
    try:
        findings = L.lint_text(name, text, doc, version, today)
    except (KeyError, ValueError, TypeError):
        findings = [{"level": L.FAIL, "rule": "unreadable", "file": name, "text": "nicht lesbar"}]
    return {"facts": facts, "inferences": inferences, "facts_unsourced": unsourced, "sources": len(set(urls)), "domains": len(domains),
            "dangling": sorted(cited - numbers), "oldest_source_age": max(ages) if ages else None,
            "unverified": len(UNVERIFIED.findall("\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#")))), "open_section": any(OPEN_HEAD.search(h) for h, _ in secs),
            "lint": L.status(findings), "lint_rules": sorted({f["rule"] for f in findings})}
