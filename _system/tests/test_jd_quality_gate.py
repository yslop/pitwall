import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest

from unittest.mock import patch, MagicMock


def mock_ts(response_body):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("urllib.request.urlopen", return_value=mock_resp)


def _ts_response(answers):
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 300, "output_tokens": 20}}


MOCK_HIGH_QUALITY = _ts_response({
    "clarity": {"type": "score", "score": 3},
    "requirements_realism": {"type": "score", "score": 3},
    "compensation_transparency": {"type": "score", "score": 3},
})

MOCK_LOW_QUALITY = _ts_response({
    "clarity": {"type": "score", "score": 1},
    "requirements_realism": {"type": "score", "score": 0},
    "compensation_transparency": {"type": "score", "score": 0},
})

MOCK_BORDERLINE = _ts_response({
    "clarity": {"type": "score", "score": 2.4},
    "requirements_realism": {"type": "score", "score": 1.8},
    "compensation_transparency": {"type": "score", "score": 1.8},
})


def test_high_quality_jd_passes():
    with mock_ts(MOCK_HIGH_QUALITY):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from jd_quality_gate import score_jd
            result = score_jd("Head of Data", "ACME AG", "Full JD text")
    assert result["pass"] is True
    assert result["overall"] == pytest.approx(1.0, abs=0.01)


def test_low_quality_jd_fails():
    with mock_ts(MOCK_LOW_QUALITY):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from jd_quality_gate import score_jd
            result = score_jd("Head of Data", "ACME AG", "vague text")
    assert result["pass"] is False


def test_weighted_composite_matches_formula():
    with mock_ts(MOCK_BORDERLINE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from jd_quality_gate import score_jd
            result = score_jd("Head of Data", "ACME AG", "text")
    expected = round(0.4 * (2.4 / 3) + 0.3 * (1.8 / 3) + 0.3 * (1.8 / 3), 4)
    assert result["overall"] == pytest.approx(expected, abs=0.001)


def test_pass_threshold_is_point_seven():
    from jd_quality_gate import _PASS_THRESHOLD
    assert _PASS_THRESHOLD == 0.7


def test_missing_api_key_returns_error():
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["TYPESAFE_ENV_FILE"] = os.devnull  # ignore the real _system/.env
    with patch.dict(os.environ, env, clear=True):
        from jd_quality_gate import score_jd
        result = score_jd("title", "co", "jd")
    assert "error" in result


def test_empty_jd_text_does_not_crash():
    with mock_ts(MOCK_LOW_QUALITY):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from jd_quality_gate import score_jd
            result = score_jd("Head of Data", "ACME AG", "")
    assert "overall" in result
    assert result["pass"] is False


def test_typesafe_network_error_returns_error_dict():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from jd_quality_gate import score_jd
            result = score_jd("title", "co", "jd")
    assert "error" in result


def test_missing_answers_key_returns_error_dict():
    with mock_ts({"model": "jev-1.13.0", "usage": {}}):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from jd_quality_gate import score_jd
            result = score_jd("title", "co", "jd")
    assert "error" in result
