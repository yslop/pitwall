"""Service health checks: thresholds, failure handling, history, end-to-end run()."""
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import health as H  # noqa: E402

NOW = datetime(2026, 9, 25, 9, 0, 0)
TODAY = "2026-09-25"


def hours_ago(h):
    return NOW - timedelta(hours=h)


def status(check):
    return check["status"]


# ---- freshness and discovery --------------------------------------------------------------------
def test_run_freshness_thresholds():
    assert status(H.check_run_freshness(NOW, None)) == H.OK
    assert status(H.check_run_freshness(NOW, hours_ago(24))) == H.OK
    assert status(H.check_run_freshness(NOW, hours_ago(36))) == H.OK
    assert status(H.check_run_freshness(NOW, hours_ago(48))) == H.WATCH
    assert status(H.check_run_freshness(NOW, hours_ago(61))) == H.ACT


def test_discovery_thresholds():
    assert status(H.check_discovery(NOW, None)) == H.WATCH
    assert status(H.check_discovery(NOW, hours_ago(2))) == H.OK
    assert status(H.check_discovery(NOW, hours_ago(50))) == H.WATCH
    assert status(H.check_discovery(NOW, hours_ago(100))) == H.ACT


# ---- security -----------------------------------------------------------------------------------
def test_security_flags_open_env_and_foreign_ledger_fields():
    assert status(H.check_security(0o600, set())) == H.OK
    assert status(H.check_security(None, set())) == H.OK
    open_env = H.check_security(0o644, set())
    assert status(open_env) == H.ACT and "chmod 600" in open_env["reason"]
    leaky = H.check_security(0o600, {"subject"})
    assert status(leaky) == H.ACT and "subject" in leaky["reason"]


# ---- capacity -----------------------------------------------------------------------------------
def usage(spike=False, used=0.0, ceiling=5.0, tokens=1000):
    return {"spike": spike, "why": "9× the median" if spike else "within normal range",
            "month": {"input_tokens": tokens, "cost_usd": used * (ceiling or 0), "ceiling_usd": ceiling,
                      "ceiling_used": used if ceiling else None}}


def test_capacity_thresholds():
    assert status(H.check_capacity(usage(used=0.1))) == H.OK
    assert status(H.check_capacity(usage(used=0.8))) == H.WATCH
    assert status(H.check_capacity(usage(used=1.0))) == H.ACT
    assert status(H.check_capacity(usage(spike=True))) == H.ACT
    assert status(H.check_capacity(usage(ceiling=None))) == H.OK


def test_capacity_unavailable_is_act_not_missing():
    c = H.check_capacity(None)
    assert status(c) == H.ACT and "unavailable" in c["reason"]


# ---- data quality -------------------------------------------------------------------------------
def test_data_quality_levels_and_failure():
    assert status(H.check_data_quality({"errors": 0, "warnings": 0})) == H.OK
    assert status(H.check_data_quality({"errors": 0, "warnings": 5})) == H.WATCH
    assert status(H.check_data_quality({"errors": 1, "warnings": 0})) == H.ACT
    failed = H.check_data_quality({"error": "boom"})
    assert status(failed) == H.ACT and "boom" in failed["reason"]
    assert status(H.check_data_quality(None)) == H.ACT


# ---- follow-through and value stream ------------------------------------------------------------
def row(uid, stage="Applied", due="", idle="0"):
    return {"uid": str(uid), "stage": stage, "due": due, "days_idle": idle}


def test_follow_through_counts_only_open_overdue_rows():
    rows = [row(1, due="2026-09-01"), row(2, due="2026-09-30"), row(3, "Closed", due="2026-01-01"), row(4)]
    c = H.check_follow_through(rows, TODAY)
    assert status(c) == H.WATCH and "1 overdue" in c["reason"]
    many = [row(i, due="2026-09-01") for i in range(4)]
    assert status(H.check_follow_through(many, TODAY)) == H.ACT
    assert status(H.check_follow_through([row(1)], TODAY)) == H.OK


