#!/usr/bin/env python3
"""
ATS check (application path, Phase 3 stage A): does the ATS-safe rendering of a CV or letter have what an applicant tracking system needs?

Checks the .docx (no tables, drawings, text boxes, headers or footers; headings; contact details in the body; text present) and the plain PDF
(text extractable, page count). It reports findings {level, rule, text}; it never changes a file. 'fail' means an ATS is likely to misread
the file; 'warn' means look at it.

    python3 ats_check.py FILE.docx|FILE.pdf [--kind CV|CL]
"""
import argparse
import re
import xml.etree.ElementTree as ET
import subprocess
import sys
import zipfile

FAIL, WARN = "fail", "warn"
BAD_PARTS = (("<w:tbl>", "Tabelle"), ("<w:tbl ", "Tabelle"), ("<w:drawing", "Grafik"), ("<w:pict", "Grafik"), ("<w:txbxContent", "Textfeld"), ("<mc:AlternateContent", "Textfeld"))
HEADINGS = {"experience": r"experience|berufserfahrung|werdegang|career", "education": r"education|ausbildung|studium|bildung", "skills": r"skills|stack|kenntnisse|fähigkeiten|kompetenzen|expertise"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
YEARS = re.compile(r"(?:19|20)\d{2}\s*[-–/.]\s*(?:19|20)\d{2}")
PHONE = re.compile(r"\+?\d[\d ()/.-]{7,}\d")
MAX_PAGES = {"CV": 2, "CL": 1}


def docx_parts(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()}


def docx_text(xml):
    return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))


def check_docx(path, kind="CV"):
    """Findings for an ATS-safe .docx."""
    out = []
    try:
        parts = docx_parts(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return [{"level": FAIL, "rule": "readable", "text": "Datei nicht lesbar: %s" % exc}]
    doc = parts.get("word/document.xml", "")
    if not doc:
        return [{"level": FAIL, "rule": "readable", "text": "word/document.xml fehlt"}]
    seen = set()
    for marker, label in BAD_PARTS:
        if marker in doc and label not in seen:
            seen.add(label)
            out.append({"level": FAIL, "rule": "layout", "text": "%s im Dokument: ein ATS liest so etwas oft falsch oder gar nicht" % label})
    for name in parts:
        if re.match(r"word/(header|footer)\d*\.xml$", name):
            out.append({"level": WARN, "rule": "layout", "text": "Kopf- oder Fußzeile (%s): ein ATS überspringt sie oft" % name})
        if name.startswith("word/media/"):
            out.append({"level": FAIL, "rule": "layout", "text": "Bild im Dokument (%s)" % name})
    try:
        ET.fromstring(doc.encode("utf-8"))
    except ET.ParseError as exc:
        return out + [{"level": FAIL, "rule": "readable", "text": "word/document.xml ist kein gültiges XML (%s): Word und ein ATS lehnen die Datei ab" % exc}]
    text = docx_text(doc)
    if len(text.split()) < 30:
        out.append({"level": FAIL, "rule": "text", "text": "kaum Text im Dokument (%d Wörter)" % len(text.split())})
    out += _text_findings(text, kind)
    return out


def pdf_text(path):
    try:
        r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def pdf_pages_tool(path):
    """Page count from pdfinfo (for PDFs whose page objects are compressed); 0 when unavailable."""
    try:
        r = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=30)
        m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
        return int(m.group(1)) if m else 0
    except (OSError, subprocess.SubprocessError):
        return 0


def pdf_pages(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return 0
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", data)) or pdf_pages_tool(path)


def check_pdf(path, kind="CV"):
    """Findings for the plain PDF: text must be extractable (not an image), page count within the limit."""
    out = []
    pages = pdf_pages(path)
    if pages == 0:
        return [{"level": FAIL, "rule": "readable", "text": "PDF nicht lesbar oder leer"}]
    if pages > MAX_PAGES.get(kind, 2):
        out.append({"level": WARN, "rule": "length", "text": "%d Seiten (empfohlen höchstens %d)" % (pages, MAX_PAGES.get(kind, 2))})
    text = pdf_text(path)
    if text is None:
        out.append({"level": WARN, "rule": "text", "text": "pdftotext nicht verfügbar: Textextraktion nicht geprüft"})
    elif len(text.split()) < 30:
        out.append({"level": FAIL, "rule": "text", "text": "aus dem PDF lässt sich kaum Text lesen (Bild-PDF?)"})
    else:
        out += _text_findings(text, kind)
    return out


def _text_findings(text, kind):
    out = []
    head = text if kind == "CL" else "\n".join(text.splitlines()[:25])          # a letter carries its contact line at the end
    if not EMAIL.search(head):
        out.append({"level": WARN, "rule": "contact", "text": "keine E-Mail-Adresse im Textanfang"})
    if not any(not YEARS.fullmatch(m.group().strip()) for m in PHONE.finditer(head)):
        out.append({"level": WARN, "rule": "contact", "text": "keine Telefonnummer im Textanfang"})
    if kind == "CV":
        low = text.lower()
        for name, pat in HEADINGS.items():
            if not re.search(r"(?m)^\s*(?:%s)" % pat, low) and not re.search(pat, "\n".join(l for l in low.splitlines() if len(l) < 50)):
                out.append({"level": WARN, "rule": "headings", "text": "keine übliche Überschrift für „%s“" % name})
    return out


def status(findings):
    return "fail" if any(f["level"] == FAIL for f in findings) else "warn" if findings else "pass"


def main(argv=None):
    ap = argparse.ArgumentParser(description="ATS check of a .docx or PDF.")
    ap.add_argument("file")
    ap.add_argument("--kind", default="CV", choices=["CV", "CL"])
    a = ap.parse_args(argv)
    f = check_docx(a.file, a.kind) if a.file.lower().endswith(".docx") else check_pdf(a.file, a.kind)
    print("ATS-Prüfung %s: %s" % (a.file, {"pass": "bestanden", "warn": "Hinweise", "fail": "Fehler"}[status(f)]))
    for x in f:
        print("  %s %s: %s" % ("FEHLER" if x["level"] == FAIL else "warn  ", x["rule"], x["text"]))
    return {"pass": 0, "warn": 1, "fail": 2}[status(f)]


if __name__ == "__main__":
    sys.exit(main())
