"""Today page: view context, rendering with both template engines. Synthetic data only (no Drive files needed)."""
import json
import os
import re
import subprocess
import sys

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import today_view as TV  # noqa: E402
from test_brand import contrast, css_block, theme, var  # noqa: E402

RENDER_PY = os.path.join(SYSTEM_DIR, "render.py")
TODAY = "2026-09-25"
COLS = ("uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,"
        "contacts,folder_id,next_action,due,note\n")


def pipeline_csv(path):
    rows = [
        "133,Nordberatung,Senior Manager Data & AI,Executive,Interviewing,,2026-07-01,2026-09-24,1,80,0,high,Hamburg,,f1,Teams-Link klären,2026-09-20,Gespräch mit Head of AI",
        "215,Blanco GmbH,Head of E-Commerce,Executive,Watchlist,,,2026-09-25,0,0,0,mid,DE,,,,,Discovered via portal 2026-09-25 — pending TypeSafe fit score",
        "154,Codewerk,Director,Executive,Final,,2026-08-01,2026-09-10,15,70,0,high,DE,,f2,Angebot prüfen,2026-10-30,Finale Runde",
        "131,Hansehandel,Teamleiter,Executive,Closed,rejected,2026-07-01,2026-09-08,17,10,0,low,DE,,f3,,2026-09-01,abgelehnt",
    ]
    path.write_text(COLS + "\n".join(rows) + "\n", encoding="utf-8")


def health_json(path, status="Act"):
    checks = [{"id": "capacity", "group": "warranty", "name": "Capacity · Jev tokens", "status": status,
               "reason": "SPIKE: 9× the median", "target": "no spike"},
              {"id": "profile", "group": "improvement", "name": "Capability profile", "status": "OK",
               "reason": "reviewed 3 d ago", "target": "within 30 d"}]
    path.write_text(json.dumps({"generated": "2026-09-25T09:00:00", "today": TODAY, "overall": status, "checks": checks,
                                "problems": [], "incidents": ["Run gap: previous run 100 h ago"],
                                "deploy": {"date": "2026-09-25", "commit": "018bbad"}}), encoding="utf-8")


def render_all(tmp_path, with_health=True):
    data = tmp_path / "pipeline.csv"
    pipeline_csv(data)
    hp = tmp_path / "health.json"
    if with_health:
        health_json(hp)
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "none.json"),
                          "--folders", str(tmp_path / "none.tsv"), "--transitions", str(tmp_path / "none.csv"),
                          "--health", str(hp), "--today", TODAY, "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return out


# ---- today_view ---------------------------------------------------------------------------------
def rows():
    return [{"uid": "1", "company": "A", "role": "r", "stage": "Applied", "due": "2026-09-20", "next_action": "call",
             "days_idle": "3", "note": "n", "last_event": "2026-09-24"},
            {"uid": "2", "company": "B", "role": "r", "stage": "Final", "due": "2026-09-27", "next_action": "x",
             "days_idle": "1", "note": "n", "last_event": "2026-09-24"},
            {"uid": "3", "company": "C", "role": "r", "stage": "Applied", "due": "2026-10-30", "next_action": "later"},
            {"uid": "4", "company": "D", "role": "r", "stage": "Closed", "due": "2026-09-01"},
            {"uid": "5", "company": "E", "role": "r", "stage": "Watchlist",
             "note": "Discovered via portal 2026-09-25 — pending TypeSafe fit score"}]


def test_needs_are_sorted_flag_overdue_and_skip_closed_and_far_dates():
    ctx = TV.build_context(rows(), None, TODAY)
    assert [n["uid"] for n in ctx["needs"]] == ["1", "2"]
    assert ctx["needs"][0]["overdue"] == "overdue" and ctx["needs"][1]["overdue"] == ""
    assert ctx["n_overdue"] == 1


def test_new_today_and_live_order():
    ctx = TV.build_context(rows(), None, TODAY)
    assert [n["uid"] for n in ctx["new_today"]] == ["5"]
    assert [p["stage"] for p in ctx["live"]] == ["Final", "Applied", "Applied"]      # Final before Applied, no Watchlist/Closed


def test_missing_health_shows_act_row_not_blank():
    ctx = TV.build_context(rows(), None, TODAY)
    assert ctx["overall"] == "Act" and ctx["checks"][0]["status_label"] == "Handeln"
    assert "health.json missing" in ctx["checks"][0]["reason"]


def test_status_labels_pair_icon_and_word():
    for s in ("OK", "Watch", "Act"):
        assert TV.STATUS_ICON[s] and TV.STATUS_LABEL[s]
    assert len({TV.STATUS_ICON[s] for s in TV.STATUS_ICON}) == 3


def test_long_notes_are_shortened():
    r = rows()[:1]
    r[0]["note"] = "x" * 500
    assert len(TV.build_context(r, None, TODAY)["live"][0]["note"]) <= TV.NOTE_MAX


# ---- rendering: full CLI run --------------------------------------------------------------------
def test_render_writes_today_first_in_nav_on_every_page(tmp_path):
    out = render_all(tmp_path)
    for name in ("00_today.html", "01_cockpit.html", "02_pipeline_crm.html", "03_briefings.html", "04_agentur_report.html"):
        html = (out / name).read_text(encoding="utf-8")
        nav = re.search(r'<nav class="views">(.*?)</nav>', html, re.S).group(1)
        assert nav.index("00_today.html") < nav.index("01_cockpit.html"), name


def test_today_page_shows_health_incident_needs_and_new(tmp_path):
    raw = (render_all(tmp_path) / "00_today.html").read_text(encoding="utf-8")
    html = re.sub(r"<script.*?</script>", "", raw, flags=re.S)        # visible page only; DATA JSON holds every row
    assert "Handeln" in html and "Capacity · Jev tokens" in html and "SPIKE" in html
    assert "Störung" in html and "Run gap" in html
    assert "Teams-Link klären" in html and 'class="trow overdue"' in html
    assert "Neu entdeckt" in html and "Blanco GmbH" in html
    assert "Letzter Deploy: 2026-09-25 · 018bbad" in html
    assert "abgelehnt" not in html                       # closed rows never appear
    assert "{{" not in html and "{%" not in html