def test_value_stream_thresholds():
    assert status(H.check_value_stream([row(1, idle="44")])) == H.OK
    assert status(H.check_value_stream([row(1, idle="46")])) == H.WATCH
    assert status(H.check_value_stream([row(1, "Interviewing", idle="61")])) == H.ACT
    assert status(H.check_value_stream([row(1, "Closed", idle="200")])) == H.OK
    assert status(H.check_value_stream([row(1, idle="")])) == H.OK          # blank idle is not stale


# ---- profile freshness --------------------------------------------------------------------------
def test_profile_freshness_thresholds():
    d = date(2026, 9, 25)
    assert status(H.check_profile_freshness(None, TODAY)) == H.WATCH
    assert status(H.check_profile_freshness(d - timedelta(days=30), TODAY)) == H.OK
    assert status(H.check_profile_freshness(d - timedelta(days=31), TODAY)) == H.WATCH
    assert status(H.check_profile_freshness(d - timedelta(days=46), TODAY)) == H.ACT


# ---- problems from history ----------------------------------------------------------------------
def hist(day, **st):
    return {"day": day, "status": st}


def test_problem_needs_three_consecutive_non_ok_days():
    checks = [{"id": "capacity", "status": H.WATCH}, {"id": "security", "status": H.OK}]
    two_bad = [hist("2026-09-23", capacity=H.WATCH), hist("2026-09-24", capacity=H.ACT)]
    assert H.find_problems(two_bad, checks, TODAY) == ["capacity"]
    broken = [hist("2026-09-23", capacity=H.OK), hist("2026-09-24", capacity=H.ACT)]
    assert H.find_problems(broken, checks, TODAY) == []
    assert H.find_problems([hist("2026-09-24", capacity=H.ACT)], checks, TODAY) == []   # too little history


def test_problems_check_levels():
    assert status(H.check_problems([])) == H.OK
    assert status(H.check_problems(["a", "b"])) == H.WATCH
    assert status(H.check_problems(["a", "b", "c"])) == H.ACT


def test_history_keeps_sixty_days_and_replaces_today():
    old = [hist((date(2026, 9, 25) - timedelta(days=n)).isoformat(), x=H.OK) for n in range(80)]
    out = H.update_history(old, TODAY, [{"id": "x", "status": H.ACT}])
    days = [h["day"] for h in out]
    assert len(out) == 60 and days[-1] == TODAY and days == sorted(days)
    assert out[-1]["status"] == {"x": H.ACT}
    assert len([h for h in out if h["day"] == TODAY]) == 1


# ---- API contract (spec 2026-09-27-api-contract-design.md) ----------------------------------------
def contract(h=2, ts_ok=True, ba_ok=True, ts_problems=None):
    return {"ts": hours_ago(h).isoformat(timespec="seconds"),
            "typesafe": {"ok": ts_ok, "problems": ts_problems or ([] if ts_ok else ["missing 'answers'"])},
            "ba": {"ok": ba_ok, "problems": [] if ba_ok else ["HTTP 403"]}}


def test_api_contract_levels():
    assert status(H.check_api_contract(NOW, None)) == H.WATCH
    assert status(H.check_api_contract(NOW, contract())) == H.OK
    assert status(H.check_api_contract(NOW, contract(h=48))) == H.WATCH
    assert status(H.check_api_contract(NOW, contract(h=61))) == H.ACT
    assert status(H.check_api_contract(NOW, contract(ts_ok=None, ts_problems=["TYPESAFE_API_KEY not set"]))) == H.WATCH
    broken = H.check_api_contract(NOW, contract(ts_ok=False, ba_ok=False))
    assert status(broken) == H.ACT and "TypeSafe" in broken["reason"] and "BA" in broken["reason"]


def test_api_contract_garbage_state_is_act_not_crash():
    assert status(H.check_api_contract(NOW, {"ts": "yesterday"})) == H.ACT


