import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest

from unittest.mock import patch, MagicMock


def test_detect_lane_data_ai():
    from discovery import detect_lane
    assert detect_lane("Head of Data & AI", "CDO CDAO analytics platform") == "Data/AI Arch"


def test_detect_lane_it_leadership():
    from discovery import detect_lane
    assert detect_lane("Leiter IT (m/w/d)", "CIO IT-Leitung Infrastruktur") == "IT Leadership"


def test_detect_lane_transformation():
    from discovery import detect_lane
    assert detect_lane("Head of Digital Transformation", "change ERP digitalisierung") == "Transformation"


def test_detect_lane_fallback():
    from discovery import detect_lane
    assert detect_lane("Sachbearbeiter Buchhaltung", "Buchführung Steuer") == "Other"


def test_verify_posting_open(requests_mock):
    requests_mock.get(
        "https://example.com/jobs/head-of-data",
        text='<html><body>Head of Data – Apply Now <a href="/apply">Apply</a></body></html>'
    )
    from discovery import verify_posting
    is_open, text = verify_posting("https://example.com/jobs/head-of-data")
    assert is_open is True
    assert "Head of Data" in text


def test_verify_posting_filled(requests_mock):
    requests_mock.get(
        "https://example.com/jobs/filled",
        text='<html><body>Position has been filled. Thank you for your interest.</body></html>'
    )
    from discovery import verify_posting
    is_open, text = verify_posting("https://example.com/jobs/filled")
    assert is_open is False
    assert text == ""


def test_verify_posting_network_error(requests_mock):
    import requests
    requests_mock.get("https://example.com/jobs/404", exc=requests.exceptions.ConnectionError)
    from discovery import verify_posting
    is_open, text = verify_posting("https://example.com/jobs/404")
    assert is_open is False
    assert text == ""


def test_verify_posting_empty_url():
    from discovery import verify_posting
    is_open, text = verify_posting("")
    assert is_open is False
    assert text == ""


def test_verify_posting_captures_text_capped_at_4000_chars(requests_mock):
    long_body = "Responsibility detail. " * 500  # well over 4000 chars
    requests_mock.get(
        "https://example.com/jobs/long",
        text=f'<html><body>{long_body}</body></html>'
    )
    from discovery import verify_posting
    is_open, text = verify_posting("https://example.com/jobs/long")
    assert is_open is True
    assert len(text) <= 4000


def test_search_portals_skips_existing_company():
    fake_result = {
        "uid": 200, "company": "ACME GmbH", "role": "Head of Data",
        "employer_url": "https://acme.de/jobs/head-of-data",
        "lane": "Data/AI Arch", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "jd text")):
                from discovery import search_portals
                rows, jd_cache = search_portals(
                    last_uid=199,
                    existing_companies={"acme gmbh"},
                    today="2026-09-22"
                )
    assert rows == []


def test_search_portals_returns_watchlist_row():
    fake_result = {
        "uid": 200, "company": "Neuland AG", "role": "CIO",
        "employer_url": "https://neuland.de/karriere/cio",
        "lane": "IT Leadership", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "jd text")):
                from discovery import search_portals
                rows, jd_cache = search_portals(
                    last_uid=199,
                    existing_companies=set(),
                    today="2026-09-22"
                )
    assert len(rows) == 1
    assert rows[0]["stage"] == "Watchlist"
    assert rows[0]["company"] == "Neuland AG"


def test_search_portals_returns_jd_cache_for_kept_rows():
    fake_result = {
        "uid": 200, "company": "Neuland AG", "role": "CIO",
        "employer_url": "https://neuland.de/karriere/cio",
        "lane": "IT Leadership", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "Full JD text here")):
                from discovery import search_portals
                rows, jd_cache = search_portals(
                    last_uid=199, existing_companies=set(), today="2026-09-22"
                )
    assert len(rows) == 1
    assert jd_cache[str(rows[0]["uid"])] == "Full JD text here"


def test_load_jd_cache_missing_file(tmp_path):
    from discovery import _load_jd_cache
    assert _load_jd_cache(str(tmp_path / "nope.json")) == {}


def test_load_jd_cache_corrupt_file(tmp_path):
    bad = tmp_path / "jd_cache.json"
    bad.write_text("{not valid json", encoding="utf-8")
    from discovery import _load_jd_cache
    assert _load_jd_cache(str(bad)) == {}


def test_load_jd_cache_valid_file(tmp_path):
    good = tmp_path / "jd_cache.json"
    good.write_text(json.dumps({"1": "existing text"}), encoding="utf-8")
    from discovery import _load_jd_cache
    assert _load_jd_cache(str(good)) == {"1": "existing text"}


