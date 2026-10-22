#!/usr/bin/env python3
"""
Renderings of a CV / cover-letter draft (application path, Phase 3 stage A). One Markdown draft, three files, never different content:

  <draft>_ATS.docx   primary: plain, one column, real headings and bullets (for application portals with an ATS)
  <draft>_ATS.pdf    the same plain layout as a PDF
  <draft>_CI.pdf     secondary: in the target company's look (colour, fonts, logo from Marke_<Firma>.json), your PE look as the fallback

The PDFs are printed by headless Google Chrome from local HTML. Without Chrome the .docx is still written and the HTML files are kept for
printing from a browser. The ATS files are checked (ats_check.py). Nothing is sent anywhere; the drafts are never changed.

    python3 render_docs.py --uid 215 [--version v1] [--force] [--dry-run]
    python3 render_docs.py --pinned
"""
import argparse
import base64
import csv
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import ats_check as A
import company_brand as B
import coverage as C
import draft_lint as L
import md_render as M

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME_CANDIDATES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium",
                     "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser")
PLAIN_CSS = ("@page{size:A4;margin:16mm}body{font-family:Calibri,Carlito,Arial,Helvetica,sans-serif;font-size:10.5pt;line-height:1.35;color:#000}"
             "h1{font-size:17pt;margin:0 0 4pt}h2{font-size:12.5pt;margin:12pt 0 3pt}h3{font-size:11pt;margin:9pt 0 2pt}p{margin:0 0 5pt}ul{margin:0 0 6pt 16pt;padding:0}"
             "li{margin:0 0 2pt}blockquote{margin:0 0 6pt 10pt}a{color:#000;text-decoration:none}")


def find_chrome(env=None):
    env = os.environ if env is None else env
    for cand in (env.get("CHROME_BIN", ""),) + CHROME_CANDIDATES:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("google-chrome") or shutil.which("chromium") or None


def chrome_pdf(html_text, pdf_path, chrome=None, runner=subprocess.run, timeout=60):
    """Print HTML to a PDF with headless Chrome. Chrome works in a temporary directory that cleans itself up; the PDF is moved into place
    (atomically) only when it exists and is not empty. True on success."""
    chrome = chrome or find_chrome()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory(prefix="render_docs_") as td:
        src, out = os.path.join(td, "doc.html"), os.path.join(td, "doc.pdf")
        with open(src, "w", encoding="utf-8") as f:
            f.write(html_text)
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files", "--print-to-pdf=" + out, "file://" + src]
        try:
            runner(cmd, capture_output=True, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            pass                                       # Chrome sometimes lingers after printing: judge by the file
        if not (os.path.isfile(out) and os.path.getsize(out) > 200):
            return False
        with open(out, "rb") as f:
            data = f.read()
    C._write_bytes_atomic(pdf_path, data)
    return True


def _data_uri(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext)
    if not mime:
        return ""
    with open(path, "rb") as f:
        data = f.read()
    if ext == "svg" and not B.svg_is_safe(data):
        return ""
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def _font_link(fonts):
    if fonts.get("source") == "google":
        fam = fonts.get("heading", "").replace(" ", "+")
        return '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=%s:wght@400;600;700&display=swap">' % html.escape(fam, quote=True)
    return ""


def _stack(name):
    n = html.escape(name or "Calibri", quote=True)
    return "'%s',Calibri,Carlito,'Helvetica Neue',Arial,sans-serif" % n if name not in ("Georgia",) else "Georgia,'Times New Roman',serif"


def ci_html(md, kind, brand=None, logo_path=""):
    """The styled page. brand None or without usable colours means your PE look; a logo is embedded as a data address (only safe images)."""
    colors = dict(B.PE)
    fonts = {"heading": B.PE["heading_font"], "body": B.PE["body_font"], "source": "fallback"}
    if isinstance(brand, dict):
        for k in ("primary", "accent", "ink", "panel"):
            v = (brand.get("colors") or {}).get(k)
            if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
                colors[k] = v
        f = brand.get("fonts")
        if isinstance(f, dict) and all(isinstance(f.get(k), str) and re.fullmatch(r"[\w .-]{1,40}", f.get(k, "")) for k in ("heading", "body")):
            fonts = {"heading": f["heading"], "body": f["body"], "source": f.get("source") if f.get("source") in ("google", "installed", "fallback") else "fallback"}
    if not B.legible(colors["primary"]):
        colors["primary"] = B.darken_until_legible(colors["primary"])
    if not B.legible(colors["ink"]):
        colors["ink"] = B.PE["ink"]                                        # body text must stay readable whatever the record says
    logo = _data_uri(logo_path) if logo_path and os.path.isfile(logo_path) else ""
    css = ("@page{size:A4;margin:15mm 16mm}body{font-family:%s;font-size:10pt;line-height:1.38;color:%s;margin:0}"
           "h1,h2,h3{font-family:%s;color:%s}h1{font-size:20pt;margin:0 0 2pt;letter-spacing:.2pt}"
           "h2{font-size:11.5pt;text-transform:uppercase;letter-spacing:.6pt;margin:13pt 0 4pt;padding-bottom:2pt;border-bottom:1.5pt solid %s}"
           "h3{font-size:10.5pt;margin:9pt 0 1pt}p{margin:0 0 5pt}ul{margin:0 0 6pt 15pt;padding:0}li{margin:0 0 2.5pt}"
           "blockquote{margin:0 0 6pt;padding:4pt 9pt;background:%s;border-left:3pt solid %s;font-style:italic}"
           "table{border-collapse:collapse;width:100%%;margin:4pt 0 8pt}th{font-size:14pt;color:%s;text-align:center;padding:2pt}td{font-size:8pt;text-align:center;color:#555;padding:0 2pt 3pt}"
           "a{color:%s;text-decoration:none}.logo{float:right;max-height:15mm;max-width:45mm;margin:0 0 4pt 8pt}"
           % (_stack(fonts["body"]), colors["ink"], _stack(fonts["heading"]), colors["primary"], colors["accent"], colors["panel"], colors["accent"], colors["primary"], colors["primary"]))
    img = '<img class="logo" alt="" src="%s">' % html.escape(logo, quote=True) if logo else ""
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>%s</title>%s<style>%s</style></head><body>%s%s</body></html>'
            % (html.escape(kind), _font_link(fonts), css, img, M.to_html(md)))


