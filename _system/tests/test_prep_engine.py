import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest

from unittest.mock import patch, MagicMock

SAMPLE_ROW = {
    "uid": "999", "company": "TestCorp AG", "role": "Head of Data",
    "lane": "Data/AI Arch", "stage": "Watchlist", "outcome": "",
    "applied": "", "last_event": "2026-09-22", "days_idle": "0",
    "score": "0", "boost": "0", "salary_fit": "mid",
    "location": "Hamburg", "contacts": "", "folder_id": "",
    "next_action": "", "due": "",
    "note": "Discovered via EURES — pending fit score",
    "ts_confidence": "", "ts_fit_score": "",
}

def _ts_response(answers):
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 200, "output_tokens": 15}}


MOCK_NOUL_SUFFICIENT = _ts_response({
    "research_sufficient": {"type": "noul", "noul": 0.85},
    "bypass_identified":   {"type": "noul", "noul": 0.20},
})

MOCK_NOUL_INSUFFICIENT = _ts_response({
    "research_sufficient": {"type": "noul", "noul": 0.35},
    "bypass_identified":   {"type": "noul", "noul": 0.15},
})


def mock_ts_noul(response):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("urllib.request.urlopen", return_value=mock_resp)


def test_detect_language_de():
    from prep_engine import detect_language
    assert detect_language("Wir suchen einen erfahrenen Leiter IT für unseren Standort Hamburg.") == "de"


def test_detect_language_en():
    from prep_engine import detect_language
    assert detect_language("We are looking for an experienced Head of Data to join our team.") == "en"


def test_detect_language_mixed_defaults_de():
    from prep_engine import detect_language
    assert detect_language("Wir suchen a Head of Data mit experience in AI.") == "de"


def test_noul_gate_sufficient():
    with mock_ts_noul(MOCK_NOUL_SUFFICIENT):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from prep_engine import noul_readiness_gate
            result = noul_readiness_gate("Head of Data", "TestCorp", "Some JD text")
    assert result["research_sufficient"] is True
    assert result["bypass_identified"] is False


def test_noul_gate_insufficient():
    with mock_ts_noul(MOCK_NOUL_INSUFFICIENT):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from prep_engine import noul_readiness_gate
            result = noul_readiness_gate("Head of Data", "TestCorp", "Some JD text")
    assert result["research_sufficient"] is False


def test_noul_gate_missing_answers_key_fails_closed():
    with mock_ts_noul({"model": "jev-1.13.0", "usage": {}}):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            from prep_engine import noul_readiness_gate
            result = noul_readiness_gate("Head of Data", "TestCorp", "Some JD text")
    assert result == {"research_sufficient": False, "bypass_identified": False}


def test_run_prep_creates_brief_markdown(tmp_path):
    pipeline_csv = tmp_path / "pipeline.csv"
    with open(pipeline_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(SAMPLE_ROW.keys()))
        w.writeheader()
        w.writerow(SAMPLE_ROW)

    prep_json = tmp_path / "prep.json"
    prep_json.write_text("{}")

    # Create employer folder structure
    vorbereitung = tmp_path / "999 TestCorp AG" / "Head of Data" / "20 Vorbereitung"
    vorbereitung.mkdir(parents=True)

    with mock_ts_noul(MOCK_NOUL_SUFFICIENT):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            with patch("prep_engine._get_extract_ci", return_value=lambda url: "#1e3a8a"):
                with patch("prep_engine._get_score_opportunity", return_value=lambda *a, **kw: {
                    "ts_fit_score": 0.78, "salary_fit": "high",
                    "boost_contribution": 12, "dimensions": {}
                }):
                    from prep_engine import run_prep
                    result = run_prep(
                        uid=999,
                        pipeline_path=str(pipeline_csv),
                        prep_json_path=str(prep_json),
                        base_dir=str(tmp_path),
                        today="2026-09-22",
                    )

    assert result["status"] in ("ok", "partial")
    md_files = list(vorbereitung.glob("CV_CL_Input_Brief*.md"))
    assert len(md_files) == 1


