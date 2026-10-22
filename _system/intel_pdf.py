#!/usr/bin/env python3
"""
Intel PDFs (Phase 3 stage B): a cheat sheet, briefing or strategy document as a PDF in your XLRTE working-document look
(ink #1A1A1A, vermilion #E4572E, Jost and Nunito Sans, the XLRTE logo small in the header).

The PDF is printed from the Markdown by headless Google Chrome (same engine as the CV/CL renderings) beside the .md with the same name, so the
intel index and the Cheat Sheets tab find it. It is made only when the lint has no error; a new version gets a new PDF and never overwrites an older one.

    python3 intel_pdf.py --uid 133 [--force]
"""
import argparse
import base64
import datetime
import html
import json
import os
import re
import subprocess
import sys

import coverage as C
import intel_job as J
import intel_lint as IL
import md_render as M
from kit_profile import load_profile
import render_docs as R

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "assets", "xlrte-logo.svg")
INK, VERMILION, MUTED = "#1A1A1A", "#E4572E", "#555555"


def logo_uri():
    try:
        with open(LOGO, "rb") as f:
            return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def intel_html(md, doc, title, subtitle, logo=None, brand=None):
    """The page: escaped body text, XLRTE colours and fonts (Google Fonts when online, then Helvetica), footer line with document type and date."""
    logo = logo_uri() if logo is None else logo
    brand = brand or load_profile(os.path.dirname(os.path.abspath(__file__)))["brand_name"]
    css = ("@page{size:A4;margin:16mm 16mm 18mm}body{font-family:'Nunito Sans','Helvetica Neue',Arial,sans-serif;font-size:10pt;line-height:1.45;color:%s;margin:0}"
           "h1,h2,h3{font-family:'Jost','Helvetica Neue',Arial,sans-serif;color:%s}h1{font-size:20pt;margin:0 0 2pt}"
           "h2{font-size:12.5pt;margin:14pt 0 4pt;padding-bottom:2pt;border-bottom:1.5pt solid %s}h3{font-size:10.5pt;margin:9pt 0 2pt}"
           "p{margin:0 0 5pt}ul,ol{margin:0 0 6pt 16pt;padding:0}li{margin:0 0 2.5pt}blockquote{margin:0 0 6pt;padding:3pt 9pt;border-left:3pt solid %s;color:%s}"
           "table{border-collapse:collapse;width:100%%;margin:4pt 0 8pt}th,td{border-bottom:.5pt solid #ccc;padding:2pt 4pt;text-align:left;vertical-align:top}th{font-family:'Jost',Arial,sans-serif}"
           "a{color:%s;text-decoration:none}.top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2pt solid %s;padding-bottom:5pt;margin-bottom:8pt}"
           ".top img{height:9mm}.sub{color:%s;font-size:9pt;margin:0}.foot{margin-top:14pt;font-size:8pt;color:%s}"
           % (INK, INK, VERMILION, VERMILION, MUTED, INK, VERMILION, MUTED, MUTED))
    fonts = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Jost:wght@500;700&family=Nunito+Sans:wght@400;600&display=swap">'
    img = '<img alt="%s" src="%s">' % (html.escape(brand, quote=True), html.escape(logo, quote=True)) if logo else ""
    return ('<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>%s</title>%s<style>%s</style></head><body>'
            '<div class="top"><div><p class="sub">%s</p></div>%s</div>%s<p class="foot">%s</p></body></html>'
            % (html.escape(title), fonts, css, html.escape(subtitle), img, M.to_html(md), html.escape("%s · %s · nur zur persönlichen Vorbereitung" % (brand, J.DOCS[doc]["label"]))))


def run_pdf(uid, system, base_dir, today, force=False, dry_run=False, locate=None, chrome=None, runner=subprocess.run):
    """{'status': 'written'|'current'|'skipped'|'error', 'files': [...], 'notes': [...]}: one PDF per intel document (latest version of each) whose lint has no error."""
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
        docs = IL.latest_per_key(IL.find_docs(folder))
        if not docs:
            return {"status": "skipped", "reason": "keine Intel-Dokumente in 20 Vorbereitung"}
        chrome = chrome if chrome is not None else R.find_chrome()
        state_path = os.path.join(system, "intel_state.json")
        files, notes, wrote = [], [], False
        for d in docs:
            text = IL._read(d["path"])
            findings = IL.lint_text(d["file"], text, d["doc"], d["version"], today) if text.strip() else [{"level": "fail"}]
            if IL.status(findings) == "fail":
                notes.append("%s: Lint hat Fehler, kein PDF (zuerst intel_lint.py)" % d["file"])
                continue
            pdf = d["path"][:-3] + ".pdf"
            digest = C._digest(text, "xlrte-v1")
            state = C._read_state(state_path)
            entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
            pdfs = entry.get("pdfs") if isinstance(entry.get("pdfs"), dict) else {}
            if not force and isinstance(pdfs.get(d["file"]), dict) and pdfs[d["file"]].get("hash") == digest and os.path.exists(pdf):
                files.append(os.path.basename(pdf))
                continue
            if dry_run:
                files.append(os.path.basename(pdf))
                continue
            title = "%s · %s" % (row.get("company", ""), J.DOCS[d["doc"]]["label"])
            page = intel_html(text, d["doc"], title, "%s · %s%s · v%d · %s" % (row.get("company", ""), J.DOCS[d["doc"]]["label"], (" · " + d["person"]) if d["person"] else "", d["version"], d["date"]))
            if R.chrome_pdf(page, pdf, chrome, runner):
                files.append(os.path.basename(pdf))
                wrote = True
                state = C._read_state(state_path)
                entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
                pdfs = entry.get("pdfs") if isinstance(entry.get("pdfs"), dict) else {}
                pdfs[d["file"]] = {"hash": digest, "date": today, "pdf": os.path.basename(pdf)}
                entry["pdfs"] = pdfs
                state[uid] = entry
                C._write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                keep = d["path"][:-3] + ".html"
                C._write_atomic(keep, page)
                notes.append("Chrome nicht verfügbar oder Druck fehlgeschlagen: %s als HTML gespeichert (im Browser drucken)" % os.path.basename(keep))
        return {"status": "written" if wrote else "current" if files else "skipped", "files": files, "notes": notes,
                **({"reason": "; ".join(notes)} if not files and notes else {})}
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print intel documents (latest version of each) as XLRTE-styled PDFs.")
    ap.add_argument("--uid", required=True)
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    res = run_pdf(a.uid, a.system, a.base_dir, a.today or datetime.date.today().isoformat(), a.force, a.dry_run)
    print("intel_pdf uid %s: %s%s" % (a.uid, res["status"], " · " + res["reason"] if res.get("reason") else ""))
    for n in res.get("files", []):
        print("  " + n)
    for n in res.get("notes", []):
        print("  Hinweis: " + n)
    return 1 if res["status"] == "error" or (not res.get("files") and res.get("notes")) else 0


if __name__ == "__main__":
    sys.exit(main())
