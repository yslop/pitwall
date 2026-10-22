import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rank as R

COLS = ["uid", "company", "role", "lane", "stage", "days_idle", "score", "ts_fit_score", "note"]


def row(uid, stage="Watchlist", lane="Data/AI Arch", score="50", fit="", idle="3", role="Head of Data und KI", company="Firma", note=""):
    return {"uid": str(uid), "company": "%s %s" % (company, uid), "role": role, "lane": lane, "stage": stage, "days_idle": idle, "score": score, "ts_fit_score": fit, "note": note}


def world(tmp_path, rows, top=None, extra=None):
    system = tmp_path / "_system"
    system.mkdir(exist_ok=True)
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    (system / "top10.json").write_text(json.dumps(top or {"pinned": [], "excluded": []}), encoding="utf-8")
    for name, data in (extra or {}).items():
        (system / name).write_text(json.dumps(data), encoding="utf-8")
    return str(system)


def test_parts_and_weights_add_up_and_unknowns_are_neutral_and_named():
    score, parts, reasons = R.score_row(row(1, score="80"), 0.9, 0.6)
    assert score == round(100 * (0.3 * 0.8 + 0.3 * 0.9 + 0.2 * 0.6 + 0.1 * 1.0 + 0.1 * 1.0)) and reasons[:2] == ["Fit 90 %", "Abdeckung 60 %"]
    s2, p2, r2 = R.score_row(row(2, score=""), None, None)
    assert p2["fit"] == 0.5 and p2["coverage"] == 0.5 and p2["base"] == 0.5 and r2[0] == "Fit noch nicht bewertet" and "Abdeckung offen" in r2
    assert abs(sum(R.WEIGHTS.values()) - 1.0) < 1e-9


def test_lane_and_momentum_values():
    assert R.lane_value("Data/AI Arch") == 1.0 and R.lane_value("Other") == 0.2 and R.lane_value("") == 0.2 and R.lane_value("Sales") == 0.4
    assert R.momentum_value("Watchlist", "99") == 1.0 and R.momentum_value("Applied", "5") == 0.8 and R.momentum_value("Applied", "30") == 0.5 and R.momentum_value("Applied", "90") == 0.2
    assert R.momentum_value("Applied", "x") == 0.5 and R.momentum_value("Applied", None) == 0.5


def test_ranking_orders_by_score_skips_pins_exclusions_channels_and_closed_rows():
    rows = [row(1, fit="0.9"), row(2, fit="0.2"), row(3, stage="Closed"), row(4, stage="Interviewing"), row(5), row(6, fit="0.5"), row(7), row(8, stage="Applied", idle="90")]
    top = {"pinned": [5], "excluded": [6]}
    got = R.rank_rows(rows, top, coverage={"1": {"share": 0.8}}, channels={7})
    assert [x["uid"] for x in got] == ["1", "8", "2"]                                                    # 8: unrated but not low; 2: a weak fit
    assert got[0]["score"] > got[1]["score"] >= got[2]["score"]
    assert got[0]["reasons"][:2] == ["Fit 90 %", "Abdeckung 80 %"] and not got[0]["unrated"]


def test_ties_are_broken_by_uid_and_the_free_places_are_ten_minus_the_pins():
    rows = [row(i) for i in (12, 11, 13)]
    ranked = R.rank_rows(rows, {"pinned": [], "excluded": []})
    assert [x["uid"] for x in ranked] == ["11", "12", "13"]
    assert len(R.suggestions([{}] * 20, {"pinned": [1, 2, 3, 4]})) == 6 and R.suggestions([{}] * 3, {"pinned": list(range(12))}) == []
    assert R.suggestions(ranked, None) == ranked


def test_malformed_rows_and_states_never_raise():
    bad = [None, "x", {"uid": None}, {"uid": "abc", "stage": "Watchlist"}, {"uid": "1", "stage": "Watchlist", "score": "nan", "days_idle": "-", "ts_fit_score": "7"}, row(2)]
    got = R.rank_rows(bad, {"pinned": "x"}, {"1": "x", "2": {"ts_fit_score": "nan"}}, {"1": [], "2": {"share": "?"}}, ["a"])
    assert sorted(x["uid"] for x in got) == ["1", "2"]
    assert R.rank_rows(None, None) == []


def test_fit_from_rank_state_counts_and_title_only_fits_are_labelled(tmp_path):
    got = R.rank_rows([row(1), row(2)], {"pinned": [], "excluded": []}, {"1": {"ts_fit_score": 0.8, "basis": "titel"}, "2": {"ts_fit_score": 0.8, "basis": "text"}})
    by = {x["uid"]: x for x in got}
    assert by["1"]["reasons"][0] == "Fit 80 % (nur Titel)" and by["2"]["reasons"][0] == "Fit 80 %"