def test_run_prep_sets_rerun_flag_when_research_insufficient(tmp_path):
    pipeline_csv = tmp_path / "pipeline.csv"
    with open(pipeline_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(SAMPLE_ROW.keys()))
        w.writeheader()
        w.writerow(SAMPLE_ROW)

    prep_json = tmp_path / "prep.json"
    prep_json.write_text("{}")

    vorbereitung = tmp_path / "999 TestCorp AG" / "Head of Data" / "20 Vorbereitung"
    vorbereitung.mkdir(parents=True)

    with mock_ts_noul(MOCK_NOUL_INSUFFICIENT):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            with patch("prep_engine._get_extract_ci", return_value=lambda url: "#1e3a8a"):
                with patch("prep_engine._get_score_opportunity", return_value=lambda *a, **kw: {
                    "ts_fit_score": 0.45, "salary_fit": "mid",
                    "boost_contribution": 7, "dimensions": {}
                }):
                    from prep_engine import run_prep
                    result = run_prep(
                        uid=999,
                        pipeline_path=str(pipeline_csv),
                        prep_json_path=str(prep_json),
                        base_dir=str(tmp_path),
                        today="2026-09-22",
                    )

    assert result["status"] == "partial"
    assert len(result["flags"]) > 0
    prep_data = json.loads(prep_json.read_text())
    assert prep_data["999"]["rerun_needed"] is True


def test_run_prep_unknown_uid_returns_error(tmp_path):
    pipeline_csv = tmp_path / "pipeline.csv"
    with open(pipeline_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(SAMPLE_ROW.keys()))
        w.writeheader()
        w.writerow(SAMPLE_ROW)

    prep_json = tmp_path / "prep.json"
    prep_json.write_text("{}")

    from prep_engine import run_prep
    result = run_prep(uid=888, pipeline_path=str(pipeline_csv),
                      prep_json_path=str(prep_json), base_dir=str(tmp_path), today="2026-09-22")
    assert result["status"] == "error"


