"""API contract (spec 2026-09-27-api-contract-design.md): every TypeSafe call site and the BA parser
are held against the one contract in api_contract.py, and the live smoke test is exercised offline."""
import io
import json
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api_contract as C  # noqa: E402
import browser_pick  # noqa: E402
import coverage  # noqa: E402
import discovery  # noqa: E402
import fit_score  # noqa: E402
import jd_quality_gate  # noqa: E402
import prep_engine  # noqa: E402
import typesafe_classify  # noqa: E402

NOW = datetime(2026, 9, 27, 7, 0, 0)
FLAT = {"model": "jev-latest", "signal": {"choice": "applied", "confidence": 0.9}, "usage": {"input_tokens": 5}}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(seen, respond):
    """urlopen stand-in: records the parsed request payload, answers with respond(payload)."""
    def _open(req, timeout=None):
        payload = json.loads(req.data) if getattr(req, "data", None) else None
        seen.append(payload)
        return _Resp(json.dumps(respond(payload)).encode())
    return _open


PROFILE = {"capabilities": [{"name": "Data Strategy", "level": 3, "evidence": "CV"},
                            {"name": "AI Governance", "level": 2, "evidence": ""}]}

# (name, module, call) — every place in Pitwall that talks to TypeSafe
CALL_SITES = [
    ("classify", typesafe_classify, lambda: typesafe_classify.classify_email("Einladung", "Gespräch am Dienstag")),
    ("fit_score", fit_score, lambda: fit_score.score_opportunity("Head of Data", "Muster AG", "Aufbau eines Data Teams")),
    ("jd_quality", jd_quality_gate, lambda: jd_quality_gate.score_jd("Head of Data", "Muster AG", "Aufbau eines Data Teams")),
    ("prep_noul", prep_engine, lambda: prep_engine.noul_readiness_gate("Head of Data", "Muster AG", "Aufbau")),
    ("discovery", discovery, lambda: discovery._typesafe_lane_and_maturity("Team Lead Data", "Muster AG", "Budget, Team")),
    ("browser_pick", browser_pick, lambda: browser_pick.pick_next("Lesezone prüfen", [{"id": "e1", "role": "button", "label": "Alpha"}, {"id": "e2", "role": "link", "label": "Beta"}])),
    ("coverage", coverage, lambda: coverage.jev_judge([(0, "Datenstrategie verantworten")], PROFILE, api_key="k")),
]


def _arm(monkeypatch, module, respond):
    seen = []
    if hasattr(module, "get_typesafe_api_key"):
        monkeypatch.setattr(module, "get_typesafe_api_key", lambda: "k")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen(seen, respond))
    return seen


def _failed(result):
    if isinstance(result, dict) and "error" in result:
        return True
    return result == {"research_sufficient": False, "bypass_identified": False}


# ---- the contract itself ------------------------------------------------------------------------
def test_fixture_meets_its_own_contract_for_every_question_type():
    qs = C.SMOKE_QUESTIONS
    assert C.check_request({"state": "x", "model": "jev-latest", "questions": qs}) == []
    assert C.check_typesafe_response(C.typesafe_fixture(qs), qs) == []


def test_request_rules_catch_the_known_mistakes():
    no_criteria = {"s": {"type": "score", "instructions": "How good?"}}
    assert any("criteria" in p for p in C.check_request({"state": "x", "model": "jev-latest", "questions": no_criteria}))
    assert C.check_request({"state": "", "model": "jev-latest", "questions": C.SMOKE_QUESTIONS})
    assert C.check_request({"state": "x", "model": "gpt", "questions": C.SMOKE_QUESTIONS})
    assert C.check_request({"state": "x", "model": "jev-latest", "questions": {"q": {"type": "guess"}}})


def test_flat_response_of_22_09_is_rejected():
    problems = C.check_typesafe_response(FLAT, {"signal": {"type": "choice", "criteria": {"applied": "a", "no_match": "b"}}})
    assert problems and "answers" in problems[0]