# ---- compute_health -----------------------------------------------------------------------------
def inputs(**over):
    base = dict(now=NOW, rows=[row(1)], prev_run=hours_ago(24), discovery_ts=hours_ago(2), discovery_new=0,
                career={"errors": 0, "warnings": 0}, usage=usage(used=0.1), env_mode=0o600,
                ledger_bad_keys=set(), profile_reviewed=date(2026, 9, 20), history=[], deploy=None,
                contract=contract())
    base.update(over)
    return base


def test_compute_health_all_ok_has_ten_checks():
    h = H.compute_health(**inputs())
    assert h["overall"] == H.OK and len(h["checks"]) == 10
    assert [c["group"] for c in h["checks"]].count("warranty") == 5
    assert h["incidents"] == [] and h["today"] == TODAY


def test_run_gap_becomes_incident_and_overall_act():
    h = H.compute_health(**inputs(prev_run=hours_ago(100)))
    assert h["overall"] == H.ACT
    assert len(h["incidents"]) == 1 and h["incidents"][0].startswith("Run gap")


def test_every_check_has_reason_and_target():
    h = H.compute_health(**inputs(usage=None, career=None))
    for c in h["checks"]:
        assert c["reason"] and c["target"] and c["status"] in (H.OK, H.WATCH, H.ACT)


# ---- end to end on disk -------------------------------------------------------------------------
def write_pipeline(path):
    path.write_text("uid,company,stage,due,days_idle\n1,Acme,Applied,2026-09-01,10\n", encoding="utf-8")


def test_run_writes_health_history_and_last_run(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "llm_calls.jsonl").write_text(
        json.dumps({"backend": "jev", "cost_usd": 0.00004, "input_tokens": 900, "model": "m", "task": "t",
                    "ts": "2026-09-25T07:00:00+00:00"}) + "\n", encoding="utf-8")
    (tmp_path / "capability_profile.md").write_text("reviewed: 2026-09-20\n", encoding="utf-8")
    h = H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a: {"errors": 0, "warnings": 2})
    assert json.loads((tmp_path / "health.json").read_text(encoding="utf-8"))["overall"] == h["overall"]
    by_id = {c["id"]: c for c in h["checks"]}
    assert by_id["follow_through"]["status"] == H.WATCH          # uid 1 is overdue
    assert by_id["data_quality"]["status"] == H.WATCH
    assert by_id["profile"]["status"] == H.OK
    assert by_id["security"]["status"] == H.OK
    history = json.loads((tmp_path / "health_history.json").read_text(encoding="utf-8"))
    assert history[-1]["day"] == TODAY
    assert json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))["ts"] == "2026-09-25T09:00:00"


def test_run_survives_missing_optional_files(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    h = H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a: {"error": "no script"})
    by_id = {c["id"]: c for c in h["checks"]}
    assert by_id["data_quality"]["status"] == H.ACT
    assert by_id["profile"]["status"] == H.WATCH and by_id["discovery"]["status"] == H.WATCH
    assert len(h["checks"]) == 17   # ten service checks plus the seven intel warranty checks


def test_ledger_with_message_text_field_is_flagged(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "llm_calls.jsonl").write_text(
        json.dumps({"backend": "jev", "input_tokens": 5, "ts": "2026-09-25T07:00:00+00:00", "subject": "Hello"}) + "\n",
        encoding="utf-8")
    h = H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a: {"errors": 0, "warnings": 0})
    sec = next(c for c in h["checks"] if c["id"] == "security")
    assert sec["status"] == H.ACT and "subject" in sec["reason"]


def test_career_counts_parses_real_checker_output(tmp_path):
    system_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(system_dir, "career_check.py")):
        return
    write_pipeline(tmp_path / "pipeline.csv")
    res = H.career_counts(system_dir, str(tmp_path / "pipeline.csv"), TODAY)
    assert ("errors" in res and "warnings" in res) or "error" in res