def test_today_without_health_file_still_renders(tmp_path):
    html = (render_all(tmp_path, with_health=False) / "00_today.html").read_text(encoding="utf-8")
    assert "health.json missing" in html


# ---- rendering: zero-dependency engine ----------------------------------------------------------
def test_today_template_renders_in_fallback_engine(monkeypatch):
    import render
    monkeypatch.setattr(render, "HAS_JINJA", False)
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    hp = {"generated": "2026-09-25T09:00:00", "today": TODAY, "overall": "Watch", "incidents": [],
          "checks": [{"id": "x", "group": "utility", "name": "Data quality", "status": "Watch", "reason": "0 errors, 5 warnings",
                      "target": "t"}]}
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="",
                         data_json="{}", footer="", logo_svg="<svg></svg>", favicon_uri="", **TV.build_context(rows(), hp, TODAY))
    assert "Beobachten" in html and "Data quality" in html and "call" in html
    assert "{{" not in html and "{%" not in html


def test_status_marker_colours_are_graphics_only_at_3_to_1():
    """Watch ochre fails 4.5:1 as text, so the word stays in ink and only the marker uses the colour."""
    light = css_block(theme().split("XLRTE Brand v0.4")[1], ":root {")
    assert contrast(var(light, "--xl-watch"), var(light, "--panel")) >= 3.0
    tpl = open(os.path.join(SYSTEM_DIR, "templates", "today.html"), encoding="utf-8").read()
    assert ".hs { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--ink); }" in tpl


# ---- review focus: awkward inputs ---------------------------------------------------------------
def test_html_in_company_and_note_is_escaped_in_fallback_engine(monkeypatch):
    import render
    monkeypatch.setattr(render, "HAS_JINJA", False)
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    bad = rows()
    bad[0]["company"] = "<script>alert(1)</script>"
    bad[0]["next_action"] = '"><img src=x onerror=alert(2)>'
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="",
                         data_json="{}", footer="", logo_svg="", favicon_uri="", **TV.build_context(bad, None, TODAY))
    visible = re.sub(r"<script>\s*\(function.*?</script>", "", html, flags=re.S)
    assert "<script>alert(1)" not in visible and "<img src=x" not in visible
    assert "&lt;script&gt;alert(1)" in visible


def test_garbage_due_dates_and_missing_columns_do_not_break_the_view():
    r = [{"uid": "1", "company": "A", "stage": "Applied", "due": "TBD"},
         {"uid": "2", "company": "B", "stage": "Applied", "due": "30.09.2026"},
         {"stage": "Applied"}]
    ctx = TV.build_context(r, None, TODAY)
    assert ctx["needs"] == [] and len(ctx["live"]) == 3


def test_health_file_with_unknown_status_value_is_reported_not_crashed():
    bad = {"generated": "2026-09-25T09:00:00", "today": TODAY, "overall": "Act", "incidents": [],
           "checks": [{"id": "x", "group": "utility", "name": "X", "status": "Act", "reason": "r", "target": "t"}]}
    assert TV.build_context([], bad, TODAY)["n_act"] == 1


# ---- final review, fix pass ---------------------------------------------------------------------
def test_due_dates_are_parsed_in_the_today_view():
    r = [{"uid": "1", "company": "A", "stage": "Applied", "due": "01.10.2026"},
         {"uid": "2", "company": "B", "stage": "Applied", "due": "20.10.2026"},
         {"uid": "3", "company": "C", "stage": "Applied", "due": " 2026-09-27"}]
    ctx = TV.build_context(r, None, TODAY)
    assert [n["uid"] for n in ctx["needs"]] == ["3"] and ctx["needs"][0]["due"] == "2026-09-27"


def test_health_json_from_another_day_is_flagged_act():
    stale = {"generated": "2026-09-24T09:00:00", "today": "2026-09-24", "overall": "OK", "incidents": [],
             "checks": [{"id": "x", "group": "utility", "name": "X", "status": "OK", "reason": "r", "target": "t"}]}
    ctx = TV.build_context([], stale, TODAY)
    assert ctx["overall"] == "Act" and ctx["checks"][0]["id"] == "health_stale"
    assert "2026-09-24" in ctx["checks"][0]["reason"]