def test_load_jd_cache_truncated_mid_utf8_char(tmp_path):
    # Simulates a sync-conflict truncation landing inside a multi-byte
    # UTF-8 character (e.g. the 2-byte "ü" in "Führung") rather than at a
    # JSON syntax boundary — must not raise UnicodeDecodeError.
    full_bytes = json.dumps({"1": "Führung"}, ensure_ascii=False).encode("utf-8")
    cut_point = full_bytes.index("ü".encode("utf-8")) + 1  # keep only the first of ü's 2 bytes
    truncated = tmp_path / "jd_cache.json"
    truncated.write_bytes(full_bytes[:cut_point])
    from discovery import _load_jd_cache
    assert _load_jd_cache(str(truncated)) == {}


def test_main_creates_jd_cache_when_missing(tmp_path, monkeypatch):
    cache_path = tmp_path / "jd_cache.json"  # does not exist yet
    out_csv = tmp_path / "out.csv"

    with patch("discovery.search_portals", return_value=([], {"5": "fresh text"})):
        monkeypatch.setattr(sys, "argv", [
            "discovery.py", "--uid-start", "1", "--out-csv", str(out_csv),
            "--today", "2026-09-22", "--jd-cache", str(cache_path),
        ])
        from discovery import main
        main()

    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"5": "fresh text"}


def test_main_merges_new_jd_cache_entries(tmp_path, monkeypatch):
    cache_path = tmp_path / "jd_cache.json"
    cache_path.write_text(json.dumps({"1": "existing text"}), encoding="utf-8")
    out_csv = tmp_path / "out.csv"

    with patch("discovery.search_portals", return_value=([], {"2": "new text"})):
        monkeypatch.setattr(sys, "argv", [
            "discovery.py", "--uid-start", "1", "--out-csv", str(out_csv),
            "--today", "2026-09-22", "--jd-cache", str(cache_path),
        ])
        from discovery import main
        main()

    merged = json.loads(cache_path.read_text(encoding="utf-8"))
    assert merged == {"1": "existing text", "2": "new text"}


def test_main_writes_out_csv_even_if_jd_cache_write_fails(tmp_path, monkeypatch):
    # A directory in place of the cache file makes the write raise
    # IsADirectoryError — the day's discovered rows must not be lost
    # just because the cache side-write failed.
    out_csv = tmp_path / "out.csv"
    bad_cache_dir = tmp_path / "cache_dir"
    bad_cache_dir.mkdir()

    fake_row = {"uid": 5, "company": "X", "role": "Y"}
    with patch("discovery.search_portals", return_value=([fake_row], {"5": "some text"})):
        monkeypatch.setattr(sys, "argv", [
            "discovery.py", "--uid-start", "1", "--out-csv", str(out_csv),
            "--today", "2026-09-22", "--jd-cache", str(bad_cache_dir),
        ])
        from discovery import main
        main()

    assert out_csv.exists()


def test_daily_slice_returns_n_items():
    from discovery import _daily_slice
    result = _daily_slice(["a", "b", "c", "d"], "2026-09-22", n=2)
    assert len(result) == 2


def test_daily_slice_rotates_across_days():
    from discovery import _daily_slice
    kws = ["a", "b", "c", "d"]
    day1 = _daily_slice(kws, "2026-09-22", n=2)
    day2 = _daily_slice(kws, "2026-09-23", n=2)
    assert day1 != day2


def test_daily_slice_wraps_when_n_exceeds_length():
    from discovery import _daily_slice
    result = _daily_slice(["a", "b", "c"], "2026-09-22", n=5)
    assert len(result) == 5
    assert set(result) <= {"a", "b", "c"}


def test_daily_keywords_combines_both_tiers():
    from discovery import _daily_keywords, _KEYWORDS_PRECISE, _KEYWORDS_BROAD
    combined = _daily_keywords("2026-09-22")
    assert len(combined) == 4
    assert any(k in _KEYWORDS_PRECISE for k in combined)
    assert any(k in _KEYWORDS_BROAD for k in combined)


def test_search_ba_sends_rotated_keywords(requests_mock):
    import discovery
    requests_mock.get(discovery._BA_URL, json={"ergebnisliste": []})
    from discovery import _search_ba, _daily_keywords
    _search_ba(100, "2026-09-22")
    sent_was = requests_mock.last_request.qs.get("was", [""])[0]
    expected_terms = [k.lower() for k in _daily_keywords("2026-09-22")]
    assert any(term in sent_was.lower() for term in expected_terms)


