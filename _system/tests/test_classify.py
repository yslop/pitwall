import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest

from unittest.mock import patch, MagicMock
from conftest import (MOCK_REJECTION_RESPONSE, MOCK_LOW_CONFIDENCE_RESPONSE,
                      REJECTION_EMAIL, INTERVIEW_EMAIL)


def mock_typesafe_call(response_body: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("urllib.request.urlopen", return_value=mock_resp)


def test_classify_returns_signal_and_confidence():
    with mock_typesafe_call(MOCK_REJECTION_RESPONSE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}):
            from typesafe_classify import classify_email
            result = classify_email(REJECTION_EMAIL["subject"], REJECTION_EMAIL["body"])
    assert result["signal"] == "closed_rejected"
    assert result["confidence"] == pytest.approx(0.92)


def test_classify_missing_api_key_returns_error():
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["TYPESAFE_ENV_FILE"] = os.devnull  # ignore the real _system/.env
    with patch.dict(os.environ, env, clear=True):
        from typesafe_classify import classify_email
        result = classify_email("subject", "body")
    assert "error" in result


def test_stage_map_covers_all_signals():
    from typesafe_classify import STAGE_MAP
    expected_signals = {
        "applied", "screening", "interviewing", "final",
        "closed_rejected", "closed_withdrawn", "closed_declined",
        "closed_signed", "no_match"
    }
    assert set(STAGE_MAP.keys()) == expected_signals


def test_no_match_maps_to_none():
    from typesafe_classify import STAGE_MAP
    assert STAGE_MAP["no_match"] is None


def test_closed_rejected_sets_outcome():
    from typesafe_classify import STAGE_MAP
    entry = STAGE_MAP["closed_rejected"]
    assert entry["stage"] == "Closed"
    assert entry["outcome"] == "rejected"


def test_confidence_constants():
    from typesafe_classify import CONFIDENCE_HIGH, CONFIDENCE_LOW
    assert CONFIDENCE_HIGH == 0.75
    assert CONFIDENCE_LOW == 0.65
    assert CONFIDENCE_LOW < CONFIDENCE_HIGH


def test_classify_missing_answers_key_returns_error():
    with mock_typesafe_call({"model": "jev-1.13.0", "usage": {}}):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}):
            from typesafe_classify import classify_email
            result = classify_email("subject", "body")
    assert "error" in result


def test_state_truncated_to_800_chars():
    captured = {}
    def fake_urlopen(req, timeout=None):
        import json as j
        body = j.loads(req.data.decode())
        captured["state_len"] = len(body["state"])
        return MagicMock(**{
            "read.return_value": j.dumps(MOCK_REJECTION_RESPONSE).encode(),
            "__enter__": lambda s: s,
            "__exit__": MagicMock(return_value=False)
        })
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}):
            from typesafe_classify import classify_email
            classify_email("subject", "x" * 2000)
    assert captured["state_len"] <= 800