# ---- review focus: awkward inputs ---------------------------------------------------------------
def test_garbage_due_and_idle_values_never_crash_and_are_not_counted():
    rows = [row(1, due="TBD", idle="n/a"), row(2, due="30.09.2026", idle="—"), row(3, due=None, idle=None)]
    assert status(H.check_follow_through(rows, TODAY)) == H.OK
    assert status(H.check_value_stream(rows)) == H.OK


def test_unreadable_ledger_line_is_flagged_not_ignored(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "llm_calls.jsonl").write_text("this is not json\n", encoding="utf-8")
    h = H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a: {"errors": 0, "warnings": 0})
    sec = next(c for c in h["checks"] if c["id"] == "security")
    assert sec["status"] == H.ACT and "unreadable" in sec["reason"]


def test_main_returns_1_when_pipeline_is_missing(tmp_path):
    assert H.main(["--data", str(tmp_path / "missing.csv"), "--system-dir", str(tmp_path), "--quiet"]) == 1


def test_second_run_on_the_same_day_replaces_history_entry(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    runner = lambda *a: {"errors": 0, "warnings": 0}   # noqa: E731
    H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=runner)
    H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW + timedelta(hours=2), career_runner=runner)
    history = json.loads((tmp_path / "health_history.json").read_text(encoding="utf-8"))
    assert [h["day"] for h in history] == [TODAY]


# ---- final review, fix pass ---------------------------------------------------------------------
def test_due_dates_are_parsed_not_string_compared():
    rows = [row(1, due="01.10.2026"), row(2, due="15.12.2026"), row(3, due="20.10.2026"), row(4, due=" 2026-10-30")]
    assert status(H.check_follow_through(rows, TODAY)) == H.OK
    assert status(H.check_follow_through([row(5, due=" 2026-09-01")], TODAY)) == H.WATCH     # padded ISO still counts


def test_timestamps_with_offset_or_z_become_naive_local():
    for s in ("2026-09-25T07:00:00+02:00", "2026-09-25T05:00:00Z"):
        assert H.parse_ts(s).tzinfo is None
    assert H.parse_ts("2026-09-25T07:00:00").hour == 7


def test_offset_timestamp_in_last_run_does_not_crash_later_runs(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    (tmp_path / "last_run.json").write_text('{"ts": "2026-09-24T07:00:00+02:00"}', encoding="utf-8")
    (tmp_path / "jd_cache.json").write_text("{}", encoding="utf-8")
    h = H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a: {"errors": 0, "warnings": 0})
    assert len(h["checks"]) == 17


