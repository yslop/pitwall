"""warranty.py: does the intel process hold? A stage document exists, is not older than the newest input, orders do not rot,
inputs in the landing zone ('30 Verlauf') are acknowledged. Thresholds: Final/Interviewing 1 day, Screening 3 days, deadline within 3 days."""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warranty as W

TODAY = "2026-10-02"


def pos(uid="1", company="Acme", stage="Interviewing", due=None, docs=(), inputs=(), unacked=(), orders=()):
    return {"uid": uid, "company": company, "stage": stage, "due": due, "folder": True,
            "docs": list(docs), "inputs": list(inputs), "unacked": list(unacked), "orders": list(orders)}


def doc(kind="briefing", version=1, date="2026-10-01"):
    return {"kind": kind, "version": version, "date": date}


def order(doc_kind="briefing", date="2026-10-02", version=1, after=False):
    return {"doc": doc_kind, "date": date, "version": version, "after": after}


def inp(name="Mail.pdf", date="2026-10-02"):
    return {"name": name, "date": date}


def status(rec):
    return rec["status"]


# ---- shape ---------------------------------------------------------------------------------------------------------
def test_every_check_has_the_health_record_shape_in_the_warranty_group():
    for rec in W.checks([pos(docs=[doc()])], TODAY):
        assert set(rec) == {"id", "group", "name", "status", "reason", "target"} and rec["group"] == "warranty" and rec["status"] in ("OK", "Watch", "Act")
    assert [r["id"] for r in W.checks([], TODAY)] == ["intel_stage_doc", "intel_fresh", "intel_orders", "intel_inputs", "intel_quality", "intel_evidence", "intel_prep"]


# ---- stage document -------------------------------------------------------------------------------------------------
def test_a_present_stage_document_or_a_deeper_one_is_ok():
    assert status(W.check_stage_docs([pos(stage="Interviewing", docs=[doc("briefing")]), pos("2", stage="Screening", docs=[doc("briefing")])], TODAY)) == "OK"


def test_a_missing_document_for_a_process_in_conversation_without_any_order_is_act():
    r = W.check_stage_docs([pos(stage="Interviewing")], TODAY)
    assert status(r) == "Act" and "Acme" in r["reason"] and "kein Auftrag" in r["reason"]
    assert status(W.check_stage_docs([pos(stage="Screening")], TODAY)) == "Watch"          # Screening without an order is a gap but not urgent


def test_a_fresh_order_is_a_watch_and_one_older_than_the_threshold_is_act():
    assert status(W.check_stage_docs([pos(stage="Interviewing", orders=[order(date="2026-10-02")])], TODAY)) == "Watch"      # 0 days
    assert status(W.check_stage_docs([pos(stage="Interviewing", orders=[order(date="2026-09-30")])], TODAY)) == "Act"        # 2 days > 1
    assert status(W.check_stage_docs([pos(stage="Screening", orders=[order("cheat_sheet", date="2026-09-30")])], TODAY)) == "Watch"   # 2 days <= 3
    assert status(W.check_stage_docs([pos(stage="Screening", orders=[order("cheat_sheet", date="2026-09-28")])], TODAY)) == "Act"    # 4 days > 3


def test_an_approaching_deadline_makes_a_missing_document_act_regardless_of_the_order_age():
    p = pos(stage="Screening", due="2026-10-04", orders=[order("cheat_sheet", date="2026-10-02")])
    assert status(W.check_stage_docs([p], TODAY)) == "Act"


def test_applied_and_closed_processes_owe_nothing():
    assert status(W.check_stage_docs([pos(stage="Applied"), pos("2", stage="Closed")], TODAY)) == "OK"


def test_a_process_without_a_folder_is_named_not_silently_skipped():
    p = pos(stage="Interviewing")
    p["folder"] = False
    r = W.check_stage_docs([p], TODAY)
    assert status(r) == "Act" and "Ordner" in r["reason"]


# ---- freshness ------------------------------------------------------------------------------------------------------
def test_a_document_newer_than_every_input_is_fresh():
    assert status(W.check_fresh([pos(docs=[doc(date="2026-10-02")], inputs=[inp(date="2026-10-01")])], TODAY)) == "OK"