def test_row_text_cannot_close_the_embedded_data_block(tmp_path):
    data = tmp_path / "pipeline.csv"
    evil = "</script><!--<script><img src=x onerror=alert(2)>Acme"
    data.write_text(COLS + "1,%s,Role,Executive,Applied,,2026-07-01,2026-09-24,1,50,0,mid,HH,,f1,x,2026-10-01,n\n" % evil, encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    for name in ("00_today.html", "01_cockpit.html"):
        html = (out / name).read_text(encoding="utf-8")
        m = re.search(r'<script type="application/json" id="DATA">(.*?)</script>', html, re.S)
        assert any(r["company"] == evil for r in json.loads(m.group(1))["rows"]), name
        raw_block = m.group(1)
        assert "<!--" not in raw_block and "</" not in raw_block, name        # nothing that can end or re-open the script state
        visible = re.sub(r'<script type="application/json" id="DATA">.*?</script>', "", html, flags=re.S)
        assert "<img src=x" not in visible, name                              # inside the JSON it is inert text; outside it would run


# ---- layout defects seen in the browser (2026-09-25) ---------------------------------------------
def test_today_rows_have_room_for_stage_and_date_and_do_not_reuse_the_pill_class():
    tpl = open(os.path.join(SYSTEM_DIR, "templates", "today.html"), encoding="utf-8").read()
    m = re.search(r"\.trow \{ display: grid; grid-template-columns: ([\d.]+)em 1fr auto;", tpl)
    assert m and float(m.group(1)) >= 7.5, "first column must fit 'Interviewing' and '2026-09-08'"
    assert "white-space: nowrap" in tpl.split(".trow .due")[1].split("}")[0]
    assert 'class="pill"' not in tpl, "'.pill' is the existing stage-pill style (adds a dot); use .uidtag"


# ---- cheat-sheet status on the live-process list ------------------------------------------------
def intel_for(**counts):
    """intel_index-shaped dict: {uid: n_current} plus one superseded file for uid '2'."""
    uids = {}
    for uid, n in counts.items():
        items = [{"name": "f%d.pdf" % i, "kind": "cheat_sheet", "superseded": False} for i in range(n)]
        if uid == "u2":
            items.append({"name": "old.pdf", "kind": "cheat_sheet", "superseded": True})
        uids[uid[1:]] = {"items": items, "warnings": [], "folders": []}
    return {"uids": uids}


def live_rows():
    return [{"uid": "1", "company": "A", "stage": "Interviewing", "role": "r"},
            {"uid": "2", "company": "B", "stage": "Final", "role": "r"},
            {"uid": "3", "company": "C", "stage": "Applied", "role": "r"},
            {"uid": "4", "company": "D", "stage": "Screening", "role": "r"}]


def test_live_rows_show_cheat_sheet_count_and_flag_missing_ones_in_interview_stages():
    ctx = TV.build_context(live_rows(), None, TODAY, intel_for(u1=0, u2=2, u3=0, u4=1))
    by = {p["uid"]: p for p in ctx["live"]}
    assert by["1"]["intel_label"] == "kein Cheat Sheet" and by["1"]["intel_flag"] == "missing"
    assert by["2"]["intel_label"] == "2 Cheat Sheets" and by["2"]["intel_flag"] == ""          # superseded copy not counted
    assert by["3"]["intel_label"] == ""                                                        # Applied with none: no noise
    assert by["4"]["intel_label"] == "1 Cheat Sheet"


def test_without_an_intel_index_no_labels_are_invented():
    ctx = TV.build_context(live_rows(), None, TODAY)
    assert all(p["intel_label"] == "" and p["intel_flag"] == "" for p in ctx["live"])
    ctx = TV.build_context(live_rows(), None, TODAY, {})
    assert all(p["intel_label"] == "" for p in ctx["live"])


def test_uid_missing_from_the_index_counts_as_no_cheat_sheet_in_interview_stages():
    ctx = TV.build_context(live_rows(), None, TODAY, {"uids": {}})
    by = {p["uid"]: p for p in ctx["live"]}
    assert by["1"]["intel_flag"] == "missing" and by["3"]["intel_label"] == ""


def test_cheat_sheet_label_is_rendered_on_the_page(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "133,Nordberatung,Mgr,Executive,Final,,2026-07-01,2026-09-24,1,80,0,high,HH,,f1,x,2026-10-01,n\n", encoding="utf-8")
    intel = tmp_path / "intel_index.json"
    intel.write_text(json.dumps({"uids": {"133": {"items": [], "warnings": [], "folders": ["133 Nordberatung"]}}}), encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--intel", str(intel), "--today", TODAY, "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html = re.sub(r"<script.*?</script>", "", (out / "00_today.html").read_text(encoding="utf-8"), flags=re.S)
    assert "kein Cheat Sheet" in html and 'class="uidtag missing"' in html


# ---- headhunter channels (channels.json) --------------------------------------------------------
def channels_for(uid="1", **entry):
    base = {"type": "headhunter", "label": "Headhunter", "contact": "Max Beispiel",
            "leads": [{"person": "Erika Beispiel", "org": "Musterfirma", "note": "bereit zu sprechen", "status": "offen", "next": "Termin klären"}]}
    base.update(entry)
    return {"channels": {uid: base}}


def test_channel_rows_show_the_channel_tag_and_never_the_missing_flag():
    ctx = TV.build_context(live_rows(), None, TODAY, intel_for(u1=0, u2=0), channels_for("1"))
    by = {p["uid"]: p for p in ctx["live"]}
    assert by["1"]["channel_label"] == "Headhunter" and by["1"]["intel_label"] == "" and by["1"]["intel_flag"] == ""
    assert by["2"]["channel_label"] == "" and by["2"]["intel_flag"] == "missing"      # a normal process is still flagged


def test_channel_with_cheat_sheets_still_shows_their_count():
    ctx = TV.build_context(live_rows(), None, TODAY, intel_for(u1=2), channels_for("1"))
    assert {p["uid"]: p for p in ctx["live"]}["1"]["intel_label"] == "2 Cheat Sheets"


def test_leads_are_composed_into_one_readable_line():
    ctx = TV.build_context(live_rows(), None, TODAY, None, channels_for("1"))
    lead = {p["uid"]: p for p in ctx["live"]}["1"]["leads"][0]["text"]
    assert lead == "Erika Beispiel · Musterfirma — bereit zu sprechen (offen) → Termin klären"


def test_malformed_channel_entries_are_ignored_not_fatal():
    bad = {"channels": {"1": "headhunter", "2": {"leads": "Erika"}, "3": {"leads": [7, {"person": "X"}]}}}
    ctx = TV.build_context(live_rows(), None, TODAY, None, bad)
    by = {p["uid"]: p for p in ctx["live"]}
    assert by["1"]["channel_label"] == "" and by["2"]["leads"] == [] and by["3"]["leads"][0]["text"] == "X"
    assert TV.build_context(live_rows(), None, TODAY, None, {"channels": []})["live"]      # wrong container type


def test_channel_and_lead_text_is_escaped_on_the_page(monkeypatch):
    import render
    monkeypatch.setattr(render, "HAS_JINJA", False)
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    ch = channels_for("1", label="<b>HH</b>", leads=[{"person": "<img src=x onerror=alert(1)>", "org": "O"}])
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="",
                         data_json="{}", footer="", logo_svg="", favicon_uri="", **TV.build_context(live_rows(), None, TODAY, None, ch))
    assert "<img src=x" not in html and "<b>HH</b>" not in html and "&lt;img src=x" in html


def test_render_reads_channels_json_and_survives_a_corrupt_one(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "119,Beispiel-Headhunter,Netzwerk,IT Leadership,Interviewing,,2026-06-16,2026-09-01,24,75,10,,HH,,f1,,,n\n", encoding="utf-8")
    good = tmp_path / "channels.json"
    good.write_text(json.dumps(channels_for("119")), encoding="utf-8")

    def run(channels):
        out = tmp_path / "out"
        return subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                               "--transitions", str(tmp_path / "n.csv"), "--channels", str(channels), "--intel", str(tmp_path / "i.json"),
                               "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True), out
    res, out = run(good)
    assert res.returncode == 0, res.stderr
    html = re.sub(r"<script.*?</script>", "", (out / "00_today.html").read_text(encoding="utf-8"), flags=re.S)
    assert "Erika Beispiel · Musterfirma" in html and 'class="uidtag channel"' in html
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    res, out = run(bad)
    assert res.returncode == 0 and "channels.json konnte nicht geladen werden" in res.stderr


# ---- final review, fix pass ---------------------------------------------------------------------
def test_zero_padded_uids_find_their_index_and_channel_entries():
    rows = [{"uid": "09", "company": "A", "stage": "Interviewing", "role": "r"}, {"uid": "7", "company": "B", "stage": "Final", "role": "r"}]
    intel = {"uids": {"9": {"items": [{"name": "f.pdf", "kind": "cheat_sheet", "superseded": False}], "warnings": [], "folders": []}}}
    channels = {"channels": {"007": {"type": "headhunter", "leads": [{"person": "X"}]}}}
    by = {p["uid"]: p for p in TV.build_context(rows, None, TODAY, intel, channels)["live"]}
    assert by["09"]["intel_label"] == "1 Cheat Sheet" and by["09"]["intel_flag"] == ""        # "09" finds key "9"
    assert by["7"]["channel_label"] == "Headhunter" and by["7"]["intel_flag"] == ""            # "7" finds key "007"


def test_non_text_values_in_channels_json_never_break_the_page(tmp_path):
    odd = {"channels": {"1": {"type": 3, "label": 5, "contact": ["x"], "leads": [
        {"person": 42, "org": True, "note": {"a": 1}, "status": 1, "next": 2.5}, {"person": None}]}}}
    ctx = TV.build_context(live_rows(), None, TODAY, None, odd)
    lead = {p["uid"]: p for p in ctx["live"]}["1"]["leads"]
    assert lead[0]["text"] == "42 (1) → 2.5"                                                  # numbers kept, bool/dict/list dropped
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "1,A,r,Executive,Interviewing,,2026-07-01,2026-09-24,1,80,0,high,HH,,f1,x,2026-10-01,n\n", encoding="utf-8")
    ch = tmp_path / "channels.json"
    ch.write_text(json.dumps(odd), encoding="utf-8")
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--channels", str(ch), "--today", TODAY, "--out", str(tmp_path / "out"), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