def test_search_ba_parses_v6_response_shape(requests_mock):
    # Real shape from the live v6 API (verified 2026-09-22): list is under
    # "ergebnisliste", title is "stellenangebotsTitel", employer is "firma",
    # and there is no "externeUrl" field — the public job page is built from
    # "referenznummer" instead.
    import discovery
    requests_mock.get(discovery._BA_URL, json={
        "ergebnisliste": [{
            "stellenangebotsTitel": "Head of Data & Platforms (m/w/d)",
            "firma": "Boehringer Ingelheim Pharma GmbH & Co. KG",
            "referenznummer": "20177-44442564-914-S",
        }]
    })
    from discovery import _search_ba
    results = _search_ba(100, "2026-09-22")
    assert len(results) == 1
    assert results[0]["role"] == "Head of Data & Platforms (m/w/d)"
    assert results[0]["company"] == "Boehringer Ingelheim Pharma GmbH & Co. KG"
    assert results[0]["employer_url"] == "https://www.arbeitsagentur.de/jobsuche/jobdetail/20177-44442564-914-S"


def test_search_ba_skips_result_missing_reference_number(requests_mock):
    import discovery
    requests_mock.get(discovery._BA_URL, json={
        "ergebnisliste": [{
            "stellenangebotsTitel": "Some Role", "firma": "Some GmbH", "referenznummer": "",
        }]
    })
    from discovery import _search_ba
    results = _search_ba(100, "2026-09-22")
    assert results == []


def _mock_ts(response_body):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("urllib.request.urlopen", return_value=mock_resp)


def test_tier_for_title_precise():
    from discovery import _tier_for_title
    assert _tier_for_title("Head of Data & AI") == "precise"


def test_tier_for_title_broad():
    from discovery import _tier_for_title
    assert _tier_for_title("Team Lead Data") == "broad"


def test_typesafe_lane_and_maturity_missing_api_key():
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["TYPESAFE_ENV_FILE"] = os.devnull  # ignore the real _system/.env
    with patch.dict(os.environ, env, clear=True):
        from discovery import _typesafe_lane_and_maturity
        result = _typesafe_lane_and_maturity("Team Lead Data", "ACME", "jd text")
    assert "error" in result


def test_typesafe_lane_and_maturity_returns_lane_when_equivalent():
    with _mock_ts({
        "model": "jev-1.13.0",
        "answers": {
            "lane_fit": {"type": "choice", "choice": "data_ai_arch"},
            "mature": {"type": "noul", "noul": 0.85},
        },
        "usage": {"input_tokens": 300, "output_tokens": 20},
    }):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from discovery import _typesafe_lane_and_maturity
            result = _typesafe_lane_and_maturity("Team Lead Data", "Kleinfirma GmbH", "Owns the data platform.")
    assert result == {"lane": "Data/AI Arch", "mature": True}


def test_typesafe_lane_and_maturity_not_equivalent():
    with _mock_ts({
        "model": "jev-1.13.0",
        "answers": {
            "lane_fit": {"type": "choice", "choice": "not_equivalent"},
            "mature": {"type": "noul", "noul": 0.9},
        },
        "usage": {"input_tokens": 300, "output_tokens": 20},
    }):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from discovery import _typesafe_lane_and_maturity
            result = _typesafe_lane_and_maturity("Junior Analyst", "ACME", "Entry-level data entry.")
    assert result["lane"] is None


def test_typesafe_lane_and_maturity_immature():
    with _mock_ts({
        "model": "jev-1.13.0",
        "answers": {
            "lane_fit": {"type": "choice", "choice": "data_ai_arch"},
            "mature": {"type": "noul", "noul": 0.2},
        },
        "usage": {"input_tokens": 300, "output_tokens": 20},
    }):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from discovery import _typesafe_lane_and_maturity
            result = _typesafe_lane_and_maturity("Manager Data", "Vagepost GmbH", "Join our team.")
    assert result["lane"] is None
    assert result["mature"] is False


def test_typesafe_lane_and_maturity_malformed_response_fails_closed():
    with _mock_ts({"unexpected": "shape"}):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from discovery import _typesafe_lane_and_maturity
            result = _typesafe_lane_and_maturity("Team Lead Data", "ACME", "jd text")
    assert "error" in result


def test_typesafe_lane_and_maturity_missing_answers_key_fails_closed():
    with _mock_ts({"model": "jev-1.13.0", "usage": {}}):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from discovery import _typesafe_lane_and_maturity
            result = _typesafe_lane_and_maturity("Team Lead Data", "ACME", "jd text")
    assert "error" in result


def test_search_portals_precise_tier_skips_typesafe_call():
    fake_result = {
        "uid": 200, "company": "ACME GmbH", "role": "Head of Data",
        "employer_url": "https://acme.de/jobs/head-of-data",
        "lane": "Data/AI Arch", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "jd text")):
                with patch("discovery._typesafe_lane_and_maturity") as mock_call:
                    from discovery import search_portals
                    rows, jd_cache = search_portals(199, set(), "2026-09-22")
    mock_call.assert_not_called()
    assert len(rows) == 1
    assert rows[0]["lane"] == "Data/AI Arch"