def test_an_input_newer_than_the_document_is_stale_and_escalates_with_age_and_deadline():
    base = dict(docs=[doc(date="2026-09-25")])
    assert status(W.check_fresh([pos(inputs=[inp(date="2026-10-02")], **base)], TODAY)) == "Watch"          # input is 0 days old
    assert status(W.check_fresh([pos(inputs=[inp(date="2026-09-30")], **base)], TODAY)) == "Act"            # 2 days > 1
    assert status(W.check_fresh([pos(inputs=[inp(date="2026-10-02")], due="2026-10-03", **base)], TODAY)) == "Act"   # deadline tomorrow


def test_without_inputs_or_without_a_document_the_freshness_check_has_nothing_to_say():
    assert status(W.check_fresh([pos(docs=[doc()]), pos("2", docs=[], inputs=[inp()])], TODAY)) == "OK"      # the missing document is the other check's job


# ---- orders ---------------------------------------------------------------------------------------------------------
def test_an_order_is_closed_by_a_document_of_that_depth_that_is_not_older():
    assert W.open_orders(pos(docs=[doc("briefing", 2, "2026-10-02")], orders=[order("briefing", "2026-10-02", 2)])) == []
    assert len(W.open_orders(pos(docs=[doc("briefing", 1, "2026-10-01")], orders=[order("briefing", "2026-10-02", 2)]))) == 1
    assert W.open_orders(pos(docs=[doc("strategy", None, "2026-10-02")], orders=[order("briefing", "2026-10-02", 1)])) == []          # a deeper document counts


def test_the_order_backlog_names_the_oldest_and_is_act_beyond_the_threshold():
    assert status(W.check_orders([pos(docs=[doc()])], TODAY)) == "OK"
    r = W.check_orders([pos(docs=[doc(date="2026-09-20")], orders=[order("briefing", "2026-09-29", 3, after=True)])], TODAY)
    assert status(r) == "Act" and "Acme" in r["reason"] and "3 Arbeitstagen" in r["reason"]
    assert status(W.check_orders([pos(docs=[doc(date="2026-09-20")], orders=[order("briefing", "2026-10-02", 3)])], TODAY)) == "Watch"
    assert status(W.check_orders([pos(stage="Applied", orders=[order("cheat_sheet", "2026-09-01")])], TODAY)) == "OK"            # Applied owes nothing


# ---- landing zone ---------------------------------------------------------------------------------------------------
def test_unacknowledged_inputs_are_watch_when_fresh_and_act_when_older_than_the_threshold():
    assert status(W.check_inputs([pos(inputs=[inp("a.pdf", "2026-10-02")], unacked=["a.pdf"])], TODAY)) == "Watch"
    assert status(W.check_inputs([pos(inputs=[inp("a.pdf", "2026-09-30")], unacked=["a.pdf"])], TODAY)) == "Act"
    assert status(W.check_inputs([pos(inputs=[inp("a.pdf", "2026-09-30")], unacked=[])], TODAY)) == "OK"


