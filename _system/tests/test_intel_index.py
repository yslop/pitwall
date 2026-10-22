"""intel_index.py: which files count as intel, how far it looks, versions, warnings, read-only behaviour."""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import intel_index as I  # noqa: E402

NOW = datetime(2026, 9, 25, 9, 0, 0)


def touch(path, day="2026-09-10", text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    t = datetime.fromisoformat(day + "T12:00:00").timestamp()
    os.utime(path, (t, t))
    return path


def rows(*pairs):
    return [{"uid": u, "stage": s} for u, s in pairs]


# ---- what counts as intel -----------------------------------------------------------------------
def test_classify_kinds_and_case():
    assert I.classify("Nordberatung_Interview_Briefing_CheatSheet_Brandt_2026-09-08.pdf") == "cheat_sheet"
    assert I.classify("Hansehandel_131_Prep_Cheat_Sheet_2026-08-07.md.gdoc") == "cheat_sheet"
    assert I.classify("Nordberatung_Briefing_Brandt.PDF") == "briefing"
    assert I.classify("Nordberatung_Cockpit_Brandt_2026-09-11.pdf") == "cockpit"
    assert I.classify("JD_Intel_Nordberatung_2026-09-22.html") == "jd_intel"
    assert I.classify("Prep_Brief_Nordberatung_2026-09-22.html") == "prep_brief"


def test_classify_rejects_debriefing_and_wrong_extensions():
    assert I.classify("Mail_2026-07-09_KEYFACTS_DebriefingInvite.pdf") is None
    assert I.classify("Cheatsheet_notes.docx") is None
    assert I.classify("cockpit.png") is None
    assert I.classify("Lebenslauf.pdf") is None


def test_version_key_ignores_dates_and_version_tags():
    keys = {I.version_key(n) for n in ("Hansehandel_Interview_Briefing_CheatSheet_20260826.pdf",
                                       "Hansehandel_Interview_Briefing_CheatSheet_2026-08-26.pdf",
                                       "Hansehandel_Interview_Briefing_CheatSheet_v2_2026-08-26.pdf")}
    assert len(keys) == 1
    assert I.version_key("Nordberatung_Briefing_CheatSheet_LorenzJohn_2026-09-11.pdf") != I.version_key("Nordberatung_Interview_Briefing_CheatSheet_Brandt_2026-09-08.pdf")


# ---- how far it looks ---------------------------------------------------------------------------
def make_tree(tmp_path):
    root = str(tmp_path)
    touch(root + "/133 Nordberatung (active)/Top_Cheatsheet_Employer.pdf")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/Briefing_role_level.pdf")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/20 Vorbereitung/Nordberatung_Cockpit_2026-09-11.pdf")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/30 Verlauf/Prep_Brief_x.html")
    touch(root + "/133 Nordberatung (active)/20 Vorbereitung/Employer_Cheat_Sheet.md")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/40 Sonstiges/Cheatsheet_ignored.pdf")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/20 Vorbereitung/deeper/Cheatsheet_too_deep.pdf")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/.hidden_cheatsheet.pdf")
    touch(root + "/133 Nordberatung (active)/Data & AI Rolle/Lebenslauf.pdf")
    return root


def test_scan_finds_the_bounded_places_only(tmp_path):
    root = make_tree(tmp_path)
    names = sorted(i["name"] for i in I.scan_folder(root, "133 Nordberatung (active)"))
    assert names == ["Briefing_role_level.pdf", "Employer_Cheat_Sheet.md", "Nordberatung_Cockpit_2026-09-11.pdf",
                     "Prep_Brief_x.html", "Top_Cheatsheet_Employer.pdf"]


def test_scan_records_where_and_relative_forward_slash_paths(tmp_path):
    root = make_tree(tmp_path)
    by = {i["name"]: i for i in I.scan_folder(root, "133 Nordberatung (active)")}
    assert by["Top_Cheatsheet_Employer.pdf"]["where"] == ""
    assert by["Employer_Cheat_Sheet.md"]["where"] == ""                      # employer-level 20 folder is not a role
    assert by["Nordberatung_Cockpit_2026-09-11.pdf"]["where"] == "Data & AI Rolle"
    assert by["Nordberatung_Cockpit_2026-09-11.pdf"]["path"] == "133 Nordberatung (active)/Data & AI Rolle/20 Vorbereitung/Nordberatung_Cockpit_2026-09-11.pdf"
    assert by["Nordberatung_Cockpit_2026-09-11.pdf"]["modified"] == "2026-09-10"