def test_search_portals_broad_tier_kept_when_equivalent():
    fake_result = {
        "uid": 200, "company": "Kleinfirma GmbH", "role": "Team Lead Data",
        "employer_url": "https://kleinfirma.de/jobs/team-lead-data",
        "lane": "Other", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "Owns the data platform.")):
                with patch("discovery._typesafe_lane_and_maturity",
                           return_value={"lane": "Data/AI Arch", "mature": True}):
                    from discovery import search_portals
                    rows, jd_cache = search_portals(199, set(), "2026-09-22")
    assert len(rows) == 1
    assert rows[0]["lane"] == "Data/AI Arch"


def test_search_portals_broad_tier_dropped_when_not_equivalent():
    fake_result = {
        "uid": 200, "company": "Kleinfirma GmbH", "role": "Team Lead Data",
        "employer_url": "https://kleinfirma.de/jobs/team-lead-data",
        "lane": "Other", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "Junior data entry role.")):
                with patch("discovery._typesafe_lane_and_maturity",
                           return_value={"lane": None, "mature": True}):
                    from discovery import search_portals
                    rows, jd_cache = search_portals(199, set(), "2026-09-22")
    assert rows == []


def test_search_portals_broad_tier_dropped_on_typesafe_error():
    fake_result = {
        "uid": 200, "company": "Errorco GmbH", "role": "Architect",
        "employer_url": "https://errorco.de/jobs/architect",
        "lane": "Other", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "Some JD text.")):
                with patch("discovery._typesafe_lane_and_maturity", return_value={"error": "timeout"}):
                    from discovery import search_portals
                    rows, jd_cache = search_portals(199, set(), "2026-09-22")
    assert rows == []


def test_search_portals_tracks_typesafe_error_count():
    fake_result = {
        "uid": 200, "company": "Errorco GmbH", "role": "Architect",
        "employer_url": "https://errorco.de/jobs/architect",
        "lane": "Other", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "Some JD text.")):
                with patch("discovery._typesafe_lane_and_maturity", return_value={"error": "timeout"}):
                    from discovery import search_portals
                    stats = {}
                    rows, jd_cache = search_portals(199, set(), "2026-09-22", stats=stats)
    assert stats["typesafe_errors"] == 1
    assert stats["rejected"] == 0


def test_search_portals_tracks_rejected_count():
    fake_result = {
        "uid": 200, "company": "Kleinfirma GmbH", "role": "Team Lead Data",
        "employer_url": "https://kleinfirma.de/jobs/team-lead-data",
        "lane": "Other", "salary_fit": "mid", "location": "Hamburg"
    }
    with patch("discovery._search_eures", return_value=[fake_result]):
        with patch("discovery._search_ba", return_value=[]):
            with patch("discovery.verify_posting", return_value=(True, "Junior data entry role.")):
                with patch("discovery._typesafe_lane_and_maturity",
                           return_value={"lane": None, "mature": True}):
                    from discovery import search_portals
                    stats = {}
                    rows, jd_cache = search_portals(199, set(), "2026-09-22", stats=stats)
    assert stats["typesafe_errors"] == 0
    assert stats["rejected"] == 1


def test_search_portals_stats_optional_for_backward_compatibility():
    from discovery import search_portals
    with patch("discovery._search_eures", return_value=[]):
        with patch("discovery._search_ba", return_value=[]):
            rows, jd_cache = search_portals(199, set(), "2026-09-22")  # no stats= arg
    assert rows == []


def test_main_reports_typesafe_error_count(tmp_path, monkeypatch, capsys):
    out_csv = tmp_path / "out.csv"

    def fake_search_portals(last_uid, existing_companies, today, stats=None):
        if stats is not None:
            stats["typesafe_errors"] = 3
            stats["rejected"] = 1
        return [], {}

    with patch("discovery.search_portals", side_effect=fake_search_portals):
        monkeypatch.setattr(sys, "argv", [
            "discovery.py", "--uid-start", "1", "--out-csv", str(out_csv),
            "--today", "2026-09-22", "--jd-cache", str(tmp_path / "jd_cache.json"),
        ])
        from discovery import main
        main()

    captured = capsys.readouterr()
    assert "3" in captured.out
    assert "TypeSafe" in captured.out


def test_discovery_writes_run_stamp_even_when_nothing_new(tmp_path, monkeypatch):
    import discovery
    monkeypatch.setattr(discovery, "search_portals", lambda *a, **k: ([], {}))
    monkeypatch.setattr(sys, "argv", ["discovery.py", "--uid-start", "1", "--out-csv", str(tmp_path / "o.csv"),
                                      "--jd-cache", str(tmp_path / "jd_cache.json"), "--today", "2026-09-25"])
    discovery.main()
    stamp = json.loads((tmp_path / "discovery_last.json").read_text(encoding="utf-8"))
    assert stamp["new"] == 0 and stamp["day"] == "2026-09-25" and stamp["ts"]
