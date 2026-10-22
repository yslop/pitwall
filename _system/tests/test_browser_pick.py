"""browser_pick: Jev chooses the next click from a list of page elements (Manifest job-crm.browser_pick).
Offline: every TypeSafe request is held against api_contract.py, no network."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_contract as C
import browser_pick as B

from unittest.mock import patch, MagicMock

ELEMENTS = [
    {"id": "e1", "role": "button", "label": "Interviewing"},
    {"id": "e2", "role": "link", "label": "Lesezone öffnen"},
    {"id": "e3", "role": "button", "label": "Archiv"},
]


def mock_ts(body, seen=None):
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)

    def opener(req, timeout=None):
        if seen is not None:
            seen.append(json.loads(req.data))
        return resp
    return patch("urllib.request.urlopen", side_effect=opener)


def _answer(choice, conf=0.9):
    return {"model": "jev-latest", "answers": {"next": {"choice": choice, "confidence": conf}},
            "usage": {"input_tokens": 120}}


def test_request_meets_the_contract_and_sends_only_role_and_label():
    seen = []
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer("e2"), seen):
        B.pick_next("Lesezone prüfen", ELEMENTS)
    assert seen and C.check_request(seen[0]) == []
    assert "http" not in json.dumps(seen[0]["questions"]).lower()


def test_picks_the_element_jev_chose():
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer("e2")):
        r = B.pick_next("Lesezone prüfen", ELEMENTS)
    assert r == {"decision": "click", "id": "e2", "confidence": 0.9}


def test_done_and_blocked_are_valid_answers():
    for word in ("done", "blocked"):
        with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer(word)):
            assert B.pick_next("x", ELEMENTS)["decision"] == word


def test_low_confidence_is_unklar_not_a_click():
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer("e1", 0.4)):
        assert B.pick_next("x", ELEMENTS) == {"decision": "UNKLAR", "confidence": 0.4}


def test_caps_elements_and_label_length():
    many = [{"id": "e%d" % i, "role": "button", "label": "L" * 200} for i in range(40)]
    seen = []
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer("done"), seen):
        B.pick_next("x", many)
    crit = seen[0]["questions"]["next"]["criteria"]
    assert len(crit) == B.MAX_ELEMENTS + 2          # + done + blocked
    assert all(len(v) <= B.MAX_LABEL + 20 for v in crit.values())


def test_fast_path_skips_jev_when_exactly_one_label_matches_the_goal():
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer("e3")) as m:
        r = B.pick_next("klicke Archiv", ELEMENTS)
    assert r["id"] == "e3" and r["decision"] == "click" and not m.called


def test_drifted_answer_and_missing_key_fail_closed():
    flat = {"model": "jev-latest", "next": {"choice": "e1", "confidence": 0.9}, "usage": {"input_tokens": 5}}
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(flat):
        assert "error" in B.pick_next("x", ELEMENTS)
    with patch.object(B, "get_typesafe_api_key", return_value=""):
        assert "error" in B.pick_next("x", ELEMENTS)


def test_unknown_choice_id_is_an_error_not_a_click():
    with patch.object(B, "get_typesafe_api_key", return_value="k"), mock_ts(_answer("e99")):
        assert "error" in B.pick_next("x", ELEMENTS)


def test_key_value_never_appears_in_the_result():
    with patch.object(B, "get_typesafe_api_key", return_value="SECRET-KEY-123"), mock_ts(_answer("e2")):
        assert "SECRET-KEY-123" not in json.dumps(B.pick_next("x", ELEMENTS))
