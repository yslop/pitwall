"""pilot_gate.py: go only on complete evidence; otherwise say what is open."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pilot_gate as G


def rep(created, cost=None):
    return {"cockpits_created": created, "estimated_ai_cost_by_document_type": {"calibrated": cost is not None, **({"cockpit": cost} if cost is not None else {})}}


def pilots(n, created=(1, 1), cost=0.4):
    return {"p%d" % i: [rep(created[0], cost), rep(created[1], cost)] for i in range(n)}


def answers(n, helped=True, pay=3.0):
    return {"p%d" % i: {"helped": helped, "would_pay_eur": pay} for i in range(n)}


def test_go_when_three_of_five_meet_every_criterion():
    res = G.evaluate(pilots(5), answers(5), max_cost_per_cockpit=1.0)
    assert res["go"] is True and res["active"] == 5 and res["helped"] == 5 and res["would_pay"] == 5 and res["needed"] == 3 and res["cost_ok"] is True


def test_no_go_when_too_few_pilots_pay():
    ans = answers(5, pay=1.0)
    res = G.evaluate(pilots(5), ans, max_cost_per_cockpit=1.0)
    assert res["go"] is False and "zahlen" in res["reason"]


def test_open_without_a_cost_threshold_or_with_too_few_pilots():
    assert G.evaluate(pilots(5), answers(5))["go"] is None and "Kostenschwelle" in G.evaluate(pilots(5), answers(5))["reason"]
    res = G.evaluate(pilots(3), answers(3), max_cost_per_cockpit=1.0)
    assert res["go"] is None and "Piloten" in res["reason"]


def test_missing_answers_make_the_gate_open_not_no():
    res = G.evaluate(pilots(5), {"p0": {"helped": True, "would_pay_eur": 3.0}}, max_cost_per_cockpit=1.0)
    assert res["helped"] == 1 and res["go"] is None and "Antworten" in res["reason"]
    res = G.evaluate(pilots(5), {p: {"helped": True, "would_pay_eur": None} for p in pilots(5)}, max_cost_per_cockpit=1.0)
    assert res["go"] is None and "Antworten" in res["reason"]


def test_pilots_with_fewer_than_two_reports_make_the_gate_open_but_are_still_counted():
    res = G.evaluate({"p0": [], "p1": [rep(2)], "p2": [rep(1), rep(1)], "p3": [rep(0), rep(0)]}, answers(4), max_cost_per_cockpit=1.0)
    assert res["active"] == 2 and res["go"] is None and "weniger als zwei Berichte" in res["reason"]


def test_an_explicit_no_from_the_pilots_is_a_real_no():
    res = G.evaluate(pilots(5), answers(5, helped=False), max_cost_per_cockpit=1.0)
    assert res["go"] is False and "Hilfe" in res["reason"]


def test_cost_above_the_threshold_blocks():
    res = G.evaluate(pilots(5, cost=2.0), answers(5), max_cost_per_cockpit=1.0)
    assert res["cost_ok"] is False and res["go"] is False