# ---- content-driven rendering (Prep_Inhalt.json): no skeleton gaps, ranked questions ---------------------
def _content_setup(tmp_path, content):
    row = dict(SAMPLE_ROW, uid="41", company="Kekswerk", role="Lead Data & AI (m/w/d)", stage="Interviewing", ts_fit_score="0.41")
    pipe = tmp_path / "pipeline.csv"
    with open(pipe, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader(); w.writerow(row)
    voraus = tmp_path / "41 Kekswerk" / "Lead Data & AI" / "20 Vorbereitung"
    voraus.mkdir(parents=True)
    if content is not None:
        (voraus / "Prep_Inhalt.json").write_text(json.dumps(content), encoding="utf-8")
    return str(pipe), str(tmp_path), voraus


CONTENT = {
    "confidence": {"pct": 30, "begruendung": "Testwert", "stand": "2026-10-08"},
    "company_snapshot": "Kekswerk: Umsatz 644,6 Mio. EUR (2024).", "strategic_context": "Neue globale IT-Leitung seit März 2026.",
    "contacts": [{"name": "David Lydon", "title": "Kekswerk", "background": "Titel unbestätigt.", "open_question": "Wie ist die Rolle verankert?"}],
    "keyfacts": {"diagnosed_pain": "Daten fragmentiert", "value_statement": "Governance zuerst", "followup_sent": "nein", "agenda_artifact": "1-Seiter"},
    "open_hook": "Hook A", "close_hook": "Hook B",
    "questions": [{"rank": 2, "question": "Zweite Frage?", "why": "w2", "to": "alle"}, {"rank": 1, "question": "Erste Frage?", "why": "w1", "to": "Tungi Dang"}],
    "open_items": ["Rolle von Tungi Dang unbestätigt"],
    "intel": {"diagnosed_pain": "Datenharmonisierung", "jd_bullets": ["Lead Data & AI"], "scope_signal": "Teamgröße offen"},
    "cockpit": {"termin": "07.10.2026, 17:00", "lage": {"lede": "Kennenlernen mit der Fachseite.", "karten": [{"titel": "Gewonnen", "text": "Einladung steht."}]},
                "vorschlag": {"satz": "Ich übernehme die Rolle mit Blaupausen-Mandat."}, "fuehrung": {"einstieg": "Zuerst zuhören.", "bewegungen": [{"titel": "Zuhören", "text": "bis das Problem klar ist"}]},
                "flanken": [{"titel": "Zeitdruck", "problem": "nicht dreimal nennen", "stattdessen": "einmal ruhig"}],
                "faktenhygiene": {"belegt": ["Umsatz 2024"], "unbelegt": ["Budget"]}, "vorher": [{"titel": "Technik prüfen", "text": "10 Minuten vorher"}],
                "bio": {"kurz": "Ich baue Data- und KI-Fähigkeiten, die vom ersten Tag an regierbar sind.", "lang": "Zuletzt Global Head of Digital, Analytics, Big Data & Governance.", "anker": ["Ordnung in ungeordnete Welten", "Blaupausen in Serie"], "bezug": "Betone Governance."},
                "panik": [{"frage": "Warum diese Rolle?", "antwort": "Weil die Schnittstelle hier die Rolle ist."}]},
}


def test_render_from_content_fills_sections_and_ranks_questions(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    assert [f for f in res["flags"] if "Staffing" not in f] == ["weniger als 3 Fragen in questions"]                    # rendered anyway, finding reported
    prep = [p for p in res["files"] if "Prep_Brief" in p][0]
    html = open(prep, encoding="utf-8").read()
    assert "pending org research" not in html and "PREP GAP" not in html
    assert 'id="meine-fragen"' in html
    assert html.index("Erste Frage?") < html.index("Zweite Frage?")            # sorted by rank, not by list order
    assert "Rolle von Tungi Dang unbestätigt" in html
    intel = open([p for p in res["files"] if "JD_Intel" in p][0], encoding="utf-8").read()
    assert "Datenharmonisierung" in intel and "Teamgröße offen" in intel


def test_render_from_content_without_content_file_writes_nothing(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, None)
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    assert res["status"] == "error" and res["files"] == []
    assert not list(voraus.glob("*.html"))


def test_skeleton_prep_brief_shows_questions_gap(tmp_path):
    import prep_engine as P
    html = P._render_html("prep_brief.html", {"company": "X", "role": "Y", "uid": "1", "today": "2026-10-07", "lang": "de", "next_action": "",
        "company_snapshot": "X — pending org research.", "strategic_context": "", "contacts_detail": [], "keyfacts_fields": [],
        "open_hook": "", "close_hook": "", "guardrails": [], "questions": [], "open_items": [], "title": "t", "heading": "h", "subtitle": "s",
        "footer": "f", "nav": [], "data_json": "{}", "theme_css": ""})
    assert 'id="meine-fragen"' in html and "PREP GAP" in html


def test_render_from_content_reuses_the_name_of_an_existing_document(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    (voraus / "Prep_Brief_Kekswerk_Alter_Rollenname_2026-09-22.html").write_text("old", encoding="utf-8")
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    assert [os.path.basename(f) for f in res["files"] if "Prep_Brief" in f] == ["Prep_Brief_Kekswerk_Alter_Rollenname_2026-10-07.html"]
    assert (voraus / "Prep_Brief_Kekswerk_Alter_Rollenname_2026-09-22.html").read_text(encoding="utf-8") == "old"      # nothing of yours is touched


# ---- going forward: validation, refresh of live processes, order for missing content -----------------------
def test_content_validation_flags_thin_content():
    import prep_engine as P
    assert [f for f in P.validate_content(CONTENT) if "Staffing" not in f] == ["weniger als 3 Fragen in questions"]
    thin = dict(CONTENT, questions=[{"rank": 1, "question": "a"}, {"rank": 1, "question": "b"}, {"rank": 2, "question": "c"}], company_snapshot="", keyfacts={"diagnosed_pain": "x"})
    flags = P.validate_content(thin)
    assert any("company_snapshot" in f for f in flags) and any("keyfacts" in f for f in flags) and any("Rang" in f for f in flags)
    ok = dict(CONTENT, questions=[{"rank": i, "question": "Budget? q%d" % i, "to": "x", "why": "y"} for i in (1, 2, 3)])
    assert P.validate_content(ok) == []


def test_render_from_content_reports_validation_flags_but_still_renders(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    assert res["status"] == "partial" and any("Fragen" in f for f in res["flags"]) and len(res["files"]) == 3


def test_refresh_live_renders_when_content_is_newer_and_orders_content_when_missing(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, dict(CONTENT, questions=[{"rank": i, "question": "q%d" % i, "to": "x", "why": "y"} for i in (1, 2, 3)]))
    out = P.refresh_live(pipe, base, "2026-10-07")
    assert out["rendered"] == ["41"] and out["needs_content"] == []
    assert P.refresh_live(pipe, base, "2026-10-07")["rendered"] == []                 # nothing new: idempotent
    (voraus / "Kekswerk_Briefing_2026-10-07_v2.md").write_text("# Briefing", encoding="utf-8")
    t = os.path.getmtime(voraus / "Prep_Inhalt.json") + 100
    os.utime(voraus / "Kekswerk_Briefing_2026-10-07_v2.md", (t, t))                   # the briefing is newer than the content
    out = P.refresh_live(pipe, base, "2026-10-07")
    assert out["needs_content"] and out["needs_content"][0]["uid"] == "41"
    order = voraus / "Prep_Auftrag_Kekswerk.md"
    assert order.exists() and "Prep_Inhalt.json" in order.read_text(encoding="utf-8") and "Kekswerk_Briefing_2026-10-07_v2.md" in order.read_text(encoding="utf-8")


# ---- cockpit per conversation + playbook (what the Sync learned from earlier conversations) --------------------
def test_cockpit_is_rendered_with_ranked_questions_and_the_playbook(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    ref = tmp_path / "00 references"
    ref.mkdir()
    (ref / "Gespraechs_Playbook.json").write_text(json.dumps({"items": [{"id": "schwan", "titel": "Der Schwan", "problem": "Selbstabwertung vor Technikern", "stattdessen": "Position behaupten", "quelle": "Cockpit 11.09."}]}), encoding="utf-8")
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    cock = [f for f in res["files"] if os.path.basename(f).startswith("Cockpit_")]
    assert len(cock) == 1
    html = open(cock[0], encoding="utf-8").read()
    assert "PREP GAP" not in html and "Ich übernehme die Rolle" in html and "Zeitdruck" in html
    assert "Der Schwan" in html and "gelernt" in html                                            # the playbook feeds 'Offene Flanken'
    assert html.index("Erste Frage?") < html.index("Zweite Frage?")


def test_cockpit_without_content_block_is_flagged_and_not_written(tmp_path):
    import prep_engine as P
    c = dict(CONTENT)
    c.pop("cockpit")
    pipe, base, voraus = _content_setup(tmp_path, c)
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    assert any("cockpit fehlt" in f for f in res["flags"])
    assert not [f for f in res["files"] if os.path.basename(f).startswith("Cockpit_")]


def test_validate_content_names_missing_cockpit_parts():
    import prep_engine as P
    c = dict(CONTENT, cockpit={"lage": {"lede": "x"}})
    flags = P.validate_content(c)
    assert any("cockpit.vorschlag" in f for f in flags) and any("cockpit.fuehrung" in f for f in flags) and any("cockpit.vorher" in f for f in flags)


def test_load_playbook_is_tolerant(tmp_path):
    import prep_engine as P
    assert P.load_playbook(str(tmp_path)) == []
    (tmp_path / "00 references").mkdir()
    (tmp_path / "00 references" / "Gespraechs_Playbook.json").write_text("{kaputt", encoding="utf-8")
    assert P.load_playbook(str(tmp_path)) == []


# ---- live guide: bio for the role, panic card, honesty guard ------------------------------------------------
def test_cockpit_has_bio_panic_card_and_generic_panic_items_from_the_playbook(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    ref = tmp_path / "00 references"
    ref.mkdir()
    (ref / "Gespraechs_Playbook.json").write_text(json.dumps({"items": [], "panik": [{"frage": "Bei Blackout", "antwort": "Darf ich kurz zurückspulen?"}]}), encoding="utf-8")
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    html = open([f for f in res["files"] if os.path.basename(f).startswith("Cockpit_")][0], encoding="utf-8").read()
    assert "Ich baue Data- und KI-Fähigkeiten" in html and "Ordnung in ungeordnete Welten" in html and "Betone Governance" in html
    assert html.index("Warum diese Rolle?") < html.index("Bei Blackout")                              # role-specific first, generic after
    assert 'id="panic"' in html and "PREP GAP" not in html


def test_missing_bio_and_panic_are_flagged():
    import prep_engine as P
    ck = dict(CONTENT["cockpit"])
    ck.pop("bio"), ck.pop("panik")
    flags = P.validate_content(dict(CONTENT, cockpit=ck))
    assert any("cockpit.bio" in f for f in flags) and any("cockpit.panik" in f for f in flags)


def test_forbidden_phrases_from_the_bio_building_blocks_are_flagged(tmp_path):
    import prep_engine as P
    ck = dict(CONTENT["cockpit"], bio=dict(CONTENT["cockpit"]["bio"], kurz="Global Head of IT Strategy, Data & AI bei Etikettenwerk"))
    flags = P.validate_content(dict(CONTENT, cockpit=ck), forbidden=["IT Strategy, Data & AI"])
    assert any("IT Strategy, Data & AI" in f for f in flags)
    assert P.load_forbidden(str(tmp_path)) == []
    (tmp_path / "00 references").mkdir()
    (tmp_path / "00 references" / "Bio_Bausteine.json").write_text(json.dumps({"nicht_sagen_woerter": ["IT Strategy, Data & AI"]}), encoding="utf-8")
    assert P.load_forbidden(str(tmp_path)) == ["IT Strategy, Data & AI"]


def test_conversation_templates_never_share_a_name_with_the_dashboard_templates():
    # regression: 'cockpit.html' is the template of the Pitwall page 01_cockpit.html and was overwritten once by the conversation cockpit
    import re
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prep = set(re.findall(r'"([\w]+\.html)"', open(os.path.join(here, "prep_engine.py"), encoding="utf-8").read())) & set(os.listdir(os.path.join(here, "templates")))
    pages = set(re.findall(r'"([\w]+\.html)"', open(os.path.join(here, "render.py"), encoding="utf-8").read())) & set(os.listdir(os.path.join(here, "templates")))
    assert prep and pages and not (prep & pages)


def test_cockpit_offers_notes_as_a_file_the_sync_picks_up_from_30_verlauf(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    res = P.render_from_content("41", pipe, base, "2026-10-07")
    html = open([f for f in res["files"] if os.path.basename(f).startswith("Cockpit_")][0], encoding="utf-8").read()
    assert "Interview_Notizen_Kekswerk_2026-10-07.txt" in html and "ck-save" in html and "30 Verlauf" in html
    import re as _re
    from revisit import CATEGORY_PATTERNS
    name = "Interview_Notizen_Kekswerk_2026-10-07.txt"
    assert CATEGORY_PATTERNS[0][0].search(name) and CATEGORY_PATTERNS[0][1] == "Gespraech gefuehrt"      # revisit counts it as a conversation input
    import intel_job
    assert intel_job.TRANSCRIPT.search(name)                                                   # and the after-interview order lists it as a source


def test_a_missing_template_engine_is_reported_not_written_as_a_page(tmp_path):
    import prep_engine as P
    pipe, base, voraus = _content_setup(tmp_path, CONTENT)
    missing = object()
    saved = sys.modules.get("jinja2", missing)
    sys.modules["jinja2"] = None                      # an import of jinja2 now fails, like in the embedded runtime without the package
    try:
        res = P.render_from_content("41", pipe, base, "2026-10-07")
    finally:
        if saved is missing:
            sys.modules.pop("jinja2", None)
        else:
            sys.modules["jinja2"] = saved
    assert res["status"] == "error" and res["files"] == [] and any("Vorlagen-Bibliothek" in f for f in res["flags"])
    assert not list(voraus.glob("*.html"))


# ---- Lehre Nordberatung (Absage 2026-10-15): Staffing/Budget/Auslastung muss als Frage im Panel stehen -----------------
def _three(extra=None):
    qs = [{"rank": i, "question": "q%d" % i, "to": "x", "why": "y"} for i in (1, 2, 3)]
    return dict(CONTENT, questions=qs + (extra or []))


def test_validate_content_flags_missing_staffing_question():
    import prep_engine as P
    flags = P.validate_content(_three())
    assert any("Staffing" in f for f in flags)


def test_validate_content_accepts_a_staffing_budget_question():
    import prep_engine as P
    for text in ("Sind Sie Budgetinhaber für diese Rolle, und wie läuft die Freigabe?",
                 "Wie hoch ist die geplante Auslastung auf Kundenprojekten?",
                 "Ist die Stelle im Headcount-Plan für 2027 hinterlegt?"):
        extra = [{"rank": 4, "question": text, "to": "x", "why": "y"}]
        assert not any("Staffing" in f for f in P.validate_content(_three(extra))), text