# ---- own finds and Top 10 (application path, stage 1) --------------------------------------------
def find_rows():
    return [{"uid": "215", "company": "Blanco", "role": "Head of E-Com", "stage": "Watchlist", "note": "Eigener Fund (Eingang 2026-09-26)"},
            {"uid": "133", "company": "Nordberatung", "role": "Mgr", "stage": "Interviewing"},
            {"uid": "216", "company": "Acme", "role": "CIO", "stage": "Watchlist"},
            {"uid": "217", "company": "Old", "role": "X", "stage": "Closed"}]


def test_pinned_rows_show_stage_chips_in_pin_order_and_count_the_slots():
    top = {"pinned": [215, 133, 216, 217, 999], "excluded": []}
    ctx = TV.build_context(find_rows(), None, TODAY, top10=top, prep={"216": {"management_summary": "x"}})
    assert [f["uid"] for f in ctx["own_finds"]] == ["215", "133", "216", "217"]                 # 999 has no row: skipped
    assert [f["chip"] for f in ctx["own_finds"]] == ["Eingegangen", "Interviewing", "Vorbereitet", "Geschlossen"]
    assert ctx["own_slots"] == "4 von 10 Fokus-Plätzen durch eigene Funde belegt"


def test_no_top10_file_means_an_empty_list_and_no_slot_text():
    ctx = TV.build_context(find_rows(), None, TODAY)
    assert ctx["own_finds"] == [] and ctx["own_slots"] == "" and ctx["intake_lines"] == []
    assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": "215"})["own_finds"] == []     # wrong shape is ignored


def test_intake_problems_are_listed_unclear_first_then_failures():
    rep = {"unclear": [{"file": "x.pdf", "reason": "Firma/Rolle fehlt"}], "failed": [{"file": "y.md", "error": "disk full"}, "junk"]}
    lines = TV.build_context(find_rows(), None, TODAY, intake=rep)["intake_lines"]
    assert lines == [{"label": "Unklar", "file": "x.pdf", "reason": "Firma/Rolle fehlt", "href": "_Eingang/x.pdf", "target": "x.pdf"},
                     {"label": "Fehler", "file": "y.md", "reason": "disk full", "href": "_Eingang/y.md", "target": "y.md"}]
    assert TV.build_context(find_rows(), None, TODAY, intake={"unclear": "x"})["intake_lines"] == []


def test_own_finds_section_is_rendered_and_escaped_in_the_fallback_engine(monkeypatch):
    import render
    monkeypatch.setattr(render, "HAS_JINJA", False)
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    rows = find_rows()
    rows[0]["company"] = "<img src=x onerror=alert(1)>"
    ctx = TV.build_context(rows, None, TODAY, top10={"pinned": [215], "excluded": []},
                           intake={"unclear": [{"file": "<b>a</b>.pdf", "reason": "r"}]})
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="",
                         data_json="{}", footer="", logo_svg="", favicon_uri="", **ctx)
    assert "Eigene Funde" in html and "1 von 10 Fokus-Plätzen durch eigene Funde belegt" in html and "Eingegangen" in html and "Im Eingang" in html
    assert "<img src=x" not in html and "<b>a</b>" not in html and "&lt;img src=x" in html