def test_main_accepts_now_with_offset_and_z(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    for s in ("2026-09-25T07:00:00+02:00", "2026-09-25T05:00:00Z"):
        assert H.main(["--data", str(tmp_path / "pipeline.csv"), "--system-dir", str(tmp_path), "--now", s, "--quiet"]) == 0


def test_discovery_uses_run_stamp_not_cache_mtime(tmp_path):
    write_pipeline(tmp_path / "pipeline.csv")
    (tmp_path / "discovery_last.json").write_text(json.dumps({"ts": "2026-09-25T06:00:00", "day": TODAY, "new": 0}), encoding="utf-8")
    cache = tmp_path / "jd_cache.json"
    cache.write_text("{}", encoding="utf-8")
    old = (NOW - timedelta(days=5)).timestamp()
    os.utime(cache, (old, old))                                   # quiet days: nothing new, cache untouched
    h = H.run(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a: {"errors": 0, "warnings": 0})
    disc = next(c for c in h["checks"] if c["id"] == "discovery")
    assert disc["status"] == H.OK and "0 new" in disc["reason"]


# ---- the last real run comes from events.csv, not from any health call -------------------------------------------------
def write_events(system, *dates):
    body = "datum,fenster_von,fenster_bis,threads_gesichtet,zeilen_geaendert,neue_uids,unklar\n" + "".join("%s,%s,%s,3,0,0,0\n" % (d, d, d) for d in dates)
    (system / "events.csv").write_text(body, encoding="utf-8")


def test_the_last_real_run_is_the_newest_valid_events_row_at_the_end_of_that_day(tmp_path):
    write_events(tmp_path, "2026-09-23", "2026-09-24")
    assert H.last_events_run(str(tmp_path), NOW) == datetime(2026, 9, 24, 23, 59, 59)
    (tmp_path / "events.csv").write_text("datum,x\nnicht ein Datum,1\n2026-09-22,1\n", encoding="utf-8")
    assert H.last_events_run(str(tmp_path), NOW) == datetime(2026, 9, 22, 23, 59, 59)
    write_events(tmp_path, "2026-09-30")
    assert H.last_events_run(str(tmp_path), NOW) == NOW                                   # a date in the future is clamped to now
    (tmp_path / "events.csv").write_bytes("datum\nüü\n".encode("cp1252"))
    assert H.last_events_run(str(tmp_path), NOW) is None
    assert H.last_events_run(str(tmp_path / "nope"), NOW) is None


def test_manual_health_calls_no_longer_hide_a_missed_scheduled_run(tmp_path):
    write_events(tmp_path, "2026-09-20")                                                  # the last real run was five days ago
    (tmp_path / "last_run.json").write_text(json.dumps({"ts": hours_ago(0.1).isoformat(timespec="seconds")}), encoding="utf-8")   # a manual call just now
    (tmp_path / "pipeline.csv").write_text("uid,company,role,stage\n1,A,B,Watchlist\n", encoding="utf-8")
    data = H.gather(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a, **k: {})
    assert data["prev_run"] == datetime(2026, 9, 20, 23, 59, 59)
    assert status(H.check_run_freshness(NOW, data["prev_run"])) == H.ACT
    (tmp_path / "events.csv").write_text("datum\nkaputt", encoding="utf-8")               # no usable events: fall back to the last health call
    data = H.gather(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a, **k: {})
    assert data["prev_run"] == hours_ago(0.1).replace(microsecond=0)


# ---- intel warranty (owner decision 2026-10-02) ---------------------------------------------------------
def intel_pos(**over):
    p = {"uid": "1", "company": "Acme", "stage": "Interviewing", "due": None, "folder": True, "docs": [], "inputs": [], "unacked": [], "orders": []}
    p.update(over)
    return p


def test_intel_warranty_checks_join_the_health_when_a_snapshot_is_given():
    h = H.compute_health(**inputs(intel=[intel_pos()]))
    ids = [c["id"] for c in h["checks"]]
    assert all(i in ids for i in ("intel_stage_doc", "intel_fresh", "intel_orders", "intel_inputs")) and len(h["checks"]) == 17
    assert h["overall"] == H.ACT and h["checks"][ids.index("intel_stage_doc")]["group"] == "warranty"      # a process in conversation without document or order


def test_without_a_snapshot_the_health_is_unchanged():
    assert len(H.compute_health(**inputs())["checks"]) == 10


def test_a_snapshot_that_could_not_be_built_is_act_not_silent():
    h = H.compute_health(**inputs(intel={"error": "OSError: disk"}))
    c = [c for c in h["checks"] if c["id"] == "intel_warranty"][0]
    assert c["status"] == H.ACT and "OSError: disk" in c["reason"] and len(h["checks"]) == 11


def test_gather_builds_the_intel_snapshot_from_the_pipeline(tmp_path):
    (tmp_path / "pipeline.csv").write_text("uid,company,role,stage,folder_id,due\n7,Acme,Head,Interviewing,,2026-10-04\n8,Zed,R,Applied,,\n", encoding="utf-8")
    data = H.gather(str(tmp_path), str(tmp_path / "pipeline.csv"), NOW, career_runner=lambda *a, **k: {})
    assert isinstance(data["intel"], list) and [p["uid"] for p in data["intel"]] == ["7"] and data["intel"][0]["folder"] is False
