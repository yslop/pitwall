"""pilot_report.py: numbers only. No company, person or file names, whatever the data looks like."""
import csv, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pilot_report as R

SECRET = ("Geheim GmbH", "Müller", "Zukunftsrolle", "Frau Schmidt")
HEADER = ["uid", "company", "role", "lane", "stage", "outcome", "applied", "last_event", "days_idle", "score", "boost", "salary_fit",
          "location", "contacts", "folder_id", "next_action", "due", "note", "ts_confidence", "ts_fit_score"]


def career(tmp_path):
    system = tmp_path / "_system"
    system.mkdir()
    rows = [
        dict(uid="1", company="Geheim GmbH", role="Zukunftsrolle", stage="Interviewing", note="Frau Schmidt Müller", next_action="Anrufen", due="2026-10-08"),
        dict(uid="2", company="Anders AG", role="Lead", stage="Applied"),
        dict(uid="3", company="Alt AG", role="Head", stage="Closed", outcome="rejected"),
    ]
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    voraus = tmp_path / "1 Geheim GmbH" / "Zukunftsrolle" / "20 Vorbereitung"
    voraus.mkdir(parents=True)
    cockpit = voraus / "Cockpit_Geheim_GmbH_Zukunftsrolle_2026-10-07.html"
    briefing = voraus / "Geheim_GmbH_Briefing_2026-10-06_v1.md"
    cockpit.write_text("<p>x</p>", encoding="utf-8")
    briefing.write_text("# Briefing", encoding="utf-8")
    (system / "intel_state.json").write_text(json.dumps({"1": {"docs": {"briefing:": {"latest": "v1", "versions": {"v1": {"result": "pass"}}}}}}), encoding="utf-8")
    ts = datetime.datetime(2026, 10, 6, 12).timestamp()                 # files are "from yesterday" whatever the real clock says
    for p in (system / "pipeline.csv", cockpit, briefing):
        os.utime(p, (ts, ts))
    return str(system), str(tmp_path)


def test_report_has_exactly_the_agreed_fields_and_counts(tmp_path):
    system, base = career(tmp_path)
    rep = R.build_report(system, base, "2026-10-07")
    assert tuple(rep) == R.FIELDS
    assert rep["week"] == "2026-W41"
    assert rep["processes_by_stage"] == {"Interviewing": 1, "Applied": 1}
    assert rep["cockpits_created"] == 1 and rep["lint_pass_rate"] == 1.0 and rep["usage_days"] >= 1


def test_report_contains_no_names_at_all(tmp_path):
    system, base = career(tmp_path)
    text = json.dumps(R.build_report(system, base, "2026-10-07"), ensure_ascii=False)
    assert not any(s in text for s in SECRET) and "Cockpit_" not in text and ".html" not in text


def test_unknown_stage_names_are_counted_as_other_not_echoed(tmp_path):
    system, base = career(tmp_path)
    with open(os.path.join(system, "pipeline.csv"), "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=HEADER).writerow(dict(uid="9", company="X", role="Y", stage="Geheimstufe Müller"))
    rep = R.build_report(system, base, "2026-10-07")
    assert rep["processes_by_stage"].get("Other") == 1 and "Müller" not in json.dumps(rep, ensure_ascii=False)


def test_cost_is_not_claimed_without_a_calibrated_table(tmp_path):
    system, base = career(tmp_path)
    assert R.build_report(system, base, "2026-10-07")["estimated_ai_cost_by_document_type"] == {"calibrated": False}
    rep = R.build_report(system, base, "2026-10-07", cost_table={"cockpit": 0.5, "briefing": 1.0})
    cost = rep["estimated_ai_cost_by_document_type"]
    assert cost["calibrated"] is True and cost["cockpit"] == 0.5 and cost["briefing"] == 1.0


def test_empty_installation_gives_zero_report(tmp_path):
    system = tmp_path / "_system"
    system.mkdir()
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(HEADER)
    rep = R.build_report(str(system), str(tmp_path), "2026-10-07")
    assert rep["processes_by_stage"] == {} and rep["cockpits_created"] == 0 and rep["lint_pass_rate"] is None