def test_render_reads_top10_and_intake_report_and_survives_corrupt_files(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Watchlist,,,2026-09-26,0,0,0,,HH,,,,,Eigener Fund,,\n", encoding="utf-8")
    top = tmp_path / "top10.json"
    top.write_text(json.dumps({"pinned": [215]}), encoding="utf-8")
    rep = tmp_path / "intake_report.json"
    rep.write_text(json.dumps({"unclear": [{"file": "z.pdf", "reason": "Firma/Rolle fehlt"}]}), encoding="utf-8")

    def go(top10_path, report_path):
        out = tmp_path / "out"
        res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                              "--transitions", str(tmp_path / "n.csv"), "--top10", str(top10_path), "--intake-report", str(report_path),
                              "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
        return res, re.sub(r"<script.*?</script>", "", (out / "00_today.html").read_text(encoding="utf-8"), flags=re.S) if res.returncode == 0 else ""
    res, html = go(top, rep)
    assert res.returncode == 0, res.stderr
    assert "Blanco" in html and "1 von 10 Fokus-Plätzen durch eigene Funde belegt" in html and "z.pdf" in html and "Firma/Rolle fehlt" in html
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    res, html = go(bad, bad)
    assert res.returncode == 0 and "intake_report.json konnte nicht geladen werden" in res.stderr and "Noch keine eigenen Funde" in html


# ---- Eingang robustness (Stage 1.1) -------------------------------------------------------------
def test_waiting_and_already_processed_files_are_listed_so_nothing_sits_unseen():
    rep = {"unclear": [{"file": "u.pdf", "reason": "r"}], "failed": [{"file": "f.md", "error": "e"}],
           "waiting": [{"file": "w.pdf", "reason": "wird noch geschrieben"}], "already": [{"file": "a.pdf", "uid": 215}]}
    lines = TV.build_context(find_rows(), None, TODAY, intake=rep)["intake_lines"]
    assert [l["label"] for l in lines] == ["Unklar", "Fehler", "Wartet", "Bereits verarbeitet"]
    assert "uid 215" in lines[3]["reason"] and "entfernen" in lines[3]["reason"]


def test_the_intake_list_is_capped_with_a_remainder_line():
    rep = {"already": [{"file": "f%d.pdf" % i, "uid": 1} for i in range(20)]}
    lines = TV.build_context(find_rows(), None, TODAY, intake=rep)["intake_lines"]
    assert len(lines) == 9 and lines[-1]["file"] == "…" and "12 weitere" in lines[-1]["reason"]


# ---- clickable intake entries (Stage 1.2) -----------------------------------------------------------
def test_intake_entries_link_to_the_file_to_open_relative_to_the_pages():
    rep = {"unclear": [{"file": "a b.pdf", "reason": "r", "edit": "a b.md"}, {"file": "c.pdf", "reason": "r", "sidecar": "c.md"},
                       {"file": "d.docx", "reason": "r"}, {"file": "javascript:alert(1).pdf", "reason": "r"}],
           "waiting": [{"file": "w.pdf", "reason": "r"}], "already": [{"file": "z.pdf", "uid": 1}]}
    lines = TV.build_context(find_rows(), None, TODAY, intake=rep)["intake_lines"]
    assert [l["href"] for l in lines] == ["_Eingang/a%20b.md", "_Eingang/c.md", "_Eingang/d.docx", "_Eingang/javascript%3Aalert%281%29.pdf",
                                          "_Eingang/w.pdf", "_Eingang/z.pdf"]
    assert [l["target"] for l in lines][:3] == ["a b.md", "c.md", "d.docx"]                # the link says which file it opens


def test_the_confirm_hint_shows_only_when_something_needs_confirming():
    with_unclear = TV.build_context(find_rows(), None, TODAY, intake={"unclear": [{"file": "a.pdf", "reason": "r", "edit": "a.md"}]})
    only_waiting = TV.build_context(find_rows(), None, TODAY, intake={"waiting": [{"file": "w.pdf", "reason": "r"}]})
    assert with_unclear["intake_hint"] == "yes" and only_waiting["intake_hint"] == ""


def test_the_intake_card_links_the_file_and_shows_the_confirm_command_in_both_engines(monkeypatch):
    import render
    monkeypatch.setattr(render, "HAS_JINJA", False)
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    rep = {"unclear": [{"file": "<b>x</b>.pdf", "reason": "r", "edit": "x.md"}]}
    ctx = TV.build_context(find_rows(), None, TODAY, intake=rep)
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="",
                         data_json="{}", footer="", logo_svg="", favicon_uri="", **ctx)
    assert 'href="_Eingang/x.md"' in html and "&lt;b&gt;x&lt;/b&gt;.pdf" in html and "<b>x</b>" not in html and "--confirm" in html
    assert ">x.md</a>" in html                                                             # the link text names the file it opens


def test_own_finds_show_the_coverage_share_and_ignore_malformed_entries():
    cov = {"215": {"share": 0.6667, "proven": 4, "must": 6, "below": False, "hard_gaps": 0}}
    assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, coverage=cov)["own_finds"][0]["coverage"] == "Abdeckung 67 % (4 von 6 Muss)"
    low = {"215": {"share": 0.25, "proven": 1, "must": 4, "below": True, "hard_gaps": 2}}
    assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, coverage=low)["own_finds"][0]["coverage"] == \
        "Abdeckung 25 % (1 von 4 Muss) · unter der Schwelle · 2 harte Lücken"
    for bad in ({"215": {"share": None, "proven": 0, "must": 0}}, {"215": "x"}, {"215": {"share": True, "proven": 1, "must": 1}}, {}, [], None):
        assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, coverage=bad)["own_finds"][0]["coverage"] == ""


def test_coverage_line_is_rendered_in_the_fallback_engine_and_escaped(monkeypatch):
    import render
    monkeypatch.setattr(render, "HAS_JINJA", False)
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    ctx = TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, coverage={"215": {"share": 0.5, "proven": 2, "must": 4}})
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="",
                         data_json="{}", footer="", logo_svg="", favicon_uri="", **ctx)
    assert "Abdeckung 50 % (2 von 4 Muss)" in html


def test_render_reads_coverage_state_and_survives_a_corrupt_file(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Watchlist,,,2026-09-26,0,0,0,,HH,,,,,Eigener Fund,,\n", encoding="utf-8")
    top = tmp_path / "top10.json"
    top.write_text(json.dumps({"pinned": [215]}), encoding="utf-8")

    def go(cov):
        out = tmp_path / "out"
        res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                              "--transitions", str(tmp_path / "n.csv"), "--top10", str(top), "--coverage", str(cov), "--rank", str(tmp_path / "norank.json"),
                              "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
        return res, (out / "00_today.html").read_text(encoding="utf-8") if res.returncode == 0 else ""
    good = tmp_path / "coverage_state.json"
    good.write_text(json.dumps({"215": {"share": 0.5, "proven": 2, "must": 4}}), encoding="utf-8")
    res, html = go(good)
    assert res.returncode == 0, res.stderr
    assert "Abdeckung 50 % (2 von 4 Muss)" in html
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    res, html = go(bad)
    assert res.returncode == 0 and "coverage_state.json konnte nicht geladen werden" in res.stderr and "Abdeckung" not in html.split("<script")[0]


def test_coverage_entries_with_nan_or_infinite_values_are_ignored():
    for v in (float("nan"), float("inf")):
        cov = {"215": {"share": v, "proven": 1, "must": 2}}
        assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, coverage=cov)["own_finds"][0]["coverage"] == ""


