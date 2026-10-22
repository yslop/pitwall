import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest

from unittest.mock import patch, MagicMock

def _ts_response(answers):
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 400, "output_tokens": 25}}


# Raw scores are on TypeSafe's 0-3 scale (4 criteria levels, indices 0-3);
# fit_score.py normalizes by /3. Values below are old_0_1_value * 3, so the
# resulting normalized dims — and every existing assertion below — are
# numerically identical to before this fix.
MOCK_HIGH_FIT_RESPONSE = _ts_response({
    "lane_fit":      {"type": "score", "score": 2.70},
    "salary_fit":    {"type": "score", "score": 2.55},
    "stability":     {"type": "score", "score": 2.25},
    "bypass_signal": {"type": "score", "score": 1.80},
    "scope_fit":     {"type": "score", "score": 2.64},
    "urgency":       {"type": "score", "score": 2.10},
})

MOCK_LOW_FIT_RESPONSE = _ts_response({
    "lane_fit":      {"type": "score", "score": 0.60},
    "salary_fit":    {"type": "score", "score": 0.30},
    "stability":     {"type": "score", "score": 1.50},
    "bypass_signal": {"type": "score", "score": 0.90},
    "scope_fit":     {"type": "score", "score": 0.75},
    "urgency":       {"type": "score", "score": 1.20},
})


def mock_ts(response_body):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("urllib.request.urlopen", return_value=mock_resp)


def test_score_returns_ts_fit_score():
    with mock_ts(MOCK_HIGH_FIT_RESPONSE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from fit_score import score_opportunity
            result = score_opportunity("Head of Data", "ACME AG", "CDO role, own team", "")
    assert "ts_fit_score" in result
    assert 0.0 <= result["ts_fit_score"] <= 1.0


def test_score_computes_mean_of_six():
    with mock_ts(MOCK_HIGH_FIT_RESPONSE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from fit_score import score_opportunity
            result = score_opportunity("Head of Data", "ACME AG", "CDO role", "")
    expected = round((0.90 + 0.85 + 0.75 + 0.60 + 0.88 + 0.70) / 6, 4)
    assert result["ts_fit_score"] == pytest.approx(expected, abs=0.001)


def test_salary_fit_top():
    with mock_ts(MOCK_HIGH_FIT_RESPONSE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from fit_score import score_opportunity
            result = score_opportunity("CDO", "Corp", "salary >150k", "")
    assert result["salary_fit"] == "top"


def test_salary_fit_below():
    with mock_ts(MOCK_LOW_FIT_RESPONSE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from fit_score import score_opportunity
            result = score_opportunity("IT Coord", "Corp", "salary 60k", "")
    assert result["salary_fit"] == "below"


def test_missing_api_key_returns_error():
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["TYPESAFE_ENV_FILE"] = os.devnull  # ignore the real _system/.env
    with patch.dict(os.environ, env, clear=True):
        from fit_score import score_opportunity
        result = score_opportunity("title", "co", "jd", "")
    assert "error" in result


def test_salary_fit_thresholds_cover_full_range():
    from fit_score import SALARY_FIT_THRESHOLDS
    labels = [label for _, label in SALARY_FIT_THRESHOLDS]
    assert set(labels) == {"top", "high", "mid", "stretch", "below"}


def test_boost_capped_at_15():
    with mock_ts(MOCK_HIGH_FIT_RESPONSE):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from fit_score import score_opportunity
            result = score_opportunity("Head of Data", "ACME AG", "CDO role", "")
    assert result["boost_contribution"] <= 15


def test_all_questions_have_criteria():
    # TypeSafe's Score primitive requires a "criteria" array (2-10 ordered
    # level descriptions) on every question — without it the live API
    # rejects the request with 422 Unprocessable Entity. Guards against
    # this regressing silently again.
    from fit_score import _QUESTIONS
    for name, q in _QUESTIONS.items():
        assert "criteria" in q, f"{name} is missing required 'criteria'"
        assert 2 <= len(q["criteria"]) <= 10, f"{name}'s criteria must have 2-10 levels"


def test_missing_answers_key_returns_error():
    with mock_ts({"model": "jev-1.13.0", "usage": {}}):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from fit_score import score_opportunity
            result = score_opportunity("title", "co", "jd", "")
    assert "error" in result
