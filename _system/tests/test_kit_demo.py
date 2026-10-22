"""kit_demo.py: two clearly fictional processes with folders, documents, rendered prep pages; removable without touching customer files."""
import csv, json, os, shutil, sys
SYSTEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_lint
import kit_demo as D
import kit_setup
from test_kit_setup import engine_copy

TODAY = "2026-10-07"
TERMS = ("Testvorname", "Testnachname", "Etikettenwerk")


def fresh(tmp_path):
    system = str(tmp_path / "_system")
    engine_copy(system)
    kit_setup.install(system, "Erika Muster")
    return system


def rows(system):
    with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_add_creates_two_demo_rows_folders_documents_and_rendered_prep_pages(tmp_path):
    system = fresh(tmp_path)
    res = D.add(system, TODAY)
    assert [r["uid"] for r in rows(system)] == ["9001", "9002"] and all(r["note"].startswith("DEMO") for r in rows(system))
    assert {r["stage"] for r in rows(system)} == {"Interviewing", "Screening"}
    f1 = tmp_path / "9001 Beispiel Maschinenbau AG (Demo)" / "Head of Data" / "20 Vorbereitung"
    names = os.listdir(f1)
    assert any(n.startswith("Cockpit_") for n in names) and any(n.startswith("Prep_Brief_") for n in names) and any("Briefing" in n and n.endswith(".md") for n in names)
    assert os.path.isdir(f1.parent / "10 Bewerbung") and os.path.isdir(f1.parent / "30 Verlauf")
    f2 = tmp_path / "9002 Beispiel Versicherung SE (Demo)" / "Director IT Strategy" / "20 Vorbereitung"
    assert any("CheatSheet" in n for n in os.listdir(f2))
    assert res["created"] and not res["kept"]


def test_demo_documents_pass_the_lint_without_findings(tmp_path):
    system = fresh(tmp_path)
    D.add(system, TODAY)
    for pattern, doc in (("Briefing", "briefing"), ("CheatSheet", "cheat_sheet")):
        path = [os.path.join(dp, n) for dp, _, ns in os.walk(tmp_path) for n in ns if pattern in n and n.endswith(".md")][0]
        text = open(path, encoding="utf-8").read()
        assert intel_lint.lint_text(os.path.basename(path), text, doc, 1, TODAY) == [], path


def test_demo_content_is_marked_fictional_and_has_nothing_of_the_owner(tmp_path):
    system = fresh(tmp_path)
    D.add(system, TODAY)
    for dp, _, ns in os.walk(tmp_path):
        for n in ns:
            if n.endswith((".md", ".json", ".html")) and "(Demo)" in dp:
                text = open(os.path.join(dp, n), encoding="utf-8").read()
                assert not any(t in text for t in TERMS), n
                if n.endswith(".md"):
                    assert "DEMO" in text, n


def test_add_twice_keeps_everything(tmp_path):
    system = fresh(tmp_path)
    D.add(system, TODAY)
    again = D.add(system, TODAY)
    assert len(rows(system)) == 2 and again["created"] == [] and again["kept"]


def test_archive_takes_only_what_the_demo_created(tmp_path):
    system = fresh(tmp_path)
    D.add(system, TODAY)
    mine = tmp_path / "9001 Beispiel Maschinenbau AG (Demo)" / "Head of Data" / "30 Verlauf" / "meine_notiz.txt"
    mine.write_text("eigene Datei", encoding="utf-8")
    with open(os.path.join(system, "pipeline.csv"), "a", encoding="utf-8") as f:
        f.write("7,Echte AG,Lead,,Applied,,,,,,,,,,,,,,,\n")
    res = D.archive(system)
    assert [r["uid"] for r in rows(system)] == ["7"]
    assert mine.exists() and res["kept"] and res["archived"]
    assert not (tmp_path / "9002 Beispiel Versicherung SE (Demo)").exists()
    archived = [os.path.join(dp, n) for dp, _, ns in os.walk(tmp_path / "_Archiv") for n in ns]
    assert any(n.endswith("Briefing_2026-10-07_v1.md") for n in archived) and any("Cheat" in n for n in archived)
    assert not any(n.endswith("meine_notiz.txt") for n in archived)
    again = D.archive(system)
    assert again["archived"] == [] and [r["uid"] for r in rows(system)] == ["7"]


def test_demo_rows_do_not_count_in_the_report_or_the_queue(tmp_path):
    import pilot_report, intel_queue, warranty
    system = fresh(tmp_path)
    D.add(system, TODAY)
    rep = pilot_report.build_report(system, str(tmp_path), TODAY)
    assert rep["processes_by_stage"] == {} and rep["cockpits_created"] == 0 and rep["queue_open"] == 0
    positions = warranty.snapshot(system, str(tmp_path), rows(system), TODAY)
    assert intel_queue.build_queue(positions, TODAY) == []


def test_health_checks_stay_ok_with_the_demo_data(tmp_path):
    import warranty
    system = fresh(tmp_path)
    D.add(system, TODAY)
    positions = warranty.snapshot(system, str(tmp_path), rows(system), TODAY)
    assert len(positions) == 2
    for rec in warranty.checks(positions, TODAY):
        assert rec["status"] == "OK", (rec["id"], rec["reason"])


def test_install_with_demo_renders_pages_that_show_the_demo_processes(tmp_path):
    system = str(tmp_path / "_system")
    engine_copy(system)
    kit_setup.install(system, "Erika Muster", demo=True, today=TODAY)
    assert kit_setup.render(system, TODAY) == 0
    page = (tmp_path / "01_cockpit.html").read_text(encoding="utf-8")
    assert "Beispiel Maschinenbau AG" in page
