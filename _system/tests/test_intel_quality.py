"""intel_quality: form and verifiability of one intel document (counts, sources, ages), not the truth of its statements."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_quality as Q
import test_intel_docs as T

TODAY = "2026-10-02"


def test_a_good_briefing_is_counted_without_surprises():
    m = Q.metrics(T.BRIEFING, "briefing", 1, TODAY)
    assert m["facts"] == 4 and m["inferences"] == 6 and m["facts_unsourced"] == 0 and m["sources"] == 3 and m["domains"] == 1
    assert m["dangling"] == [] and m["oldest_source_age"] == 12 and m["open_section"] is True
    assert m["lint"] == "pass" and m["lint_rules"] == []


def test_unsourced_facts_and_dangling_references_are_found():
    text = T.BRIEFING.replace("Umsatz von 1,2 Mrd. EUR [1]", "Umsatz von 1,2 Mrd. EUR").replace("Zukäufe, weil die Bilanz Spielraum zeigt [1]", "Zukäufe [9]")
    m = Q.metrics(text, "briefing", 1, TODAY)
    assert m["facts_unsourced"] == 1 and m["dangling"] == [9]


def test_domains_age_and_unverified_marks():
    text = T.BRIEFING.replace("https://example.org/market", "https://other.example.com/market").replace("abgerufen 2026-09-21", "abgerufen 2026-08-01")
    text += "\n\n- LinkedIn-Profil nicht abrufbar (robots.txt), Rolle nicht verifiziert.\n"
    m = Q.metrics(text, "briefing", 1, TODAY)
    assert m["domains"] == 2 and m["oldest_source_age"] == 62 and m["unverified"] == 2


def test_the_open_points_section_is_recognised_by_its_heading():
    assert Q.metrics(T.BRIEFING.replace("## Offen / nicht verifiziert", "## Hinweise"), "briefing", 1, TODAY)["open_section"] is False


def test_odd_input_never_crashes():
    for text in ("", "kein Markdown", "## Quellen\n\n", "FACT: [", "\x00\x01"):
        m = Q.metrics(text, "briefing", 1, TODAY)
        assert m["lint"] in ("pass", "warn", "fail") and m["oldest_source_age"] is None or isinstance(m["oldest_source_age"], int)


# ---- the lint rule and the order template (step C) ----------------------------------------------------------------
def test_lint_warns_when_the_open_points_section_is_missing():
    text = T.BRIEFING.replace("## Offen / nicht verifiziert\nkeine.\n\n", "")
    f = T.lint(text)
    assert "open" in T.rules(f, "warn") and T.rules(f, "fail") == []


def test_the_research_order_demands_the_open_points_section(tmp_path):
    system, base, role, locate = T.world(tmp_path)
    import intel_job as J
    res = J.run_job("215", system, base, "2026-10-02", locate=locate)
    t = open(res["file"], encoding="utf-8").read()
    assert t.count("Offen / nicht verifiziert") >= 3          # required section, writing rule and checklist


def test_sources_without_a_url_are_legitimate_numbered_sources():
    text = T.BRIEFING.replace("## Quellen", "## Quellen").rstrip("\n") + "\n4. eigene Mitschrift „Interview“ vom 2026-09-30 (Transkript, intern)\n5. Zeilennotiz der Pipeline, Stand 2026-10-01\n"
    text = text.replace("Zuerst diagnostizieren, dann ein 90-Tage-Plan mit KPI-Register [1].", "Zuerst diagnostizieren [4], Rückmeldung offen [5], Ziel unklar [7].")
    m = Q.metrics(text, "briefing", 1, TODAY)
    assert m["sources"] == 3 and m["dangling"] == [7]               # [4] and [5] exist (no URL needed), [7] does not
