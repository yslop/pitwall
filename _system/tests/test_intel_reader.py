"""intel_reader: which documents a reading pane offers per live position, and their (safe) content."""
import os
import sys

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM_DIR)

import intel_reader


def item(name, kind, path, modified="2026-10-01", superseded=False, link=None, where="Rolle"):
    return {"name": name, "kind": kind, "path": path, "where": where, "modified": modified, "link": link, "superseded": superseded}


def idx(uid, items):
    return {"generated": "2026-10-02T08:00:00", "uids": {str(uid): {"folders": ["x"], "warnings": [], "items": items}}}


def write(root, rel, text):
    p = os.path.join(str(root), rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(text)


def rows(*pairs):
    return [{"uid": u, "stage": s, "company": "C", "role": "R"} for u, s in pairs]


def test_markdown_is_preferred_over_the_html_of_the_same_file_and_is_escaped(tmp_path):
    write(tmp_path, "220 m/R/20 V/m_Briefing_v1.md", "# Briefing\n\n<script>alert(1)</script> **wichtig**\n")
    write(tmp_path, "220 m/R/20 V/m_Briefing_v1.html", "<html>x</html>")
    index = idx(220, [item("m_Briefing_v1.html", "briefing", "220 m/R/20 V/m_Briefing_v1.html"),
                      item("m_Briefing_v1.md", "briefing", "220 m/R/20 V/m_Briefing_v1.md")])
    out = intel_reader.build(index, rows(("220", "Interviewing")), str(tmp_path))
    docs = out["220"]["docs"]
    assert len(docs) == 1 and docs[0]["mode"] == "md" and docs[0]["kind"] == "briefing"
    assert "<h1>Briefing</h1>" in docs[0]["html"] and "<script" not in docs[0]["html"].lower() and "<strong>wichtig</strong>" in docs[0]["html"]


def test_html_only_files_become_restyled_pages_and_pdfs_become_links(tmp_path):
    write(tmp_path, "1 a/20 V/JD_Intel_a.html", "<html><head></head><body>jd</body></html>")
    write(tmp_path, "1 a/20 V/Cheat.pdf", "%PDF")
    index = idx(1, [item("JD_Intel_a.html", "jd_intel", "1 a/20 V/JD_Intel_a.html"), item("Cheat.pdf", "cheat_sheet", "1 a/20 V/Cheat.pdf")])
    docs = intel_reader.build(index, rows(("1", "Screening")), str(tmp_path))["1"]["docs"]
    by_kind = {d["kind"]: d for d in docs}
    jd = by_kind["jd_intel"]
    assert jd["mode"] == "page" and jd["path"] == "1 a/20 V/JD_Intel_a.html" and jd["html"].startswith("<html><head></head><body>jd")
    assert "XLRTE Brand" in jd["html"] and jd["html"].index("jd") < jd["html"].index("XLRTE Brand")        # the CI layer comes after the old styles
    assert "#E4572E" in jd["html"] and jd["html"].rstrip().endswith("</html>")
    assert by_kind["cheat_sheet"]["mode"] == "link"


def test_a_very_large_html_file_is_framed_by_path_instead_of_embedded(tmp_path):
    write(tmp_path, "1 a/JD_Intel_big.html", "<html><body>" + "x" * 300000 + "</body></html>")
    docs = intel_reader.build(idx(1, [item("JD_Intel_big.html", "jd_intel", "1 a/JD_Intel_big.html")]), rows(("1", "Screening")), str(tmp_path))["1"]["docs"]
    assert docs[0]["mode"] == "frame" and docs[0]["html"] is None


def test_the_document_of_the_stage_comes_first_and_is_the_default(tmp_path):
    for rel in ("1 a/c.md", "1 a/b.md", "1 a/s.md"):
        write(tmp_path, rel, "x")
    index = idx(1, [item("c.md", "cheat_sheet", "1 a/c.md"), item("b.md", "briefing", "1 a/b.md"), item("s.md", "strategy", "1 a/s.md")])
    for stage, first in (("Applied", "cheat_sheet"), ("Screening", "cheat_sheet"), ("Interviewing", "briefing"), ("Final", "strategy")):
        entry = intel_reader.build(index, rows(("1", stage)), str(tmp_path))["1"]
        assert entry["docs"][0]["kind"] == first and entry["primary"] == 0, stage


def test_without_the_stage_document_the_default_is_still_the_first_available(tmp_path):
    write(tmp_path, "1 a/c.md", "x")
    entry = intel_reader.build(idx(1, [item("c.md", "cheat_sheet", "1 a/c.md")]), rows(("1", "Final")), str(tmp_path))["1"]
    assert entry["docs"][0]["kind"] == "cheat_sheet" and entry["primary"] == 0


def test_superseded_files_closed_stages_and_unknown_uids_are_left_out(tmp_path):
    write(tmp_path, "1 a/old.md", "old")
    index = idx(1, [item("old.md", "briefing", "1 a/old.md", superseded=True)])
    assert intel_reader.build(index, rows(("1", "Interviewing")), str(tmp_path)) == {}
    write(tmp_path, "2 b/n.md", "n")
    index2 = idx(2, [item("n.md", "briefing", "2 b/n.md")])
    assert intel_reader.build(index2, rows(("2", "Closed"), ("2", "Watchlist")), str(tmp_path)) == {}
    assert intel_reader.build(index2, rows(("9", "Final")), str(tmp_path)) == {}


def test_uids_with_leading_zeros_find_their_entry(tmp_path):
    write(tmp_path, "9 z/b.md", "x")
    out = intel_reader.build(idx(9, [item("b.md", "briefing", "9 z/b.md")]), rows(("09", "Interviewing")), str(tmp_path))
    assert list(out) == ["9"]


def test_paths_outside_the_career_folder_are_never_read(tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("TOPSECRET", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    index = idx(1, [item("x.md", "briefing", "../secret.md"), item("y.md", "cheat_sheet", str(secret))])
    out = intel_reader.build(index, rows(("1", "Interviewing")), str(root))
    assert "TOPSECRET" not in repr(out)
    assert all(d["mode"] == "link" and d["html"] is None for d in out["1"]["docs"])


def test_a_missing_file_and_an_oversized_file_degrade_safely(tmp_path):
    write(tmp_path, "1 a/big.md", "wort " * 40000)
    index = idx(1, [item("gone.md", "cheat_sheet", "1 a/gone.md"), item("big.md", "briefing", "1 a/big.md")])
    docs = {d["kind"]: d for d in intel_reader.build(index, rows(("1", "Interviewing")), str(tmp_path))["1"]["docs"]}
    assert docs["cheat_sheet"]["mode"] == "link" and docs["cheat_sheet"]["html"] is None
    assert docs["briefing"]["mode"] == "md" and docs["briefing"]["truncated"] is True and "gekürzt" in docs["briefing"]["html"]


def test_empty_or_broken_index_gives_an_empty_result(tmp_path):
    for bad in (None, {}, {"uids": None}, {"uids": {"1": None}}, {"uids": {"1": {"items": None}}}):
        assert intel_reader.build(bad, rows(("1", "Final")), str(tmp_path)) == {}


def _render(tmp_path, intel_obj, csv_rows, root):
    import json
    import re
    import subprocess
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,contacts,folder_id,next_action,due,note\n" + csv_rows, encoding="utf-8")
    intel = tmp_path / "intel_index.json"
    intel.write_text(json.dumps(intel_obj), encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, os.path.join(SYSTEM_DIR, "render.py"), "--data", str(data), "--prep", str(tmp_path / "n.json"),
                          "--folders", str(tmp_path / "n.tsv"), "--transitions", str(tmp_path / "n.csv"), "--intel", str(intel),
                          "--reader-root", str(root), "--today", "2026-10-02", "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html = (out / "03_briefings.html").read_text(encoding="utf-8")
    return json.loads(re.search(r'<script type="application/json" id="DATA">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))


def test_render_embeds_the_reading_pane_data_and_survives_script_breakers(tmp_path):
    root = tmp_path / "career"
    write(root, "133 Nordberatung/R/20 V/Briefing_v1.md", "# Titel\n\n</script><b>x</b>\n")
    index = idx(133, [item("Briefing_v1.md", "briefing", "133 Nordberatung/R/20 V/Briefing_v1.md")])
    d = _render(tmp_path, index, "133,Nordberatung,Mgr,Executive,Interviewing,,2026-07-01,2026-09-24,1,80,0,high,HH,,f1,x,2026-10-01,n\n", root)
    doc = d["reader"]["133"]["docs"][0]
    assert doc["mode"] == "md" and "<h1>Titel</h1>" in doc["html"] and "<b>" not in doc["html"]


def test_render_without_documents_gives_an_empty_reader(tmp_path):
    d = _render(tmp_path, {"generated": "x", "uids": {}}, "1,A,R,L,Final,,,,,,,,,,,,,\n", tmp_path / "career")
    assert d["reader"] == {}


def test_a_markdown_marked_superseded_by_its_own_html_is_still_the_preferred_source(tmp_path):
    # intel_index.py flags the .md as 'superseded' when the same version exists as .html; for reading, the markdown is the better source
    write(tmp_path, "220 m/R/m_Briefing_v2.md", "# Fassung 2\n")
    write(tmp_path, "220 m/R/m_Briefing_v2.html", "<html>x</html>")
    write(tmp_path, "220 m/R/m_Briefing_v1.md", "# Fassung 1\n")
    index = idx(220, [item("m_Briefing_v2.html", "briefing", "220 m/R/m_Briefing_v2.html"),
                      item("m_Briefing_v2.md", "briefing", "220 m/R/m_Briefing_v2.md", superseded=True),
                      item("m_Briefing_v1.md", "briefing", "220 m/R/m_Briefing_v1.md", superseded=True)])
    docs = intel_reader.build(index, rows(("220", "Interviewing")), str(tmp_path))["220"]["docs"]
    assert len(docs) == 1 and docs[0]["mode"] == "md" and "Fassung 2" in docs[0]["html"]          # v1 is an older version: not offered


def test_only_the_briefings_page_carries_the_reading_pane_data(tmp_path):
    import json
    import re
    import subprocess
    root = tmp_path / "career"
    write(root, "133 Nordberatung/R/20 V/Briefing_v1.md", "# Titel\n")
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,contacts,folder_id,next_action,due,note\n"
                    "133,Nordberatung,Mgr,Executive,Interviewing,,2026-07-01,2026-09-24,1,80,0,high,HH,,f1,x,2026-10-01,n\n", encoding="utf-8")
    intel = tmp_path / "intel_index.json"
    intel.write_text(json.dumps(idx(133, [item("Briefing_v1.md", "briefing", "133 Nordberatung/R/20 V/Briefing_v1.md")])), encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, os.path.join(SYSTEM_DIR, "render.py"), "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"),
                          "--transitions", str(tmp_path / "n.csv"), "--intel", str(intel), "--reader-root", str(root), "--today", "2026-10-02", "--out", str(out), "--no-pdf"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    def data_of(name):
        h = (out / name).read_text(encoding="utf-8")
        return json.loads(re.search(r'<script type="application/json" id="DATA">(.*?)</script>', h, re.S).group(1))
    assert "133" in data_of("03_briefings.html")["reader"]
    for page in ("00_today.html", "01_cockpit.html", "02_pipeline_crm.html", "05_expert.html"):
        assert "reader" not in data_of(page), page


def test_a_generated_markdown_document_carries_its_quality_and_other_files_do_not(tmp_path):
    import test_intel_docs as T
    write(tmp_path, "220 m/R/20 V/pharmo_Briefing_2026-10-01_v1.md", T.BRIEFING)
    write(tmp_path, "220 m/R/20 V/eigenes_Dokument.md", "# Eigenes\n")
    write(tmp_path, "220 m/R/20 V/JD_Intel_m.html", "<html></html>")
    index = idx(220, [item("pharmo_Briefing_2026-10-01_v1.md", "briefing", "220 m/R/20 V/pharmo_Briefing_2026-10-01_v1.md"),
                      item("eigenes_Dokument.md", "cheat_sheet", "220 m/R/20 V/eigenes_Dokument.md"),
                      item("JD_Intel_m.html", "jd_intel", "220 m/R/20 V/JD_Intel_m.html")])
    docs = {d["kind"]: d for d in intel_reader.build(index, rows(("220", "Interviewing")), str(tmp_path), today="2026-10-02")["220"]["docs"]}
    q = docs["briefing"]["quality"]
    assert q["lint"] == "pass" and q["facts"] == 4 and q["inferences"] == 6 and q["sources"] == 3 and q["oldest_source_age"] == 12
    assert docs["cheat_sheet"]["quality"] is None and docs["jd_intel"]["quality"] is None