def test_umlauts_spaces_and_special_characters_in_names(tmp_path):
    root = str(tmp_path)
    touch(root + "/21 Größe & Söhne/Rolle Ä/20 Vorbereitung/Cheat Sheet – Überblick #1.pdf")
    items = I.scan_folder(root, "21 Größe & Söhne")
    assert [i["name"] for i in items] == ["Cheat Sheet – Überblick #1.pdf"]


# ---- versions -----------------------------------------------------------------------------------
def test_only_the_newest_copy_is_current(tmp_path):
    root = str(tmp_path)
    for name, day in (("X_CheatSheet_20260911.pdf", "2026-09-11"), ("X_CheatSheet_2026-09-11.pdf", "2026-09-11"),
                      ("X_CheatSheet_2026-09-01.pdf", "2026-09-01"), ("Y_Cockpit.pdf", "2026-09-02")):
        touch(root + "/9 Acme/" + name, day)
    items = I.mark_superseded(I.scan_folder(root, "9 Acme"))
    current = [i["name"] for i in items if not i["superseded"]]
    assert len(current) == 2 and "Y_Cockpit.pdf" in current
    assert [i["superseded"] for i in items] == [False, False, True, True]        # current first, older after


# ---- build --------------------------------------------------------------------------------------
def test_build_only_live_stages_and_exact_uid_prefix(tmp_path):
    root = str(tmp_path)
    touch(root + "/05 ticketwerk (inactive)/Cheatsheet.pdf")
    touch(root + "/55 KEYFACTS (active)/Cheatsheet_B.pdf")
    touch(root + "/133 Nordberatung (active)/Cheatsheet_M.pdf")
    idx = I.build(root, rows(("5", "Applied"), ("55", "Closed"), ("133", "Final"), ("77", "Watchlist")), NOW)
    assert sorted(idx["uids"]) == ["133", "5"]
    assert [i["name"] for i in idx["uids"]["5"]["items"]] == ["Cheatsheet.pdf"]      # uid 5 does not pick up "55 KEYFACTS"
    assert idx["uids"]["133"]["folders"] == ["133 Nordberatung (active)"]


def test_missing_and_duplicate_folders_produce_warnings(tmp_path):
    root = str(tmp_path)
    touch(root + "/118 Baerwerk/Cheatsheet.pdf")
    touch(root + "/118 Baerwerk (1)/Briefing.pdf")
    idx = I.build(root, rows(("118", "Applied"), ("999", "Applied")), NOW)
    assert "Mehrere Ordner" in idx["uids"]["118"]["warnings"][0]
    assert len(idx["uids"]["118"]["items"]) == 2                                   # files from both are listed
    assert "Kein Ordner" in idx["uids"]["999"]["warnings"][0] and idx["uids"]["999"]["items"] == []


def test_garbage_uid_cells_are_skipped(tmp_path):
    idx = I.build(str(tmp_path), [{"uid": "", "stage": "Applied"}, {"uid": "abc", "stage": "Applied"}, {"stage": "Applied"}], NOW)
    assert idx["uids"] == {}


def test_gdoc_pointer_becomes_a_docs_link_and_garbage_gdoc_does_not_crash(tmp_path):
    root = str(tmp_path)
    touch(root + "/131 Hansehandel/Prep_Cheat_Sheet.md.gdoc", text=json.dumps({"doc_id": "1ArfeP", "email": "a@b.c"}))
    touch(root + "/131 Hansehandel/Cockpit_broken.gdoc", text="not json")
    by = {i["name"]: i for i in I.scan_folder(root, "131 Hansehandel")}
    assert by["Prep_Cheat_Sheet.md.gdoc"]["link"] == "https://docs.google.com/document/d/1ArfeP/edit"
    assert by["Cockpit_broken.gdoc"]["link"] is None


# ---- CLI ----------------------------------------------------------------------------------------
def test_main_writes_index_leaves_no_temp_file_and_never_touches_the_folders(tmp_path):
    root = tmp_path / "root"
    touch(str(root / "133 Nordberatung (active)/Cheatsheet.pdf"))
    data = tmp_path / "pipeline.csv"
    data.write_text("uid,stage\n133,Final\n", encoding="utf-8")
    before = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs) + [str(os.stat(root).st_mtime)]
    out = tmp_path / "intel_index.json"
    assert I.main(["--data", str(data), "--root", str(root), "--out", str(out)]) == 0
    after = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs) + [str(os.stat(root).st_mtime)]
    assert before == after and not os.path.exists(str(out) + ".tmp")
    assert json.loads(out.read_text(encoding="utf-8"))["uids"]["133"]["items"][0]["name"] == "Cheatsheet.pdf"


def test_main_returns_1_when_pipeline_is_missing(tmp_path):
    assert I.main(["--data", str(tmp_path / "nope.csv"), "--root", str(tmp_path), "--out", str(tmp_path / "o.json")]) == 1


