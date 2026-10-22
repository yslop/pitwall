import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import confidence as C


def row(**kw):
    r = {"stage": "Interviewing", "score": 60, "salary_fit": "", "days_idle": "3", "outcome": ""}
    r.update(kw)
    return r


def test_stage_is_the_base_and_later_stages_rank_higher():
    p = [C.estimate(row(stage=s), 0)["pct"] for s in ("Watchlist", "Applied", "Screening", "Interviewing", "Final")]
    assert p == sorted(p) and len(set(p)) == 5


def test_each_documented_conversation_raises_the_value_but_stays_capped_by_stage():
    a, b = C.estimate(row(), 0)["pct"], C.estimate(row(), 2)["pct"]
    assert b > a
    assert C.estimate(row(stage="Applied"), 9)["pct"] <= C.CAP["Applied"]


def test_below_target_pay_and_long_silence_lower_it():
    base = C.estimate(row(), 1)["pct"]
    assert C.estimate(row(salary_fit="below"), 1)["pct"] < base
    assert C.estimate(row(days_idle="50"), 1)["pct"] < base


def test_closed_rows_have_no_value_and_every_value_explains_itself():
    assert C.estimate(row(stage="Closed", outcome="rejected"), 3) is None
    e = C.estimate(row(), 1)
    assert 1 <= e["pct"] <= 85 and e["why"] and all(isinstance(w, str) for w in e["why"])


def test_missing_or_odd_fields_do_not_crash():
    assert C.estimate({"stage": "Interviewing"}, 0)["pct"] > 0
    assert C.estimate(row(score="x", days_idle=""), 0)["pct"] > 0


def test_conversations_are_counted_from_debriefs_and_transcripts_only():
    with tempfile.TemporaryDirectory() as d:
        v = os.path.join(d, "30 Verlauf"); os.makedirs(v)
        for n in ("Debrief_X_2026-10-07.md", "10-07 Interview_ X-transcript.txt", "10-07 Interview_ X-Summary.pdf", "10-02 Call-transcript.txt", "Mail_2026-09-03_Ack.pdf", "JD_X.pdf"):
            open(os.path.join(v, n), "w").close()
        assert C.conversations_done(d) == 2          # two transcripts; the debrief and summary of the same call do not count again
        for n in os.listdir(v):
            if "transcript" in n:
                os.remove(os.path.join(v, n))
        assert C.conversations_done(d) == 1          # only a debrief left: one conversation
        assert C.conversations_done(os.path.join(d, "none")) == 0


def _prep(d, content):
    import json
    v = os.path.join(d, "20 Vorbereitung"); os.makedirs(v, exist_ok=True)
    with open(os.path.join(v, "Prep_Inhalt.json"), "w", encoding="utf-8") as f:
        json.dump(content, f)


def test_the_observers_judgement_in_the_prep_content_is_read_with_its_reasoning():
    with tempfile.TemporaryDirectory() as d:
        _prep(d, {"confidence": {"pct": 35, "begruendung": "Mandat bestaetigt, Budget offen", "stand": "2026-10-08"}})
        j = C.observer_judgement(d)
        assert j == {"pct": 35, "why": ["Einschätzung nach den Gesprächen (Stand 2026-10-08): Mandat bestaetigt, Budget offen"]}


def test_unusable_judgements_are_ignored_so_the_heuristic_stays():
    for bad in ({"pct": 0, "begruendung": "x"}, {"pct": 120, "begruendung": "x"}, {"pct": "viel", "begruendung": "x"}, {"pct": 40}, "40"):
        with tempfile.TemporaryDirectory() as d:
            _prep(d, {"confidence": bad})
            assert C.observer_judgement(d) is None
    assert C.observer_judgement("/nonexistent") is None


def test_prep_validation_asks_for_a_judgement_and_rejects_a_broken_one():
    import prep_engine as P
    full = {"questions": [{"rank": i, "question": "q", "to": "t", "why": "w"} for i in (1, 2, 3)], "company_snapshot": "x",
            "keyfacts": {k: "x" for _, k in P._KEYFACTS_LABELS["de"]}, "contacts": [{"name": "a"}], "intel": {"jd_bullets": ["b"]},
            "cockpit": {"lage": {"lede": "l"}, "vorschlag": {"satz": "s"}, "fuehrung": {"einstieg": "e"}, "vorher": ["v"], "bio": {"kurz": "k"}, "panik": ["p"]}}
    assert any("confidence" in f for f in P.validate_content(full))
    full["confidence"] = {"pct": 30, "begruendung": "Grund", "stand": "2026-10-08"}
    assert not any("confidence" in f for f in P.validate_content(full))
    full["confidence"] = {"pct": 300, "begruendung": "Grund"}
    assert any("confidence" in f for f in P.validate_content(full))