def ats_html(md):
    return '<!DOCTYPE html><html><head><meta charset="utf-8"><title>ATS</title><style>%s</style></head><body>%s</body></html>' % (PLAIN_CSS, M.to_html(M.flatten_tables(md)))


def _file_sha(path):
    """SHA-256 of a file's content ('' when there is none): a replaced logo of the same size still changes the rendering."""
    if not path or not os.path.isfile(path):
        return ""
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sha(*parts):
    return C._digest(*parts)


def _write_text_atomic(path, text):
    C._write_atomic(path, text)


def render_version(folder, num, files, brand, brand_label, logo, chrome, runner, dry_run=False):
    """Render the CV and letter of one version. {'files': [...], 'ats': status, 'findings': [...], 'notes': [...]}. Existing files of this version are replaced."""
    out_files, findings, notes = [], [], []
    bew = os.path.join(str(folder), "10 Bewerbung")
    for kind in ("CV", "CL"):
        src = files.get(kind)
        if not src:
            continue
        md = L.read_text(src)
        if not md.strip():
            notes.append("%s leer oder nicht lesbar: übersprungen" % os.path.basename(src))
            continue
        stem = os.path.splitext(src)[0]
        targets = {"docx": stem + "_ATS.docx", "ats_pdf": stem + "_ATS.pdf", "ci_pdf": stem + "_CI.pdf"}
        if dry_run:
            out_files += [os.path.basename(p) for p in targets.values()]
            continue
        M.write_docx(md, targets["docx"])
        out_files.append(os.path.basename(targets["docx"]))
        findings += [dict(f, file=os.path.basename(targets["docx"])) for f in A.check_docx(targets["docx"], kind)]
        for key, html_text in (("ats_pdf", ats_html(md)), ("ci_pdf", ci_html(md, kind, brand, logo))):
            if chrome_pdf(html_text, targets[key], chrome, runner):
                out_files.append(os.path.basename(targets[key]))
                if key == "ats_pdf":
                    findings += [dict(f, file=os.path.basename(targets[key])) for f in A.check_pdf(targets[key], kind)]
                else:
                    pages = A.pdf_pages(targets[key])
                    if pages > A.MAX_PAGES[kind]:
                        findings.append({"level": A.WARN, "rule": "length", "text": "%d Seiten (empfohlen höchstens %d)" % (pages, A.MAX_PAGES[kind]), "file": os.path.basename(targets[key])})
            else:
                keep = targets[key][:-4] + ".html"
                C._write_atomic(keep, html_text)
                out_files.append(os.path.basename(keep))
                notes.append("Chrome nicht verfügbar oder Druck fehlgeschlagen: %s als HTML gespeichert (im Browser drucken)" % os.path.basename(keep))
    return {"files": out_files, "ats": A.status(findings), "findings": findings, "notes": notes, "brand": brand_label}


