"""kit_import.py: the customer's history from a CSV, with a preview first; append only, never overwrite."""
import csv, os, sys
SYSTEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_import as I
import kit_setup
from test_kit_setup import engine_copy

TODAY = "2026-10-07"


def fresh(tmp_path):
    system = str(tmp_path / "_system")
    engine_copy(system)
    kit_setup.install(system, "Erika Muster")
    return system


def write_csv(tmp_path, text, name="verlauf.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8-sig")
    return str(p)


def pipeline(system):
    with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


GERMAN = """Firma;Position;Status;Beworben am;Letzter Kontakt;Ort;Notiz
Müller & Söhne GmbH;Leiter IT;Zweites Vorstellungsgespräch;03.09.2026;28.09.2026;Hamburg;Gespräch mit dem Vorstand
Beispiel AG;Head of Data;Absage erhalten;01.08.2026;15.08.2026;Berlin;
Neue Firma SE;Data Lead;beworben;2026-10-01;;;
"""


def test_stage_mapping_covers_german_and_english_status_words():
    cases = {"beworben": ("Applied", ""), "Applied": ("Applied", ""), "Telefoninterview mit Recruiter": ("Screening", ""),
             "Zweites Vorstellungsgespräch": ("Interviewing", ""), "interview scheduled": ("Interviewing", ""), "Angebot erhalten": ("Final", ""),
             "Absage erhalten": ("Closed", "rejected"), "rejected": ("Closed", "rejected"), "selbst zurückgezogen": ("Closed", "withdrawn"),
             "interessant, später": ("Watchlist", "")}
    for text, expected in cases.items():
        assert I.map_status(text)[:2] == expected, text
    assert I.map_status("???")[0] == "Applied" and I.map_status("???")[2] is True      # unknown status: Applied, flagged


def test_dates_are_normalised_and_bad_dates_become_empty():
    assert I.parse_date("03.09.2026") == "2026-09-03" and I.parse_date("2026-09-03") == "2026-09-03" and I.parse_date("3/9/2026") == "2026-09-03"
    assert I.parse_date("") == "" and I.parse_date("gestern") == ""


def test_preview_reads_german_semicolon_files_and_writes_nothing(tmp_path):
    system = fresh(tmp_path)
    before = open(os.path.join(system, "pipeline.csv"), encoding="utf-8").read()
    plan = I.plan(write_csv(tmp_path, GERMAN), system, TODAY)
    assert [r["company"] for r in plan["rows"]] == ["Müller & Söhne GmbH", "Beispiel AG", "Neue Firma SE"]
    assert [r["stage"] for r in plan["rows"]] == ["Interviewing", "Closed", "Applied"] and plan["rows"][1]["outcome"] == "rejected"
    assert plan["rows"][0]["applied"] == "2026-09-03" and plan["rows"][0]["last_event"] == "2026-09-28" and plan["rows"][2]["last_event"] == "2026-10-01"
    assert [r["uid"] for r in plan["rows"]] == ["1", "2", "3"]
    assert open(os.path.join(system, "pipeline.csv"), encoding="utf-8").read() == before


def test_apply_appends_creates_folders_and_never_touches_existing_rows(tmp_path):
    system = fresh(tmp_path)
    with open(os.path.join(system, "pipeline.csv"), "a", encoding="utf-8") as f:
        f.write("5,Alt AG,Lead,,Applied,,2026-01-01,2026-01-02,,,,,,,,,,meine Notiz,,\n")
    res = I.apply(write_csv(tmp_path, GERMAN), system, TODAY)
    rows = pipeline(system)
    assert [r["uid"] for r in rows] == ["5", "6", "7", "8"] and rows[0]["note"] == "meine Notiz"
    folder = tmp_path / "6 Müller & Söhne GmbH" / "Leiter IT"
    assert all(os.path.isdir(folder / sub) for sub in ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf")) and res["added"] == 3


def test_second_import_of_the_same_file_adds_nothing(tmp_path):
    system = fresh(tmp_path)
    path = write_csv(tmp_path, GERMAN)
    I.apply(path, system, TODAY)
    again = I.apply(path, system, TODAY)
    assert again["added"] == 0 and len(again["skipped"]) == 3 and len(pipeline(system)) == 3


def test_rows_without_company_or_role_are_skipped_with_a_warning(tmp_path):
    system = fresh(tmp_path)
    plan = I.plan(write_csv(tmp_path, "company,role,status\n,Lead,applied\nAcme,,applied\nOk AG,Head,applied\n"), system, TODAY)
    assert [r["company"] for r in plan["rows"]] == ["Ok AG"] and len(plan["warnings"]) == 2


def test_missing_required_columns_are_refused_clearly(tmp_path):
    system = fresh(tmp_path)
    try:
        I.plan(write_csv(tmp_path, "a,b\n1,2\n"), system, TODAY)
        raise AssertionError("expected ImportError_")
    except I.ImportError_ as e:
        assert "company" in str(e) and "role" in str(e)


def test_unsafe_names_become_safe_folder_names(tmp_path):
    system = fresh(tmp_path)
    I.apply(write_csv(tmp_path, 'company,role,status\n"A/B: Firma",Head / Data?,applied\n'), system, TODAY)
    created = [n for n in os.listdir(tmp_path) if n.startswith("1 ")]
    assert created and "/" not in created[0] and ":" not in created[0]


def test_demo_rows_do_not_shift_the_numbering(tmp_path):
    import kit_demo
    system = fresh(tmp_path)
    kit_demo.add(system, TODAY)
    I.apply(write_csv(tmp_path, GERMAN), system, TODAY)
    assert [r["uid"] for r in pipeline(system)][2:] == ["1", "2", "3"]


def test_the_shipped_example_csv_imports_cleanly(tmp_path):
    system = fresh(tmp_path)
    plan = I.plan(os.path.join(SYSTEM, "kit_examples", "history_import.example.csv"), system, TODAY)
    assert [r["stage"] for r in plan["rows"]] == ["Interviewing", "Closed", "Applied"] and plan["warnings"] == [] and plan["skipped"] == []
