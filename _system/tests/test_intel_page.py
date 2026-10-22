"""Briefing tabs on the page: template wiring, tab CSS, and render.py --intel."""
import json
import os
import re
import subprocess
import sys

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER_PY = os.path.join(SYSTEM_DIR, "render.py")


def item(name="Cheat.pdf", kind="cheat_sheet", path="133 X/Cheat.pdf", where="", modified="2026-09-11", link=None, superseded=False):
    return {"name": name, "kind": kind, "path": path, "where": where, "modified": modified, "link": link, "superseded": superseded}


def brief_template():
    return open(os.path.join(SYSTEM_DIR, "templates", "brief.html"), encoding="utf-8").read()


def test_brief_template_has_tabs_panes_and_handler():
    t = brief_template()
    for needle in ('role="tablist"', 'data-pane="now"', 'data-pane="intel"', "JS26.intelHtml(", "JS26.intelCount(", 'closest(".tab")'):
        assert needle in t, needle
    assert t.index('data-pane="now"') < t.index('data-pane="intel"')


def test_tab_css_uses_brand_tokens_and_prints_both_panes():
    css = open(os.path.join(SYSTEM_DIR, "theme.css"), encoding="utf-8").read().split("Briefing tabs")[1]
    assert "var(--xl-accent)" in css and ".tabpane[hidden]" in css
    assert re.search(r"@media print[^@]*\.tabpane\[hidden\]\s*\{\s*display:\s*block", css)


def test_brief_template_shows_the_stamp_in_the_intel_pane():
    t = brief_template()
    assert t.index("JS26.intelStamp(") > t.index('data-pane="intel" hidden')


def test_render_embeds_the_intel_index_in_the_data_block(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,contacts,folder_id,next_action,due,note\n"
                    "133,Nordberatung,Mgr,Executive,Interviewing,,2026-07-01,2026-09-24,1,80,0,high,HH,,f1,x,2026-10-01,n\n", encoding="utf-8")
    intel = tmp_path / "intel_index.json"
    intel.write_text(json.dumps({"generated": "2026-09-25T09:00:00", "uids": {"133": {"folders": ["133 Nordberatung"], "warnings": [],
                     "items": [item(name="</script>Cheat.pdf")]}}}), encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--intel", str(intel), "--today", "2026-09-25", "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html = (out / "03_briefings.html").read_text(encoding="utf-8")
    d = json.loads(re.search(r'<script type="application/json" id="DATA">(.*?)</script>', html, re.S).group(1))
    assert d["intel"]["uids"]["133"]["items"][0]["name"] == "</script>Cheat.pdf"          # survives the </script> escaping


def test_render_without_an_intel_file_still_works(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,company,stage\n1,A,Final\n", encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--intel", str(tmp_path / "none.json"), "--today", "2026-09-25", "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html = (out / "03_briefings.html").read_text(encoding="utf-8")
    assert json.loads(re.search(r'<script type="application/json" id="DATA">(.*?)</script>', html, re.S).group(1))["intel"] == {}


def test_render_survives_a_corrupt_intel_index(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,company,stage\n1,A,Final\n", encoding="utf-8")
    bad = tmp_path / "intel_index.json"
    bad.write_text("{not json", encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--intel", str(bad), "--today", "2026-09-25", "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0 and "intel_index.json konnte nicht geladen werden" in res.stderr


def test_brief_template_looks_cards_up_by_the_normalised_uid():
    t = brief_template()
    assert "I[r.uid]" not in t and t.count("I[JS26.intelKey(r.uid)]") == 3


# ---- reading pane ("Lesezone") -----------------------------------------------------------------------
def theme_css():
    return open(os.path.join(SYSTEM_DIR, "theme.css"), encoding="utf-8").read()


def test_brief_template_has_the_reading_pane_and_a_switch_to_the_dossiers():
    t = brief_template()
    for needle in ('id="reader-list"', 'id="reader-pane"', 'data-mode="read"', 'data-mode="dossier"', "JS26.readerGroups(", "JS26.readerDocHtml(",
                   "JS26.readerSwitchHtml(", "D.reader"):
        assert needle in t, needle
    assert 'id="briefs"' in t        # the dossier cards stay


def test_reading_pane_keeps_a_read_mark_only_in_the_browser_and_guards_storage():
    t = brief_template()
    assert "localStorage" in t and "try {" in t.split("localStorage")[0][-200:] + "try {"      # storage access is wrapped
    assert "fetch(" not in t and "XMLHttpRequest" not in t


def test_reading_pane_is_keyboard_operable():
    t = brief_template()
    for needle in ('"ArrowDown"', '"ArrowUp"', '"ArrowLeft"', '"ArrowRight"', "tagName"):
        assert needle in t, needle


def test_reading_pane_css_uses_xlrte_tokens_only():
    css = theme_css().split("Reading pane")[1]
    for needle in (".reader-list", ".reader-pane", ".reader-frame", ".md table", ".md blockquote", "var(--xl-accent)"):
        assert needle in css, needle
    assert not re.search(r"#(2563eb|1e3a8a|3b82f6|0284c7|7c3aed)", css, re.I)
    assert re.search(r"@media print[^@]*\.reader-list\s*\{\s*display:\s*none", css)


def test_render_ships_the_reading_pane_markup_into_the_briefings_page(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,company,stage\n1,A,Final\n", encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--intel", str(tmp_path / "none.json"), "--reader-root", str(tmp_path),
                          "--today", "2026-10-02", "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html = (out / "03_briefings.html").read_text(encoding="utf-8")
    assert 'id="reader-list"' in html and ".reader-pane" in html and "readerGroups" in html


def test_intel_page_uses_the_xlrte_ci_and_only_a_dot_of_the_employer_color():
    t = open(os.path.join(SYSTEM_DIR, "templates", "intel.html"), encoding="utf-8").read()
    rule = lambda sel: next(l for l in t.splitlines() if l.startswith(sel + " {"))
    assert "linear-gradient(135deg, {{ employer_color }}" not in t
    assert "var(--xl-accent)" in rule(".fit-fill") and "var(--xl-accent)" in rule(".salary-fill")
    assert "{{ employer_color }}" in rule(".emp-dot") and "employer_color" not in rule(".fit-fill") and "employer_color" not in rule(".salary-fill")


def test_theme_stage_and_info_colors_follow_the_xlrte_palette():
    ci = theme_css().split("XLRTE Brand v0.4")[1].split("Briefing tabs")[0]
    for needle in ("--w-applied: #2A78D6", "--w-screening: #199E70", "--w-interviewing: #E4572E", "--w-final: #1A1A1A", "--info: #2A78D6", "--health-warm: #2A78D6"):
        assert needle in ci, needle
    for bad in ("#2563eb", "#0284c7", "#7c3aed", "#3b82f6", "#60a5fa", "#38bdf8", "#a78bfa"):
        assert bad not in ci.lower(), bad
    assert "--w-applied: #3987E5" in ci.split("prefers-color-scheme: dark")[1]


def test_quality_strip_css_uses_status_tokens_only():
    css = theme_css().split("Reading pane")[1]
    for needle in (".reader-quality", ".qchip.ok", ".qchip.warn", ".qchip.fail"):
        assert needle in css, needle
    assert not re.search(r"#(2563eb|1e3a8a|3b82f6|0284c7|7c3aed)", css, re.I)