def test_coverage_lookup_uses_the_same_uid_normalisation_as_the_rest_of_today():
    rows = find_rows()
    rows[0]["uid"] = "0215"
    cov = {"215": {"share": 0.5, "proven": 1, "must": 2}}
    assert TV.build_context(rows, None, TODAY, top10={"pinned": [215]}, coverage=cov)["own_finds"][0]["coverage"] == "Abdeckung 50 % (1 von 2 Muss)"


def test_own_finds_show_the_draft_stage_and_lint_result_in_order_of_progress():
    def view(cov=None, drafts=None):
        return TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, coverage=cov, drafts=drafts)["own_finds"][0]
    cov = {"215": {"share": 0.8, "proven": 4, "must": 5}}
    assert view()["chip"] == "Eingegangen" and view()["draft"] == ""
    assert view(cov)["chip"] == "Analysiert"
    job = {"215": {"job": {"version": 1}}}
    assert view(cov, job)["chip"] == "Bereit zum Entwurf" and "Auftrag bereit" in view(cov, job)["draft"]
    v1 = {"215": {"job": {"version": 1}, "latest": "v1", "versions": {"v1": {"result": "warn", "fails": 0, "warns": 2}}}}
    assert view(cov, v1)["chip"] == "Entwurf v1" and view(cov, v1)["draft"] == "Entwurf v1 · Lint: Warnungen (2 Warnungen)"
    v2 = {"215": {"latest": "v2", "versions": {"v2": {"result": "fail", "fails": 1, "warns": 1}, "v1": {"result": "pass"}}}}
    assert view(cov, v2)["draft"] == "Entwurf v2 · Lint: Fehler (1 Fehler, 1 Warnung)"
    ok = {"215": {"latest": "v3", "versions": {"v3": {"result": "pass", "fails": 0, "warns": 0}}}}
    assert view(cov, ok)["draft"] == "Entwurf v3 · Lint: bestanden"


def test_malformed_draft_state_is_ignored_and_a_stage_chip_wins():
    for bad in (None, [], {"215": "x"}, {"215": {"latest": "v9", "versions": {}}}, {"215": {"latest": "<b>", "versions": {"<b>": {"result": "pass"}}}}, {"215": {"versions": "x"}}):
        assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, drafts=bad)["own_finds"][0]["draft"] == ""
    rows = find_rows()
    rows[0]["stage"] = "Applied"
    d = {"215": {"latest": "v1", "versions": {"v1": {"result": "pass"}}}}
    got = TV.build_context(rows, None, TODAY, top10={"pinned": [215]}, drafts=d)["own_finds"][0]
    assert got["chip"] == "Beworben" and got["draft"] == "Entwurf v1 · Lint: bestanden"


def test_render_reads_draft_state_and_survives_a_corrupt_file(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Watchlist,,,2026-09-26,0,0,0,,HH,,,,,Eigener Fund,,\n", encoding="utf-8")
    top = tmp_path / "top10.json"
    top.write_text(json.dumps({"pinned": [215]}), encoding="utf-8")

    def go(path):
        out = tmp_path / "out"
        res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                              "--transitions", str(tmp_path / "n.csv"), "--top10", str(top), "--drafts", str(path),
                              "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
        return res, (out / "00_today.html").read_text(encoding="utf-8") if res.returncode == 0 else ""
    good = tmp_path / "draft_state.json"
    good.write_text(json.dumps({"215": {"latest": "v1", "versions": {"v1": {"result": "warn", "fails": 0, "warns": 2}}}}), encoding="utf-8")
    res, html = go(good)
    assert res.returncode == 0, res.stderr
    assert "Entwurf v1 · Lint: Warnungen (2 Warnungen)" in html
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    res, html = go(bad)
    assert res.returncode == 0 and "draft_state.json konnte nicht geladen werden" in res.stderr and "Lint:" not in html.split("<script")[0]


def test_draft_counts_are_bounded_and_never_negative():
    d = {"215": {"latest": "v1", "versions": {"v1": {"result": "warn", "fails": -2, "warns": 1e308}}}}
    assert TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, drafts=d)["own_finds"][0]["draft"] == "Entwurf v1 · Lint: Warnungen"


def test_draft_line_names_the_renderings_that_exist_for_the_latest_version():
    d = {"215": {"latest": "v1", "versions": {"v1": {"result": "pass"}}}}
    both = {"215": {"v1": {"files": ["CV_x_v1_ATS.docx", "CV_x_v1_ATS.pdf", "CV_x_v1_CI.pdf"]}}}
    one = {"215": {"v1": {"files": ["CV_x_v1_ATS.docx"]}}}
    def line(renders):
        return TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, drafts=d, renders=renders)["own_finds"][0]["draft"]
    assert line(both) == "Entwurf v1 · Lint: bestanden · Dateien: ATS + CI" and line(one) == "Entwurf v1 · Lint: bestanden · Dateien: ATS"
    assert line(None) == "Entwurf v1 · Lint: bestanden"
    stale = {"215": {"v0": {"files": ["CV_x_v0_ATS.docx"]}}}
    assert line(stale) == "Entwurf v1 · Lint: bestanden"                                                    # only the latest version counts


def test_malformed_render_state_is_ignored():
    d = {"215": {"latest": "v1", "versions": {"v1": {"result": "pass"}}}}
    for bad in ({"215": "x"}, {"215": {"v1": "x"}}, {"215": {"v1": {"files": "x"}}}, {"215": {"v1": {"files": [1, None, {"a": 1}]}}}, [], "x", None):
        got = TV.build_context(find_rows(), None, TODAY, top10={"pinned": [215]}, drafts=d, renders=bad)["own_finds"][0]["draft"]
        assert got == "Entwurf v1 · Lint: bestanden", bad


