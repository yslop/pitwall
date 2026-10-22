"""intel_queue.py: what the Sync session researches next, ranked by stage and deadline, capped per run."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_queue as Q
from test_warranty import pos, doc, order, prep, cockpit

TODAY = "2026-10-07"


def kinds(items):
    return [(i["uid"], i["kind"]) for i in items]


def test_a_missing_stage_document_with_an_order_is_queued_as_stage_doc():
    items = Q.build_queue([pos(uid="21", stage="Screening", orders=[order("cheat_sheet")])], TODAY)
    assert kinds(items) == [("21", "stage_doc")] and items[0]["doc"] == "cheat_sheet"


def test_an_open_after_interview_order_comes_before_a_stage_doc_of_the_same_stage():
    a = dict(pos(uid="1", stage="Interviewing", docs=[doc("briefing", 1, "2026-10-01")], orders=[order("briefing", after=True, date="2026-10-06", version=2)]), prep=dict(prep(), date="2026-10-07"), cockpit=cockpit())
    b = pos(uid="2", stage="Interviewing", orders=[order("briefing")])
    assert kinds(Q.build_queue([b, a], TODAY)) == [("1", "after_interview"), ("2", "stage_doc")]


def test_deadline_within_three_days_beats_stage_then_stage_then_due_date():
    near_screening = pos(uid="3", stage="Screening", due="2026-10-08", orders=[order("cheat_sheet")])
    final = pos(uid="4", stage="Final", due="2026-10-30", orders=[order("strategy")])
    interviewing = pos(uid="5", stage="Interviewing", due="2026-10-20", orders=[order("briefing")])
    assert [i["uid"] for i in Q.build_queue([interviewing, final, near_screening], TODAY)] == ["3", "4", "5"]


def test_prep_content_is_queued_once_the_document_exists_and_the_prep_brief_is_incomplete_or_old():
    p = dict(pos(uid="6", stage="Interviewing", docs=[doc("briefing", 2, "2026-10-07")]), prep=prep(gaps=2, questions=False, file="Prep_Brief_X_2026-10-01.html"))
    assert kinds(Q.build_queue([p], TODAY)) == [("6", "prep_content")]
    done = dict(pos(uid="6", stage="Interviewing", docs=[doc("briefing", 2, "2026-10-07")]), prep=dict(prep(), date="2026-10-07"), cockpit=cockpit())
    assert Q.build_queue([done], TODAY) == []
    no_cockpit = dict(done, cockpit=None)
    assert kinds(Q.build_queue([no_cockpit], TODAY)) == [("6", "prep_content")]
    assert Q.build_queue([pos(uid="7", stage="Screening", docs=[doc("cheat_sheet")])], TODAY) == []          # Screening owes no prep brief


def test_limit_caps_the_run_and_reports_what_is_left():
    ps = [pos(uid=str(n), stage="Interviewing", orders=[order("briefing")]) for n in range(1, 6)]
    items = Q.build_queue(ps, TODAY, limit=3)
    assert len(items) == 3
    assert Q.build_queue(ps, TODAY)[0]["total"] == 5 and items[0]["total"] == 5


def test_nothing_to_do_is_an_empty_queue():
    assert Q.build_queue([dict(pos(docs=[doc()]), prep=dict(prep(), date="2026-10-07"), cockpit=cockpit())], TODAY) == []