def test_response_rules_check_fields_and_ranges():
    qs = C.SMOKE_QUESTIONS
    good = C.typesafe_fixture(qs)
    bad = json.loads(json.dumps(good))
    bad["answers"]["n"]["noul"] = 1.7
    bad["answers"]["s"]["score"] = 9
    bad["answers"]["c"]["choice"] = "maybe"
    del bad["answers"]["c"]["confidence"]
    problems = C.check_typesafe_response(bad, qs)
    assert len(problems) == 4


# ---- every call site against the contract -------------------------------------------------------
def test_every_call_site_sends_a_valid_request_and_reads_the_contract_answer(monkeypatch):
    for name, module, call in CALL_SITES:
        seen = _arm(monkeypatch, module, lambda p: C.typesafe_fixture(p["questions"]))
        result = call()
        assert seen, name + ": no TypeSafe request was made"
        assert C.check_request(seen[0]) == [], (name, C.check_request(seen[0]))
        assert not (isinstance(result, dict) and "error" in result), (name, result)


def test_every_call_site_fails_safe_on_a_drifted_answer(monkeypatch):
    for name, module, call in CALL_SITES:
        _arm(monkeypatch, module, lambda p: FLAT)
        result = call()  # must not raise
        assert _failed(result), (name, result)


# ---- BA-Jobbörse --------------------------------------------------------------------------------
def test_ba_parser_reads_the_contract_fixture(monkeypatch):
    monkeypatch.setattr(discovery, "requests", None)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen([], lambda p: C.ba_fixture(2)))
    rows = discovery._search_ba(100, "2026-09-27")
    assert len(rows) == 2 and rows[0]["company"] and rows[0]["role"] and "jobdetail" in rows[0]["employer_url"]


def test_ba_contract_flags_renamed_fields_and_empty_lists():
    assert C.check_ba_response(C.ba_fixture(1)) == []
    assert C.check_ba_response({"stellenangebote": []})
    assert C.check_ba_response({"ergebnisliste": []})
    assert C.check_ba_response({"ergebnisliste": [{"arbeitgeber": "X", "titel": "Y", "refnr": "1"}]})


# ---- live smoke, exercised offline --------------------------------------------------------------
def test_smoke_writes_ok_state_when_both_apis_match(tmp_path):
    def opener(req, timeout=None):
        if "arbeitsagentur" in req.full_url:
            return _Resp(json.dumps(C.ba_fixture(1)).encode())
        return _Resp(json.dumps(C.typesafe_fixture(json.loads(req.data)["questions"])).encode())
    state = C.smoke(str(tmp_path), NOW, api_key="k", opener=opener)
    assert state["typesafe"]["ok"] is True and state["ba"]["ok"] is True
    assert json.load(open(tmp_path / "contract_state.json"))["ts"] == "2026-09-27T07:00:00"


def test_smoke_reports_drift_and_network_errors_without_raising(tmp_path):
    def opener(req, timeout=None):
        if "arbeitsagentur" in req.full_url:
            raise OSError("HTTP 403")
        return _Resp(json.dumps(FLAT).encode())
    state = C.smoke(str(tmp_path), NOW, api_key="k", opener=opener)
    assert state["typesafe"]["ok"] is False and "answers" in state["typesafe"]["problems"][0]
    assert state["ba"]["ok"] is False and "403" in state["ba"]["problems"][0]


def test_smoke_without_key_skips_typesafe_instead_of_faking_it(tmp_path):
    calls = []

    def opener(req, timeout=None):
        calls.append(req.full_url)
        return _Resp(json.dumps(C.ba_fixture(1)).encode())
    state = C.smoke(str(tmp_path), NOW, api_key="", opener=opener)
    assert state["typesafe"]["ok"] is None and all("typesafe" not in u for u in calls)


def test_main_cli_respects_system_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "get_typesafe_api_key", lambda: "k")
    def opener(req, timeout=None):
        if "arbeitsagentur" in req.full_url:
            return _Resp(json.dumps(C.ba_fixture(1)).encode())
        return _Resp(json.dumps(C.typesafe_fixture(json.loads(req.data)["questions"])).encode())
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    code = C.main(["--smoke", "--system-dir", str(tmp_path)])
    assert code == 0
    assert os.path.exists(tmp_path / "contract_state.json")
    show_code = C.main(["--show", "--system-dir", str(tmp_path)])
    assert show_code == 0
