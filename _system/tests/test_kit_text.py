"""Personal text comes from profile.json: name and brand in pages and PDFs, guardrails and briefs."""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_pdf
import prep_engine as P
import render

PROFILE = {"name": "Erika Müller-O'Neil", "brand_name": "Muster Consulting", "photo": "", "exit_file": "",
           "exit_summary": {"de": "", "en": ""}, "proof_examples": []}


def test_pdf_footer_and_logo_alt_use_the_brand():
    page = intel_pdf.intel_html("# T", "briefing", "t", "s", logo="data:image/png;base64,AAAA", brand="Muster Consulting")
    assert 'alt="Muster Consulting"' in page and "Muster Consulting · Briefing" in page and "XLRTE" not in page


def test_pdf_brand_defaults_to_the_profile_brand(monkeypatch):
    monkeypatch.setattr(intel_pdf, "load_profile", lambda d=None: {"brand_name": "Pitwall"})        # independent of a profile.json next to the engine
    assert "Pitwall · Briefing" in intel_pdf.intel_html("# T", "briefing", "t", "s", logo="")


def test_default_applicant_comes_from_the_profile(tmp_path, monkeypatch):
    (tmp_path / "profile.json").write_text(json.dumps({"name": "Erika Muster"}), encoding="utf-8")
    monkeypatch.setattr(render, "HERE", str(tmp_path))
    assert render.default_applicant() == "Erika Muster"


def _setup(tmp_path):
    row = {"uid": "41", "company": "Acme", "role": "Lead Data", "lane": "Data", "stage": "Interviewing", "ts_fit_score": "0.5", "salary_fit": "mid"}
    pipe = tmp_path / "pipeline.csv"
    with open(pipe, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    voraus = tmp_path / "41 Acme" / "Lead Data" / "20 Vorbereitung"
    voraus.mkdir(parents=True)
    (voraus / "Prep_Inhalt.json").write_text(json.dumps({"company_snapshot": "x", "intel": {"jd_bullets": ["a"]}}), encoding="utf-8")
    return str(pipe), str(tmp_path)


def test_jd_intel_page_shows_the_profile_name_not_the_owner(tmp_path):
    pipe, base = _setup(tmp_path)
    res = P.render_from_content("41", pipe, base, "2026-10-07", profile=PROFILE)
    intel = open([f for f in res["files"] if os.path.basename(f).startswith("JD_Intel_")][0], encoding="utf-8").read()
    assert "Erika Müller-O&#39;Neil" in intel or "Erika Müller-O'Neil" in intel
    assert "Testvorname" not in intel and "Testnachname" not in intel


OWNER = {"name": "Testvorname Testnachname", "brand_name": "XLRTE", "photo": "", "exit_file": "00 references/Exit_Narrative_AllForLabels_CANONICAL.md",
         "exit_summary": {"de": "PE-getriebene Kostenrestrukturierung bei Etikettenwerk hat die Funktion konsolidiert — Transition sauber gemanagt.",
                          "en": "PE-driven restructuring at Etikettenwerk consolidated the function — transition managed cleanly."},
         "proof_examples": ["CUPRA/ATHENA", "EU-AI-Act-Crosswalk bei Etikettenwerk"]}
EMPTY = {"name": "Bewerber:in", "brand_name": "Pitwall", "photo": "", "exit_file": "", "exit_summary": {"de": "", "en": ""}, "proof_examples": []}
TERMS = ("Testvorname", "Testnachname", "Etikettenwerk", "CUPRA", "ATHENA")


def test_owner_guardrails_are_unchanged_for_the_owner_profile():
    de = P.guardrails_for("de", OWNER)
    assert de[2] == "Exit-Story (falls gefragt): PE-getriebene Kostenrestrukturierung bei Etikettenwerk hat die Funktion konsolidiert — Transition sauber gemanagt. Nie anders formulieren."
    assert len(de) == 5 and de[0].startswith("Zuhören vor Pitchen") and de[3].startswith("Nach dem Gespräch")
    en = P.guardrails_for("en", OWNER)
    assert en[2] == "Exit story (if asked): PE-driven restructuring at Etikettenwerk consolidated the function — transition managed cleanly. Never frame differently."


def test_guardrails_without_an_exit_summary_have_no_exit_line():
    for lang in ("de", "en"):
        items = P.guardrails_for(lang, EMPTY)
        assert len(items) == 4 and not any("xit" in i for i in items)


def test_input_brief_has_no_owner_text_for_a_fresh_profile():
    row = {"company": "Acme", "role": "Lead Data", "uid": "1"}
    for lang in ("de", "en"):
        text = P._generate_input_brief(row, lang, {"research_sufficient": True, "bypass_identified": False}, "2026-10-07", profile=EMPTY)
        assert not any(t in text for t in TERMS) and "Bewerber:in" in text


def test_input_brief_uses_name_examples_and_exit_summary_from_the_profile():
    row = {"company": "Acme", "role": "Lead Data", "uid": "1"}
    text = P._generate_input_brief(row, "de", {"research_sufficient": True, "bypass_identified": False}, "2026-10-07", profile=OWNER)
    assert "Testvorname Testnachname" in text and "CUPRA/ATHENA, EU-AI-Act-Crosswalk bei Etikettenwerk" in text
    assert "Transition sauber gemanagt." in text and "Exit_Narrative_AllForLabels_CANONICAL.md" in text