def test_render_reads_render_state_and_survives_a_corrupt_file(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Watchlist,,,2026-09-26,0,0,0,,HH,,,,,Eigener Fund,,\n", encoding="utf-8")
    top = tmp_path / "top10.json"
    top.write_text(json.dumps({"pinned": [215]}), encoding="utf-8")
    drafts = tmp_path / "draft_state.json"
    drafts.write_text(json.dumps({"215": {"latest": "v1", "versions": {"v1": {"result": "pass"}}}}), encoding="utf-8")

    def go(path):
        out = tmp_path / "out"
        res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                              "--transitions", str(tmp_path / "n.csv"), "--top10", str(top), "--drafts", str(drafts), "--renders", str(path),
                              "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
        return res, (out / "00_today.html").read_text(encoding="utf-8") if res.returncode == 0 else ""
    good = tmp_path / "render_state.json"
    good.write_text(json.dumps({"215": {"v1": {"files": ["a_ATS.docx", "a_CI.pdf"]}}}), encoding="utf-8")
    res, html = go(good)
    assert res.returncode == 0, res.stderr
    assert "Dateien: ATS + CI" in html
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    res, html = go(bad)
    assert res.returncode == 0 and "render_state.json konnte nicht geladen werden" in res.stderr and "Dateien:" not in html.split("<script")[0]


def test_live_rows_show_the_intel_work_state_from_intel_state():
    rows = find_rows()
    rows[0]["stage"] = "Interviewing"
    def work(state):
        live = TV.build_context(rows, None, TODAY, intel_state=state)["live"]
        return live[0]["intel_work"] if live else None
    job = {"215": {"jobs": {"a": {"doc": "briefing"}}}}
    docs = {"215": {"docs": {"briefing:": {"doc": "briefing", "latest": "v2", "versions": {"v2": {"result": "warn"}}}, "cheat_sheet:": {"doc": "cheat_sheet", "latest": "v1", "versions": {"v1": {"result": "pass"}}}}}}
    assert work(None) == "" and work(job) == "Briefing: Auftrag bereit" and work(docs) == "Briefing v2 · Lint: Warnungen"
    for bad in ([], "x", {"215": "x"}, {"215": {"docs": "x"}}, {"215": {"docs": {"a": {"doc": "<b>", "latest": "v1", "versions": {"v1": {}}}}}}, {"215": {"docs": {"a": {"doc": "briefing", "latest": ["v1"], "versions": {}}}}}, {"215": {"jobs": {"a": {"doc": "<script>"}}}}):
        assert work(bad) == "", bad


def test_render_reads_intel_state_and_survives_a_corrupt_file(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Interviewing,,,2026-09-26,0,0,0,,HH,,,,,Eigener Fund,,\n", encoding="utf-8")
    def go(path):
        out = tmp_path / "out"
        res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                              "--transitions", str(tmp_path / "n.csv"), "--intel-state", str(path), "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
        return res, (out / "00_today.html").read_text(encoding="utf-8") if res.returncode == 0 else ""
    good = tmp_path / "intel_state.json"
    good.write_text(json.dumps({"215": {"jobs": {"a": {"doc": "briefing"}}}}), encoding="utf-8")
    res, html = go(good)
    assert res.returncode == 0, res.stderr
    assert "Recherche: Briefing: Auftrag bereit" in html
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    res, html = go(bad)
    assert res.returncode == 0 and "intel_state.json konnte nicht geladen werden" in res.stderr and "Recherche:" not in html.split("<script")[0]


# ---- what the last run changed (e2e visibility) ------------------------------------------------------------------------
def crow(uid, company, role, stage, outcome=""):
    return {"uid": uid, "company": company, "role": role, "stage": stage, "outcome": outcome}


def test_changes_since_lists_new_rows_stage_changes_rejections_and_ignores_the_rest():
    before = [crow("1", "Alpha", "Head of X", "Applied"), crow("2", "Beta", "Lead Y", "Interviewing"), crow("3", "Gamma", "Dir Z", "Watchlist")]
    after = [crow("1", "Alpha", "Head of X", "Closed", "rejected"), crow("2", "Beta", "Lead Y", "Final"), crow("3", "Gamma", "Dir Z", "Watchlist"),
             crow("4", "Delta", "Manager W", "Applied")]
    got = TV.changes_since(after, before)
    assert [(c["label"], c["text"]) for c in got] == [("Absage", "Alpha · Head of X: Applied → Closed (rejected)"), ("Stufe", "Beta · Lead Y: Interviewing → Final"),
                                                      ("Neu", "Delta · Manager W (Applied)")]
    assert TV.changes_since(after, after) == [] and TV.changes_since(after, None) == [] and TV.changes_since(after, []) == []


def test_changes_since_is_capped_and_survives_malformed_rows():
    before = [crow(str(i), "C%d" % i, "R", "Applied") for i in range(30)]
    after = [crow(str(i), "C%d" % i, "R", "Screening") for i in range(30)]
    got = TV.changes_since(after, before)
    assert len(got) == TV.MAX_CHANGE_LINES + 1 and got[-1]["text"] == "und %d weitere" % (30 - TV.MAX_CHANGE_LINES)
    assert TV.changes_since([{"uid": None}, "x", {"uid": "1", "stage": "Applied"}], [{"uid": "1", "stage": "Applied"}, None, 5]) == []
    assert TV.changes_since([crow("1", "<b>A</b>", "R", "Closed", "rejected")], [crow("1", "<b>A</b>", "R", "Applied")])[0]["label"] == "Absage"


def test_last_run_text_comes_from_the_newest_event_row_and_bad_rows_are_ignored():
    events = [{"datum": "2026-09-24", "threads_gesichtet": "3", "zeilen_geaendert": "0", "neue_uids": "0", "unklar": "1"},
              {"datum": "2026-09-25", "threads_gesichtet": "5", "zeilen_geaendert": "2", "neue_uids": "0", "unklar": "0"}]
    assert TV.last_run_text(events) == "2026-09-25 · 5 Threads gesichtet · 2 Zeilen geändert · 0 neue UIDs"
    assert TV.last_run_text([{"datum": "x"}, "y", None]) == "" and TV.last_run_text(None) == "" and TV.last_run_text([]) == ""
    assert TV.last_run_text([{"datum": "2026-09-25", "threads_gesichtet": "viele"}]) == "2026-09-25"


def test_automatically_filed_finds_are_listed_for_a_check():
    rep = {"new": [{"file": "a.pdf", "uid": 216, "company": "Contoso", "role": "AI Governance Officer", "auto": True}, {"file": "b.md", "uid": 217, "company": "X", "role": "Y"}]}
    lines = TV.build_context(find_rows(), None, TODAY, intake=rep)["intake_lines"]
    assert [(l["label"], l["reason"]) for l in lines] == [("Automatisch angelegt", "uid 216 · Contoso · AI Governance Officer: bitte prüfen")]


def test_the_card_shows_changes_with_the_snapshot_time_and_the_last_run(tmp_path):
    import render
    engine = render.TemplateEngine(os.path.join(SYSTEM_DIR, "templates"))
    ctx = TV.build_context(find_rows(), None, TODAY, baseline=[crow("215", "Blanco", "Head", "Applied")], baseline_label="26.09. 00:17",
                           events=[{"datum": "2026-09-25", "threads_gesichtet": "5", "zeilen_geaendert": "2", "neue_uids": "0", "unklar": "0"}])
    html = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="", data_json="{}", footer="", logo_svg="", favicon_uri="", **ctx)
    assert "Seit dem letzten Lauf" in html and "seit 26.09. 00:17" in html and "Letzter Lauf: 2026-09-25 · 5 Threads gesichtet" in html
    empty = TV.build_context(find_rows(), None, TODAY, baseline=[], events=None)
    html2 = engine.render("today.html", title="t", heading="Heute", subtitle="s", nav=[], today=TODAY, theme_css="", core_js="", data_json="{}", footer="", logo_svg="", favicon_uri="", **empty)
    assert "Seit dem letzten Lauf" in html2 and "Keine Änderungen" in html2


def test_render_reads_the_newest_differing_archive_snapshot_and_the_events_file(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Closed,rejected,,2026-09-26,0,0,0,,HH,,,,,n,,\n216,Neu AG,Manager,Executive,Applied,,,2026-09-26,0,0,0,,HH,,,,,n,,\n", encoding="utf-8")
    arch = tmp_path / "archive"
    arch.mkdir()
    (arch / "20260925_pipeline.csv").write_text(COLS + "215,Blanco,Head,Executive,Applied,,,2026-09-24,0,0,0,,HH,,,,,n,,\n", encoding="utf-8")
    (arch / "20260926_pipeline.csv").write_text(data.read_text(encoding="utf-8"), encoding="utf-8")                 # identical to now: skipped, the older differing one counts
    (arch / "20260901_pipeline.csv").write_text("kaputt", encoding="utf-8")
    events = tmp_path / "events.csv"
    events.write_text("datum,fenster_von,fenster_bis,threads_gesichtet,zeilen_geaendert,neue_uids,unklar\n2026-09-25,2026-09-25,2026-09-25,5,2,0,0\n", encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--archive-dir", str(arch), "--events", str(events), "--today", TODAY, "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html = re.sub(r"<script.*?</script>", "", (out / "00_today.html").read_text(encoding="utf-8"), flags=re.S)
    assert "Absage" in html and "Blanco · Head: Applied → Closed (rejected)" in html and "Neu" in html and "Neu AG · Manager (Applied)" in html and "Letzter Lauf: 2026-09-25" in html
    res2 = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                           "--transitions", str(tmp_path / "n.csv"), "--archive-dir", str(tmp_path / "nope"), "--events", str(tmp_path / "nope.csv"), "--today", TODAY,
                           "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res2.returncode == 0, res2.stderr


def test_snapshots_are_ordered_by_file_name_and_broken_ones_are_skipped(tmp_path):
    import time
    arch = tmp_path / "archive"
    arch.mkdir()
    cur = [crow("1", "A", "R", "Closed", "rejected")]
    def snap(name, stage, mtime):
        p = arch / name
        p.write_text("\ufeffuid,company,role,stage,outcome\n1,A,R,%s,\n" % stage, encoding="utf-8")
        os.utime(p, (mtime, mtime))
    snap("20260925_2359_pipeline.csv", "Applied", time.time() - 9000)
    snap("20260920_pipeline.csv", "Watchlist", time.time())                                     # touched last, but older by name
    os.symlink(str(arch / "nowhere.csv"), str(arch / "20260926_pipeline.csv"))                  # dangling link: must not crash
    rows, label = TV.latest_baseline(str(arch), cur)
    assert rows is not None and rows[0]["stage"] == "Applied" and label.startswith("25.09.")


def test_automatic_lines_also_show_for_existing_and_healed_finds():
    rep = {"existing": [{"file": "a.pdf", "uid": 5, "company": "X", "role": "Y", "auto": True}], "healed": [{"file": "b.pdf", "uid": 6, "company": "Z", "role": "W", "auto": True}]}
    lines = TV.build_context(find_rows(), None, TODAY, intake=rep)["intake_lines"]
    assert [l["label"] for l in lines] == ["Automatisch angelegt", "Automatisch angelegt"]


def test_render_writes_alias_copies_of_the_five_pages_without_the_number_prefix(tmp_path):
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "215,Blanco,Head,Executive,Watchlist,,,2026-09-26,0,0,0,,HH,,,,,n,,\n", encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    for orig, alias in (("00_today.html", "today.html"), ("01_cockpit.html", "cockpit.html"), ("02_pipeline_crm.html", "pipeline_crm.html"),
                        ("03_briefings.html", "briefings.html"), ("04_agentur_report.html", "agentur_report.html")):
        assert (out / alias).read_text(encoding="utf-8") == (out / orig).read_text(encoding="utf-8"), alias


def test_the_render_flag_of_the_step_scripts_is_accepted(tmp_path):
    import intel_job, draft_job, coverage
    for mod in (intel_job, draft_job, coverage):
        res = subprocess.run([sys.executable, mod.__file__, "--help"], capture_output=True, text=True)
        assert res.returncode == 0 and "--render" in res.stdout, mod.__name__