# ---- snapshot from folders ------------------------------------------------------------------------------------------
def test_snapshot_reads_documents_inputs_orders_and_the_revisit_state(tmp_path):
    base = tmp_path / "career"
    role = base / "215 Acme AG" / "Head of Data"
    (role / "20 Vorbereitung").mkdir(parents=True)
    (role / "30 Verlauf").mkdir()
    system = base / "_system"
    system.mkdir()
    (role / "20 Vorbereitung" / "Acme_AG_Briefing_2026-10-01_v1.md").write_text("x", encoding="utf-8")
    (role / "30 Verlauf" / "10-02 Telefonat-transcript.txt").write_text("x", encoding="utf-8")
    (role / "30 Verlauf" / "Debrief_Acme_AG_2026-10-01.md").write_text("x", encoding="utf-8")
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "stage", "folder_id", "due"])
        w.writeheader()
        w.writerow({"uid": "215", "company": "Acme AG", "role": "Head of Data", "stage": "Interviewing", "folder_id": "", "due": "2026-10-05"})
        w.writerow({"uid": "9", "company": "Nope", "role": "R", "stage": "Applied", "folder_id": "", "due": ""})
    (system / "intel_state.json").write_text(json.dumps({"215": {"jobs": {"x.md": {"doc": "briefing", "date": "2026-10-02", "version": 2, "after": True}}}}), encoding="utf-8")
    (system / "revisit_state.json").write_text(json.dumps({"215": {"known_files": ["Debrief_Acme_AG_2026-10-01.md"]}}), encoding="utf-8")
    rows = list(csv.DictReader(open(system / "pipeline.csv", newline="", encoding="utf-8")))
    got = W.snapshot(str(system), str(base), rows, TODAY)
    assert [p["uid"] for p in got] == ["215"]                                 # Applied is not in scope
    p = got[0]
    assert p["folder"] is True and p["due"] == "2026-10-05" and p["stage"] == "Interviewing"
    assert [(d["kind"], d["version"], d["date"]) for d in p["docs"]] == [("briefing", 1, "2026-10-01")]
    assert [i["name"] for i in p["inputs"]] == ["10-02 Telefonat-transcript.txt"]        # the debrief is generated, not an input
    assert p["unacked"] == ["10-02 Telefonat-transcript.txt"]
    assert p["orders"] == [{"doc": "briefing", "date": "2026-10-02", "version": 2, "after": True}]


# ---- quality and evidence of the current document (step B) ----------------------------------------------------------
def q(**over):
    m = {"file": "Acme_Briefing_2026-10-01_v1.md", "doc": "briefing", "version": 1, "facts": 10, "inferences": 5, "facts_unsourced": 0, "sources": 6, "domains": 3,
         "dangling": [], "oldest_source_age": 5, "unverified": 0, "open_section": True, "lint": "pass", "lint_rules": []}
    m.update(over)
    return m


def with_q(quality, **over):
    p = pos(docs=[doc()], **over)
    p["quality"] = quality
    return p


def test_the_lint_result_of_the_current_document_decides_the_quality_check():
    assert status(W.check_quality([with_q(q())], TODAY)) == "OK"
    r = W.check_quality([with_q(q(lint="warn", lint_rules=["tags", "open"]))], TODAY)
    assert status(r) == "Watch" and "tags" in r["reason"] and "Acme" in r["reason"]
    assert status(W.check_quality([with_q(q(lint="warn", lint_rules=["tags"]), due="2026-10-04")], TODAY)) == "Act"          # a warning matters when the date is near
    assert status(W.check_quality([with_q(q(lint="fail", lint_rules=["section"]))], TODAY)) == "Act"


def test_a_document_that_cannot_be_checked_is_named_and_an_error_is_act():
    r = W.check_quality([with_q(None)], TODAY)
    assert status(r) == "Watch" and "nicht prüfbar" in r["reason"]
    assert status(W.check_quality([with_q({"error": "OSError: x"})], TODAY)) == "Act"
    assert status(W.check_quality([pos(docs=[])], TODAY)) == "OK"                      # no document: the stage-document check owns that


def test_the_evidence_check_flags_dangling_references_unsourced_facts_and_single_sources():
    assert status(W.check_evidence([with_q(q())], TODAY)) == "OK"
    assert status(W.check_evidence([with_q(q(dangling=[9]))], TODAY)) == "Act"
    r = W.check_evidence([with_q(q(facts_unsourced=3))], TODAY)
    assert status(r) == "Watch" and "3 von 10" in r["reason"]
    assert status(W.check_evidence([with_q(q(facts_unsourced=2))], TODAY)) == "OK"            # exactly 20 percent is tolerated
    assert status(W.check_evidence([with_q(q(domains=1))], TODAY)) == "Watch"


def test_old_sources_matter_only_when_the_date_is_near():
    old = q(oldest_source_age=20)
    assert status(W.check_evidence([with_q(old)], TODAY)) == "OK"
    assert status(W.check_evidence([with_q(old, due="2026-10-08")], TODAY)) == "Watch"      # 6 days
    assert status(W.check_evidence([with_q(old, due="2026-10-04")], TODAY)) == "Act"        # 2 days