def run_render(uid, system, base_dir, today, version=None, force=False, dry_run=False, locate=None, chrome=None, runner=subprocess.run):
    """{'status': 'written'|'current'|'skipped'|'error', 'version', 'files', 'ats', 'findings', 'notes'}; reports problems instead of raising."""
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
        drafts = L.find_drafts(folder)
        if not drafts:
            return {"status": "skipped", "reason": "keine Entwürfe (CV_*_v<N>.md / CL_*_v<N>.md) in 10 Bewerbung"}
        num = int(version.lstrip("vV")) if version else max(drafts)
        if num not in drafts:
            return {"status": "skipped", "reason": "Version v%d nicht vorhanden" % num}
        brand = B.load_brand(folder)
        logo = B.effective_logo(folder, brand)
        label = (brand or {}).get("company") or "PE"
        chrome = chrome if chrome is not None else find_chrome()
        digest = _sha(*[L.read_text(p) for _, p in sorted(drafts[num].items())], json.dumps({k: v for k, v in (brand or {}).items() if k != "_path"}, sort_keys=True), logo,
                      _file_sha(logo))
        state_path = os.path.join(system, "render_state.json")
        state = C._read_json(state_path, {})
        entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
        prior = entry.get(("v%d" % num)) if isinstance(entry.get("v%d" % num), dict) else {}
        bew = os.path.join(str(folder), "10 Bewerbung")
        files_ok = isinstance(prior.get("files"), list) and prior["files"] and all(isinstance(n, str) and not n.endswith(".html") and os.path.exists(os.path.join(bew, n)) for n in prior["files"])
        if not force and prior.get("hash") == digest and files_ok:                  # a failed print (HTML fallback) is retried, never frozen
            return {"status": "current", "version": "v%d" % num, "files": prior["files"], "ats": prior.get("ats", "")}
        res = render_version(folder, num, drafts[num], brand, label, logo, chrome, runner, dry_run)
        res.update(status="written", version="v%d" % num)
        if not brand:
            res["notes"].append("keine Marke (Marke_*.json): PE-Look; zuerst company_brand.py")
        if not dry_run:
            state = C._read_json(state_path, {})
            entry = state.get(uid) if isinstance(state.get(uid), dict) else {}
            entry["v%d" % num] = {"hash": digest, "date": today, "files": res["files"], "ats": res["ats"], "brand": label, "notes": res["notes"]}
            state[uid] = entry
            C._write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        return res
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render CV and cover-letter drafts: ATS-safe .docx and PDF, plus the company-styled PDF.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid")
    g.add_argument("--pinned", action="store_true")
    ap.add_argument("--version", default=None)
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    today = a.today or datetime.date.today().isoformat()
    uids = [a.uid]
    if a.pinned:
        from top10 import load
        uids = [str(u) for u in load(os.path.join(a.system, "top10.json")).get("pinned", [])]
    rc = 0
    for uid in uids:
        res = run_render(uid, a.system, a.base_dir, today, a.version, a.force, a.dry_run)
        print("render_docs uid %s: %s%s%s" % (uid, res["status"], " · " + res["version"] if res.get("version") else "", " · " + res["reason"] if res.get("reason") else ""))
        for n in res.get("files", []):
            print("  " + n)
        for f in res.get("findings", []):
            print("  %s %s %s: %s" % ("FEHLER" if f["level"] == "fail" else "warn  ", f["rule"], f.get("file", ""), f["text"]))
        for n in res.get("notes", []):
            print("  Hinweis: " + n)
        if res["status"] == "error" or res.get("ats") == "fail":
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