def test_unreadable_folder_is_skipped_without_crashing(tmp_path):
    root = str(tmp_path)
    touch(root + "/133 Nordberatung (active)/Cheatsheet_ok.pdf")
    locked = root + "/133 Nordberatung (active)/Rolle/20 Vorbereitung"
    os.makedirs(locked)
    os.chmod(root + "/133 Nordberatung (active)/Rolle", 0o000)
    try:
        names = [i["name"] for i in I.scan_folder(root, "133 Nordberatung (active)")]
    finally:
        os.chmod(root + "/133 Nordberatung (active)/Rolle", 0o755)
    assert names == ["Cheatsheet_ok.pdf"]


# ---- final review, fix pass ---------------------------------------------------------------------
def test_same_day_versions_the_higher_version_is_current(tmp_path):
    root = str(tmp_path)
    for name in ("Cheat Sheet.pdf", "Cheat Sheet v2.pdf"):
        touch(root + "/9 Acme/" + name, "2026-09-10")
    for name in ("X_Cockpit_v9.pdf", "X_Cockpit_v10.pdf"):
        touch(root + "/9 Acme/" + name, "2026-09-10")
    items = I.mark_superseded(I.scan_folder(root, "9 Acme"))
    current = sorted(i["name"] for i in items if not i["superseded"])
    assert current == ["Cheat Sheet v2.pdf", "X_Cockpit_v10.pdf"]


def test_same_file_name_in_different_folders_stays_current_in_each(tmp_path):
    root = str(tmp_path)
    touch(root + "/55 KEYFACTS/Head of IT/Cheat Sheet.pdf", "2026-09-01")
    touch(root + "/55 KEYFACTS/CIO/Cheat Sheet.pdf", "2026-09-10")
    touch(root + "/118 Baerwerk/Briefing.pdf", "2026-09-01")
    touch(root + "/118 Baerwerk (1)/Briefing.pdf", "2026-09-10")
    a = I.mark_superseded(I.scan_folder(root, "55 KEYFACTS"))
    assert [i["superseded"] for i in a] == [False, False]
    idx = I.build(root, rows(("118", "Applied")), NOW)
    assert [i["superseded"] for i in idx["uids"]["118"]["items"]] == [False, False]


def test_rejected_and_inactive_role_folders_are_not_scanned(tmp_path):
    root = str(tmp_path)
    touch(root + "/62 Technikdienst/Employer_Cheatsheet.pdf")
    touch(root + "/62 Technikdienst/PMO Governance (rejected)/Cheatsheet_old.pdf")
    touch(root + "/62 Technikdienst/Data Lead (inactive)/20 Vorbereitung/Briefing_old.pdf")
    touch(root + "/62 Technikdienst/AI Lead (active)/Cheatsheet_live.pdf")
    touch(root + "/62 Technikdienst/AI Lead/Cockpit_live.pdf")
    names = sorted(i["name"] for i in I.scan_folder(root, "62 Technikdienst"))
    assert names == ["Cheatsheet_live.pdf", "Cockpit_live.pdf", "Employer_Cheatsheet.pdf"]


def test_closed_role_folder_is_scanned_when_it_is_the_only_one(tmp_path):
    # Kekswerk uid 41: re-opened process still lives in the old '(rejected)' role folder
    root = str(tmp_path)
    touch(root + "/41 Kekswerk (rejected)/Lead Data & AI (rejected)/20 Vorbereitung/Briefing_2026-10-07_v2.md")
    touch(root + "/41 Kekswerk (rejected)/Head of Global (rejected)/20 Vorbereitung/Briefing_old.md")
    names = sorted(i["name"] for i in I.scan_folder(root, "41 Kekswerk (rejected)"))
    assert names == ["Briefing_2026-10-07_v2.md", "Briefing_old.md"]
    touch(root + "/41 Kekswerk (rejected)/New Role/Cheatsheet.pdf")                 # an open role folder wins again
    names = sorted(i["name"] for i in I.scan_folder(root, "41 Kekswerk (rejected)"))
    assert names == ["Cheatsheet.pdf"]


def test_channel_uids_are_excluded_from_intel_index(tmp_path):
    root = str(tmp_path)
    touch(root + "/133 Nordberatung (active)/Cheatsheet.pdf")
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps({"channels": {"184": {"type": "headhunter"}}}), encoding="utf-8")
    loaded_channels = I.load_channels(str(channels_file))
    assert loaded_channels == {184}
    idx = I.build(root, rows(("133", "Applied"), ("184", "Applied")), NOW, channels=loaded_channels)
    assert "133" in idx["uids"]
    assert "184" not in idx["uids"]
