import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_matrix as DM


def test_verdict_red_wins_amber_checks_green_goes():
    keys = ["a", "b", "c", "d", "e"]
    assert DM.verdict({k: "go" for k in keys}, keys)["code"] == "go"
    assert DM.verdict(dict({k: "go" for k in keys}, b="check"), keys)["code"] == "go"          # one amber is fine
    assert DM.verdict(dict({k: "go" for k in keys}, b="check", c="check"), keys)["code"] == "check"
    assert DM.verdict(dict({k: "go" for k in keys}, e="stop"), keys)["code"] == "stop"          # one red is a deal breaker
    assert DM.verdict({"a": "go"}, keys)["code"] == "check"                                      # partly rated
    v = DM.verdict({}, keys)
    assert v["code"] == "open" and v["open"] == 5 and v["total"] == 5


def test_verdict_ignores_unknown_values_and_labels_follow_language():
    v = DM.verdict({"a": "maybe", "b": "go"}, ["a", "b"], "en")
    assert v["open"] == 1 and v["go"] == 1 and v["label"] == "Check"
    assert DM.verdict({"a": "go"}, ["a"], "de")["label"] == "Go"


def test_criteria_most_specific_source_wins():
    content = {"entscheidung": {"kriterien": [{"label": "Budget & Freigabe", "go": "fest budgetiert", "stop": "Budgetrunde offen"}]}}
    prefs = {"decision_criteria": ["Pendelzeit", "Teamgröße"]}
    assert [c["label"] for c in DM.criteria(content, prefs)] == ["Budget & Freigabe"]
    assert [c["label"] for c in DM.criteria({}, prefs)] == ["Pendelzeit", "Teamgröße"]
    assert len(DM.criteria({}, {})) == 5 and DM.criteria({}, {}, "en")[0]["label"] == "Budget & approval"


def test_criteria_keys_are_unique_and_blank_labels_dropped():
    crit = DM.criteria({}, {"decision_criteria": ["Gehalt", "Gehalt", "  ", {"label": ""}, {"label": "Chemie", "go": "Augenhöhe"}]})
    assert [c["label"] for c in crit] == ["Gehalt", "Gehalt", "Chemie"]
    assert len({c["key"] for c in crit}) == 3 and crit[2]["go"] == "Augenhöhe"


def test_yardstick_from_content_or_preferences():
    assert DM.yardstick({}, {"entscheidung": {"massstab": "Drei Tage Pendeln müssen sich rechnen."}}) == "Drei Tage Pendeln müssen sich rechnen."
    y = DM.yardstick({"goal_label": "Vertrag unterschrieben", "goal_date": "2026-12-31", "salary_band": {"floor": 95000, "target": 115000, "currency": "€"},
                      "work_mode": "hybrid", "decision_context": "Umzug Anfang 2027"})
    assert "Vertrag unterschrieben bis 2026-12-31" in y and "€ 95k" in y and "€ 115k" in y and "hybrid" in y and "Umzug" in y
    assert DM.yardstick({}) == ""


def _matrix(folder, name, saved, ratings, criteria=None):
    verlauf = folder / "30 Verlauf"
    verlauf.mkdir(parents=True, exist_ok=True)
    (verlauf / name).write_text(json.dumps({"kind": "pitwall.decision", "saved": saved, "ratings": ratings, "criteria": criteria or []}), encoding="utf-8")


def test_latest_file_takes_the_newest_valid_matrix(tmp_path):
    role = tmp_path / "41 Beispiel AG" / "Head of Data"
    _matrix(role, "Entscheidung_Beispiel_2026-10-20.json", "2026-10-20T10:00:00Z", {"a": "stop"})
    _matrix(role, "Entscheidung_Beispiel_2026-10-28.json", "2026-10-28T15:00:00Z", {"a": "go"})
    (role / "30 Verlauf" / "Entscheidung_kaputt.json").write_text("{not json", encoding="utf-8")
    (role / "30 Verlauf" / "Notizen.txt").write_text("x", encoding="utf-8")
    path, data = DM.latest_file(role)
    assert path.endswith("2026-10-28.json") and data["ratings"] == {"a": "go"}
    assert DM.latest_file(tmp_path / "fehlt") == (None, None)


def test_overview_reads_open_processes_only_and_never_raises(tmp_path):
    role = tmp_path / "41 Beispiel AG" / "Head of Data"
    crit = [{"key": "a"}, {"key": "b"}]
    _matrix(role, "Entscheidung_Beispiel_2026-10-28.json", "2026-10-28T15:00:00Z", {"a": "go", "b": "check"}, crit)
    rows = [{"uid": "41", "role": "Head of Data", "stage": "Interviewing"}, {"uid": "42", "role": "x", "stage": "Closed"},
            {"uid": "43", "role": "y", "stage": "Final"}, "kaputt"]
    finder = lambda base, uid, rolle, fid: ((role, []) if uid == "41" else (None, ["fehlt"]))
    out = DM.overview(rows, str(tmp_path), "de", finder)
    assert list(out) == ["41"] and out["41"]["code"] == "go" and out["41"]["saved"] == "2026-10-28" and out["41"]["file"].startswith("Entscheidung_")
    boom = lambda *a: (_ for _ in ()).throw(RuntimeError("x"))
    assert DM.overview(rows, str(tmp_path), "de", boom) == {}


def test_cockpit_context_names_the_file_for_30_verlauf():
    ctx = DM.cockpit_context({"uid": "41", "company": "Beispiel Maschinenbau AG", "role": "Head of Data"}, {}, {}, "de", "2026-10-30")
    assert ctx["filename"] == "Entscheidung_Beispiel_Maschinenbau_AG_2026-10-30.json"
    assert ctx["uid"] == "41" and len(ctx["criteria"]) == 5 and ctx["lang"] == "de"


def test_conversation_cockpit_renders_the_matrix_with_process_criteria(tmp_path):
    import prep_engine as P
    from test_prep_engine import CONTENT, _content_setup
    content = dict(CONTENT, entscheidung={"massstab": "Pendeln muss sich durch Mandat rechnen.",
                                          "kriterien": [{"label": "Budget & Freigabe", "go": "fest budgetiert", "stop": "Budgetrunde offen"},
                                                        {"label": "Chemie mit CIO", "go": "Augenhöhe", "stop": "Taktung von oben"}]})
    pipe, base, voraus = _content_setup(tmp_path, content)
    res = P.render_from_content("41", pipe, base, "2026-10-30")
    html = open([f for f in res["files"] if os.path.basename(f).startswith("Cockpit_")][0], encoding="utf-8").read()
    assert 'id="ck-entscheidung"' in html and "Entscheidungsmatrix" in html
    assert "Pendeln muss sich durch Mandat rechnen." in html and "Chemie mit CIO" in html and "Budgetrunde offen" in html
    data = json.loads(html.split('<script type="application/json" id="dm-data">', 1)[1].split("</script>", 1)[0])
    assert [c["label"] for c in data["criteria"]] == ["Budget & Freigabe", "Chemie mit CIO"] and data["filename"].startswith("Entscheidung_")
