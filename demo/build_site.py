#!/usr/bin/env python3
"""Build the public live demo: Pitwall with the fictional person Alex Muster, as static pages (GitHub Pages).

    python3 demo/build_site.py --out _site [--lang de]

Works on a throwaway copy of this folder, so your own data is never touched. Only fictional demo data goes in; absolute
paths of the build machine are removed from the pages. The demo also carries one saved decision matrix, so the cockpit
shows a recommendation next to the process.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".git", ".github", "installer", "dist", "runtime", ".venv", "config", "logs", "feedback", "_site", "__pycache__"}
BANNER = {
    "de": ("Live-Demo mit erfundenen Daten (Alex Muster). Nichts hier ist echt, nichts wird gespeichert.", "Pitwall installieren"),
    "en": ("Live demo with made-up data (Alex Muster). Nothing here is real, nothing is stored.", "Install Pitwall"),
}


def _copy_tree(dst):
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP]
        rel = os.path.relpath(d, ROOT)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(d, f), os.path.join(dst, rel, f))


def _sample_matrix(work, today):
    """One saved matrix for the first demo process with an interview cockpit."""
    for ck in sorted(glob.glob(os.path.join(work, "*", "*", "20 Vorbereitung", "Cockpit_*.html"))):
        verlauf = os.path.join(os.path.dirname(os.path.dirname(ck)), "30 Verlauf")
        os.makedirs(verlauf, exist_ok=True)
        company = re.sub(r"[^\w\-]", "_", os.path.basename(os.path.dirname(os.path.dirname(ck))).split(" ", 1)[-1])[:30]
        data = {"kind": "pitwall.decision", "version": 1, "saved": today + "T18:00:00Z",
                "criteria": [{"key": k} for k in ("budget", "role", "chemistry", "pay", "work")],
                "ratings": {"budget": "go", "role": "go", "chemistry": "check", "pay": "go", "work": "go"},
                "note": "Demo: Runde 2 annehmen, Gehaltsreview schriftlich klären.", "verdict": "go"}
        with open(os.path.join(verlauf, "Entscheidung_%s_%s.json" % (company, today)), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    return False


def _clean(html, work, lang):
    html = html.replace(work + os.sep, "").replace(work, ".")
    html = re.sub(r'<img[^>]+src="(?:/|[A-Za-z]:\\)[^"]*"[^>]*>', "", html)            # leftover absolute image paths
    text, cta = BANNER.get(lang, BANNER["de"])
    bar = ('<div style="position:fixed;left:0;right:0;bottom:0;z-index:9998;background:#E4572E;color:#0E0E10;'
           'font:600 13px/1.4 system-ui,sans-serif;padding:8px 14px;text-align:center">%s · '
           '<a href="https://github.com/yslop/pitwall/releases/latest" style="color:#0E0E10">%s →</a></div>') % (text, cta)
    bar += ('<script>setTimeout(function(){document.querySelectorAll("button").forEach(function(b){var s=getComputedStyle(b);'
            'if(s.position==="fixed"&&parseInt(s.bottom)<40)b.style.bottom="48px";});document.body.style.paddingBottom="44px";},300);</script>')
    return html.replace("</body>", bar + "</body>", 1) if "</body>" in html else html + bar


def build(out, lang="de"):
    today = datetime.date.today().isoformat()
    work = tempfile.mkdtemp(prefix="pitwall-demo-")
    _copy_tree(work)
    sys.path.insert(0, os.path.join(work, "setup"))
    import xlrte_setup
    xlrte_setup.ROOT = work
    xlrte_setup.SETTINGS = os.path.join(work, "config", "settings.json")
    answers = {"name": "Alex Muster", "ui_language": lang, "goal_label": "Vertrag unterschrieben" if lang == "de" else "Contract signed",
               "goal_date": "%d-12-31" % datetime.date.today().year, "salary_floor": "85000", "salary_target": "105000",
               "decision_context": "Höchstens drei Pendeltage" if lang == "de" else "At most three commuting days", "demo": True}
    for m in xlrte_setup.save({"answers": answers, "ai": {"provider": "none"}, "privacy": {"local_only": True}}):
        print(m)
    if _sample_matrix(work, today):
        subprocess.run([sys.executable, os.path.join(work, "_system", "render.py"), "--data", "pipeline.csv", "--out", work, "--today", today],
                       cwd=os.path.join(work, "_system"), capture_output=True, text=True)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    pages = sorted(glob.glob(os.path.join(work, "0*_*.html"))) + glob.glob(os.path.join(work, "*", "*", "20 Vorbereitung", "*.html"))
    for p in pages:
        rel = os.path.relpath(p, work)
        os.makedirs(os.path.dirname(os.path.join(out, rel)) or out, exist_ok=True)
        with open(p, encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(out, rel), "w", encoding="utf-8") as f:
            f.write(_clean(html, work, lang))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8"><title>Pitwall · Live-Demo</title>'
                '<meta http-equiv="refresh" content="0; url=01_cockpit.html"><a href="01_cockpit.html">Pitwall-Demo öffnen</a>')
    open(os.path.join(out, ".nojekyll"), "w").close()
    shutil.rmtree(work, ignore_errors=True)
    return len(pages)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the static live demo")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--lang", default="de", choices=["de", "en"])
    a = ap.parse_args(argv)
    print("Seiten:", build(os.path.abspath(a.out), a.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