def test_snapshot_attaches_the_quality_of_the_current_document(tmp_path):
    import intel_lint
    base = tmp_path / "career"
    role = base / "215 Acme AG" / "Head of Data"
    (role / "20 Vorbereitung").mkdir(parents=True)
    system = base / "_system"
    system.mkdir()
    (role / "20 Vorbereitung" / "Acme_AG_Briefing_2026-10-01_v1.md").write_text("# Briefing\n\n## Quellen\n1. https://example.org/a abgerufen 2026-09-30\n", encoding="utf-8")
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "stage", "folder_id", "due"])
        w.writeheader()
        w.writerow({"uid": "215", "company": "Acme AG", "role": "Head of Data", "stage": "Interviewing", "folder_id": "", "due": ""})
    rows = list(csv.DictReader(open(system / "pipeline.csv", newline="", encoding="utf-8")))
    quality = W.snapshot(str(system), str(base), rows, TODAY)[0]["quality"]
    assert quality["doc"] == "briefing" and quality["version"] == 1 and quality["file"].startswith("Acme_AG_Briefing") and quality["lint"] == "fail"
    assert quality["sources"] == 1 and quality["domains"] == 1 and quality["oldest_source_age"] == 2



# ---- ages count working days: the routines run Monday to Friday only ------------------------------------------------
def test_working_days_skip_the_weekend():
    assert W.age_days("2026-10-05", "2026-10-02") == 1          # Friday -> Monday: one run day in between
    assert W.age_days("2026-10-06", "2026-10-02") == 2
    assert W.age_days("2026-10-05", "2026-10-03") == 1          # Saturday -> Monday
    assert W.age_days("2026-10-02", "2026-10-02") == 0 and W.age_days("2026-10-02", "bad") is None


def test_an_order_from_friday_is_not_overdue_on_monday_but_is_on_tuesday():
    friday = [pos(stage="Interviewing", orders=[order(date="2026-10-02")])]
    assert status(W.check_stage_docs(friday, "2026-10-05")) == "Watch"          # 1 working day, threshold 1
    assert status(W.check_stage_docs(friday, "2026-10-06")) == "Act"
    assert status(W.check_orders([pos(docs=[doc(date="2026-09-20")], orders=[order("briefing", "2026-10-02", 3)])], "2026-10-05")) == "Watch"


def test_an_input_from_friday_is_not_overdue_on_monday():
    p = pos(docs=[doc(date="2026-09-25")], inputs=[inp(date="2026-10-02")], unacked=["Mail.pdf"])
    assert status(W.check_fresh([p], "2026-10-05")) == "Watch" and status(W.check_inputs([p], "2026-10-05")) == "Watch"
    assert status(W.check_fresh([p], "2026-10-06")) == "Act" and status(W.check_inputs([p], "2026-10-06")) == "Act"


def test_the_reasons_name_working_days():
    r = W.check_orders([pos(docs=[doc(date="2026-09-20")], orders=[order("briefing", "2026-09-29", 3, after=True)])], TODAY)
    assert "3 Arbeitstagen" in r["reason"]


# ---- prep brief completeness ----------------------------------------------------------------------------------------
def prep(file="Prep_Brief_X_2026-10-07.html", gaps=0, questions=True):
    return {"file": file, "gaps": gaps, "questions": questions}


def cockpit(date="2026-10-07", gaps=0):
    return {"file": "Cockpit_X_%s.html" % date, "date": date, "gaps": gaps}


def test_prep_brief_is_owed_from_interviewing_on_and_complete_means_no_gaps_and_ranked_questions():
    assert status(W.check_prep([pos(stage="Interviewing", due="2026-10-20")], TODAY)) == "Watch"                      # no prep brief at all
    assert status(W.check_prep([dict(pos(), prep=prep(), cockpit=cockpit())], TODAY)) == "OK"
    assert status(W.check_prep([pos(stage="Screening"), pos(stage="Applied")], TODAY)) == "OK"                      # owes nothing yet


def test_prep_gaps_and_missing_questions_are_named_and_escalate_with_the_date():
    far = dict(pos(company="Kekswerk", due="2026-10-20"), prep=prep(gaps=3, questions=False))
    rec = W.check_prep([far], TODAY)
    assert status(rec) == "Watch" and "Kekswerk" in rec["reason"] and "Fragen" in rec["reason"] and "3" in rec["reason"]
    near = dict(pos(company="Kekswerk", due="2026-10-03"), prep=prep(gaps=3))
    assert status(W.check_prep([near], TODAY)) == "Act"