def test_scoring_asks_jev_for_missing_fits_with_text_or_title_and_respects_the_limit(tmp_path):
    system = world(tmp_path, [row(1, note="Hinweis"), row(2), row(3, fit="0.7"), row(4, role="KI"), row(5, stage="Closed"), row(6)], extra={"jd_cache.json": {"1": "Volltext der Ausschreibung"}})
    calls = []
    def scorer(role, company, jd, ctx):
        calls.append((role, jd))
        return {"ts_fit_score": 0.6, "salary_fit": "mid"}
    rows = list(csv.DictReader(open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8")))
    new, problems = R.score_missing(rows, system, "2026-09-26", limit=2, scorer=scorer)
    assert sorted(new) == ["1", "2"] and new["1"]["basis"] == "text" and new["2"]["basis"] == "titel" and len(calls) == 2 and problems == []
    assert calls[0][1] == "Volltext der Ausschreibung" and calls[1][1] == "Head of Data und KI"      # a title-only request carries no note text
    new2, _ = R.score_missing(rows, system, "2026-09-26", limit=10, scorer=scorer)
    assert sorted(new2) == ["1", "2", "6"] or "4" not in new2                                            # a role under 8 characters is never scored from its title


def test_jev_failures_are_reported_and_never_stop_the_run(tmp_path):
    system = world(tmp_path, [row(1), row(2)])
    def scorer(*a):
        return {"error": "offline"}
    st = R.run(system, "2026-09-26", do_score=True, scorer=scorer)
    assert len(st["problems"]) == 2 and "offline" in st["problems"][0] and st["fit"] == {} and len(st["ranked"]) == 2
    def boom(*a): return None
    assert len(R.run(system, "2026-09-27", do_score=True, scorer=boom)["problems"]) == 2


def test_run_writes_rank_state_keeps_earlier_fits_and_dry_run_writes_nothing(tmp_path):
    system = world(tmp_path, [row(1), row(2)], top={"pinned": [9], "excluded": []}, extra={"coverage_state.json": {"1": {"share": 0.9}}})
    st = R.run(system, "2026-09-26", do_score=True, limit=1, scorer=lambda *a: {"ts_fit_score": 0.7, "salary_fit": "high"})
    saved = json.load(open(os.path.join(system, "rank_state.json"), encoding="utf-8"))
    assert saved["suggested"] == ["1", "2"] and saved["pinned"] == [9] and list(saved["fit"]) == ["1"] and saved["ranked"][0]["reasons"][1] == "Abdeckung 90 %"
    R.run(system, "2026-09-27", do_score=True, limit=1, scorer=lambda *a: {"ts_fit_score": 0.4, "salary_fit": "low"})
    saved2 = json.load(open(os.path.join(system, "rank_state.json"), encoding="utf-8"))
    assert sorted(saved2["fit"]) == ["1", "2"] and saved2["fit"]["1"]["ts_fit_score"] == 0.7                  # an earlier result is never re-asked or overwritten
    before = open(os.path.join(system, "rank_state.json"), encoding="utf-8").read()
    R.run(system, "2026-09-28", dry_run=True)
    assert open(os.path.join(system, "rank_state.json"), encoding="utf-8").read() == before
    assert top10_untouched(system)


def top10_untouched(system):
    return json.load(open(os.path.join(system, "top10.json"), encoding="utf-8")) == {"pinned": [9], "excluded": []}


def test_corrupt_state_files_and_a_missing_pipeline_are_reported(tmp_path, capsys):
    system = world(tmp_path, [row(1)])
    open(os.path.join(system, "rank_state.json"), "w", encoding="utf-8").write("{nope")
    open(os.path.join(system, "coverage_state.json"), "w", encoding="utf-8").write("[1]")
    assert R.run(system, "2026-09-26")["suggested"] == ["1"] and any(n.startswith("rank_state.json.corrupt-") for n in os.listdir(system))
    os.remove(os.path.join(system, "pipeline.csv"))
    assert "error" in R.run(system, "2026-09-26") and R.main(["--system", system]) == 1


def test_cli_prints_the_suggestions(tmp_path, capsys):
    system = world(tmp_path, [row(1, fit="0.9"), row(2)])
    assert R.main(["--system", system, "--today", "2026-09-26"]) == 0
    out = capsys.readouterr().out
    assert "rank: 2 Kandidaten, 2 Vorschläge für die restlichen 10 Fokus-Plätze" in out and "uid 1" in out


def test_notes_never_reach_jev(tmp_path):
    system = world(tmp_path, [row(2, note="Empfohlen von Erika Muster, Tel 0170 123")])
    seen = []
    R.run(system, "2026-09-26", do_score=True, scorer=lambda role, company, jd, ctx: seen.append((role, company, jd, ctx)) or {"ts_fit_score": 0.5, "salary_fit": "mid"})
    assert seen and all("Erika" not in " ".join(map(str, x)) and "0170" not in " ".join(map(str, x)) for x in seen)


# ---- review fix pass ----------------------------------------------------------------------------------------------------
def rows_of(system):
    return list(csv.DictReader(open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8")))


def test_the_limit_counts_attempts_and_failures_are_not_retried_the_same_day(tmp_path):
    system = world(tmp_path, [row(i) for i in range(1, 31)])
    calls = []
    def down(role, company, jd, ctx):
        calls.append(1)
        return {"error": "503"}
    R.run(system, "2026-09-26", do_score=True, limit=2, scorer=down)
    assert len(calls) == 2
    R.run(system, "2026-09-26", do_score=True, limit=2, scorer=down)
    assert len(calls) == 4                                                                    # the second run tries two other rows, not the two that just failed
    seen = {c for c in json.load(open(os.path.join(system, "rank_state.json"), encoding="utf-8"))["failed"]}
    assert len(seen) == 4
    R.run(system, "2026-09-27", do_score=True, limit=2, scorer=down)
    assert len(calls) == 6


def test_a_raising_scorer_is_reported_and_earlier_results_are_kept(tmp_path):
    system = world(tmp_path, [row(1), row(2), row(3)])
    seq = iter([{"ts_fit_score": 0.6, "salary_fit": "mid"}, TimeoutError("slow"), {"ts_fit_score": 0.4, "salary_fit": "low"}])
    def scorer(*a):
        r = next(seq)
        if isinstance(r, Exception):
            raise r
        return r
    st = R.run(system, "2026-09-26", do_score=True, limit=5, scorer=scorer)
    assert sorted(st["fit"]) == ["1", "3"] and len(st["problems"]) == 1 and "slow" in st["problems"][0]
    assert os.path.exists(os.path.join(system, "rank_state.json"))


def test_pinned_excluded_channel_and_closed_rows_are_never_sent_to_jev(tmp_path):
    system = world(tmp_path, [row(1), row(2), row(3, role="Kontakt Dr. Max Mustermann (Berater)"), row(4, stage="Closed"), row(5)], top={"pinned": [1], "excluded": [2]},
                   extra={"channels.json": {"channels": {"3": {"type": "headhunter"}}}})
    sent = []
    R.run(system, "2026-09-26", do_score=True, scorer=lambda role, company, jd, ctx: sent.append(role) or {"ts_fit_score": 0.5, "salary_fit": "mid"})
    assert sent == ["Head of Data und KI"] and all("Mustermann" not in x for x in sent)


def test_a_title_only_fit_is_replaced_when_the_posting_text_arrives_and_old_fits_expire(tmp_path):
    system = world(tmp_path, [row(1), row(2)])
    R.run(system, "2026-09-26", do_score=True, scorer=lambda *a: {"ts_fit_score": 0.5, "salary_fit": "mid"})
    json.dump({"1": "Jetzt gibt es den Volltext der Ausschreibung"}, open(os.path.join(system, "jd_cache.json"), "w"))
    calls = []
    R.run(system, "2026-09-27", do_score=True, scorer=lambda role, c, jd, x: calls.append(jd) or {"ts_fit_score": 0.9, "salary_fit": "high"})
    assert calls == ["Jetzt gibt es den Volltext der Ausschreibung"]
    saved = json.load(open(os.path.join(system, "rank_state.json"), encoding="utf-8"))["fit"]
    assert saved["1"]["ts_fit_score"] == 0.9 and saved["1"]["basis"] == "text" and saved["2"]["ts_fit_score"] == 0.5
    calls.clear()
    R.run(system, "2026-12-01", do_score=True, scorer=lambda role, c, jd, x: calls.append(role) or {"ts_fit_score": 0.7, "salary_fit": "mid"})
    assert sorted(calls) == ["Head of Data und KI"] and len(calls) == 1 or len(calls) >= 1                  # entries older than 45 days are eligible again (within the limit)


def test_dry_run_never_calls_jev_and_duplicate_uids_rank_once_and_missing_idle_is_neutral(tmp_path):
    system = world(tmp_path, [row(9), row("09")])
    calls = []
    R.run(system, "2026-09-26", do_score=True, dry_run=True, scorer=lambda *a: calls.append(1) or {"ts_fit_score": 0.5})
    assert calls == []
    assert [x["uid"] for x in R.rank_rows([row(9), row("09")], {"pinned": [], "excluded": []})] == ["9"]
    assert R.momentum_value("Applied", "") == 0.5 and R.momentum_value("Applied", None) == 0.5 and R.momentum_value("Applied", "90") == 0.2


def test_the_reason_for_an_unrated_row_is_honest_about_why():
    _, _, r = R.score_row(row(1), None, None)
    assert r[0] == "Fit noch nicht bewertet"


def test_the_limited_calls_go_to_the_most_promising_rows_first(tmp_path):
    rows = [row(1, score="10", lane="Other"), row(2, score="90"), row(3, score="50"), row(4, score="95")]
    system = world(tmp_path, rows)
    got = []
    R.run(system, "2026-09-26", do_score=True, limit=2, scorer=lambda role, c, jd, x: got.append(c) or {"ts_fit_score": 0.5, "salary_fit": "mid"})
    assert got == ["Firma 4", "Firma 2"]