def test_snapshot_reads_the_current_prep_brief(tmp_path):
    base = tmp_path / "career"
    voraus = base / "215 Acme AG" / "Head of Data" / "20 Vorbereitung"
    voraus.mkdir(parents=True)
    (base / "_system").mkdir()
    (voraus / "Prep_Brief_Acme_2026-09-01.html").write_text("<p>old</p>", encoding="utf-8")
    (voraus / "Prep_Brief_Acme_2026-10-01.html").write_text('<span class="gap">PREP GAP</span> pending org research. <div id="meine-fragen"></div>', encoding="utf-8")
    state = W._prep_state(str(voraus.parent))
    assert state["file"] == "Prep_Brief_Acme_2026-10-01.html" and state["gaps"] == 2 and state["questions"] is True
    assert W._prep_state(str(base)) == {"file": None, "gaps": 0, "questions": False}


def test_a_prep_brief_older_than_the_current_briefing_is_named():
    p = dict(pos(company="Kekswerk", due="2026-10-20", docs=[doc("briefing", 2, "2026-10-07")]), prep=dict(prep(), date="2026-10-02"))
    rec = W.check_prep([p], TODAY)
    assert status(rec) == "Watch" and "älter als das Briefing" in rec["reason"]
    fresh = dict(p, prep=dict(prep(), date="2026-10-07"), cockpit=cockpit())
    assert status(W.check_prep([fresh], TODAY)) == "OK"


def test_prep_state_carries_the_date_of_the_prep_brief(tmp_path):
    voraus = tmp_path / "Acme" / "Role" / "20 Vorbereitung"
    voraus.mkdir(parents=True)
    (voraus / "Prep_Brief_Acme_2026-10-07.html").write_text('<div id="meine-fragen"></div>', encoding="utf-8")
    assert W._prep_state(str(voraus.parent))["date"] == "2026-10-07"


# ---- cockpit per conversation ----------------------------------------------------------------------------------
def test_cockpit_is_owed_from_interviewing_on_and_checked_like_the_prep_brief():
    base = dict(pos(company="Kekswerk", due="2026-10-20", docs=[doc("briefing", 2, "2026-10-07")]), prep=dict(prep(), date="2026-10-07"))
    rec = W.check_prep([dict(base, cockpit=None)], TODAY)
    assert status(rec) == "Watch" and "Cockpit fehlt" in rec["reason"]
    assert status(W.check_prep([dict(base, cockpit={"file": "Cockpit_X_2026-10-07.html", "date": "2026-10-07", "gaps": 0})], TODAY)) == "OK"
    old = W.check_prep([dict(base, cockpit={"file": "Cockpit_X_2026-10-01.html", "date": "2026-10-01", "gaps": 0})], TODAY)
    assert status(old) == "Watch" and "Cockpit" in old["reason"] and "älter" in old["reason"]
    gap = W.check_prep([dict(base, cockpit={"file": "Cockpit_X_2026-10-07.html", "date": "2026-10-07", "gaps": 2})], TODAY)
    assert "Cockpit" in gap["reason"] and "Lücke" in gap["reason"]


def test_cockpit_state_reads_the_newest_cockpit_html(tmp_path):
    voraus = tmp_path / "Acme" / "Role" / "20 Vorbereitung"
    voraus.mkdir(parents=True)
    (voraus / "Cockpit_Acme_2026-10-01.html").write_text("<p>old</p>", encoding="utf-8")
    (voraus / "Cockpit_Acme_2026-10-07.html").write_text('<span class="gap">PREP GAP</span>', encoding="utf-8")
    (voraus / "Nordberatung_Cockpit_Brandt_20260911.pdf").write_text("pdf", encoding="utf-8")                      # the owner's own cockpit files do not count
    st = W._cockpit_state(str(voraus.parent))
    assert st == {"file": "Cockpit_Acme_2026-10-07.html", "date": "2026-10-07", "gaps": 1}
    assert W._cockpit_state(str(tmp_path)) is None
