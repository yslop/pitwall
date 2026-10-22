import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_job as J
import intel_lint as IL
import intel_pdf as P
import test_render as TR

BRIEFING = """# Briefing — Acme AG

## Strategie und Finanzbild
FACT: Acme AG erzielte 2025 einen Umsatz von 1,2 Mrd. EUR [1]. FACT: Eigentümer ist ein PE-Fonds seit 2022 [2].
INFERENCE: Der Fonds sucht Wachstum durch Zukäufe, weil die Bilanz Spielraum zeigt [1].

## Markt und Wettbewerb
FACT: Der Markt wächst laut Verband mit 4 % pro Jahr [3]. INFERENCE: Preisdruck bleibt hoch, weil zwei Wettbewerber expandieren [3].

## Organisation und Entscheider
FACT: Der CFO verantwortet die IT-Roadmap [2]. INFERENCE: Der CFO ist der eigentliche Sponsor der Rolle [2].

## Risiken
INFERENCE: Integration mehrerer Zukäufe bindet Kapazität, die Rolle braucht ein klares Mandat [2].

## Was sie von dieser Rolle brauchen
INFERENCE: Ein Datenbackbone über Standorte hinweg, weil Berichte heute manuell entstehen [1].

## Mein Pitch und meine Agenda
INFERENCE: Zuerst diagnostizieren, dann ein 90-Tage-Plan mit KPI-Register [1].

## Offen / nicht verifiziert
keine.

## Quellen
1. https://example.org/annual-report abgerufen 2026-09-20
2. https://example.org/about abgerufen 2026-09-20
3. https://example.org/market abgerufen 2026-09-21
"""


def world(tmp_path, stage="Interviewing", with_docs=True):
    system, base, role, locate = TR.world(tmp_path, with_drafts=False)
    rows = list(csv.DictReader(open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8")))
    with open(os.path.join(system, "pipeline.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "folder_id", "note", "stage"])
        w.writeheader()
        for r in rows:
            r["stage"] = stage
            w.writerow(r)
    (role / "30 Verlauf").mkdir(exist_ok=True)
    open(os.path.join(system, "jd_cache.json"), "w", encoding="utf-8").write(json.dumps({"215": "Anforderungen\n- Mehrjährige Erfahrung in der IT-Strategie und Führung großer Teams"}))
    return system, base, role, locate


def write_doc(role, text, version=1, doc="Briefing", person="", date="2026-09-22"):
    tag = "_" + person.replace(" ", "_") if person else ""
    p = role / "20 Vorbereitung" / ("Acme_AG_%s%s_%s_v%d.md" % (doc, tag, date, version))
    p.write_text(text, encoding="utf-8")
    return p


def rules(findings, level=None):
    return sorted({f["rule"] for f in findings if level is None or f["level"] == level})


# ---- job files ------------------------------------------------------------------------------------------------------
def test_each_stage_calls_for_its_own_document_and_deeper_existing_ones_satisfy_it():
    assert [J.needed_doc(s, {}) for s in ("Watchlist", "Applied", "Screening", "Interviewing", "Final", "Closed")] == [None, None, "cheat_sheet", "briefing", "strategy", None]
    assert J.needed_doc("Interviewing", {"cheat_sheet": ["x"]}) == "briefing" and J.needed_doc("Screening", {"briefing": ["x"]}) is None
    assert J.needed_doc("Final", {"briefing": ["x"]}) == "strategy" and J.needed_doc("Final", {"strategy": ["x"]}) is None


def test_the_research_job_file_is_self_contained_with_sections_rules_outputs_and_commands(tmp_path):
    system, base, role, locate = world(tmp_path)
    (role / "20 Vorbereitung" / "CV_CL_Input_Brief_Acme.md").write_text("x", encoding="utf-8")
    (role / "10 Bewerbung" / "Ausschreibung.pdf").write_bytes(b"%PDF x")
    res = J.run_job("215", system, base, "2026-09-26", locate=locate)
    assert res["status"] == "written" and res["doc"] == "briefing" and res["version"] == 1 and os.path.basename(res["file"]) == "Recherche_Auftrag_Acme_AG_Lagebild.md"
    t = open(res["file"], encoding="utf-8").read()
    assert t.startswith("# Rechercheauftrag — Acme AG · Head of Data") and "Stufe **Interviewing**" in t and "Dokument: **Briefing**" in t
    for s in J.DOCS["briefing"]["sections"]:
        assert s in t
    for part in ("Nur öffentliche Quellen", "URL und Abrufdatum", "FACT oder INFERENCE", "Keine erfundenen Zahlen", "Exit_Narrative.md",
                 "Acme_AG_Briefing_2026-09-26_v1.md", "intel_lint.py --uid 215", "intel_pdf.py --uid 215", "Ausschreibung.pdf", "CV_CL_Input_Brief_Acme.md", "Nichts wird gesendet"):
        assert part in t, part
    st = json.load(open(os.path.join(system, "intel_state.json"), encoding="utf-8"))["215"]["jobs"]["Recherche_Auftrag_Acme_AG_Lagebild.md"]
    assert st["doc"] == "briefing" and st["version"] == 1 and st["after"] is False


def test_no_job_for_stages_without_a_document_or_when_the_document_exists_and_a_wrong_doc_name_is_reported(tmp_path):
    system, base, role, locate = world(tmp_path, stage="Watchlist")
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    system, base, role, locate = world(tmp_path / "b", stage="Interviewing")
    (role / "20 Vorbereitung" / "Acme_Briefing_Brandt_2026-09-11.pdf").write_bytes(b"%PDF")             # your own file counts
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    assert J.run_job("215", system, base, "2026-09-26", doc="strategy", locate=locate)["status"] == "written"
    assert J.run_job("215", system, base, "2026-09-26", doc="nonsense", locate=locate)["status"] == "skipped"
    assert J.run_job("999", system, base, "2026-09-26", locate=locate)["status"] == "skipped"


def test_a_person_gets_their_own_job_and_versions_count_up_from_the_generated_files(tmp_path):
    system, base, role, locate = world(tmp_path)
    res = J.run_job("215", system, base, "2026-09-26", person="Erika Muster", locate=locate)
    assert os.path.basename(res["file"]) == "Recherche_Auftrag_Acme_AG_Lagebild_Erika_Muster.md" and "für **Erika Muster**" in open(res["file"], encoding="utf-8").read()
    assert "Acme_AG_Briefing_Erika_Muster_2026-09-26_v1.md" in open(res["file"], encoding="utf-8").read()
    write_doc(role, BRIEFING, 1, person="Erika Muster")
    write_doc(role, BRIEFING, 3, person="Erika Muster")
    write_doc(role, BRIEFING, 1)
    assert J.next_intel_version(role, "briefing", "Erika Muster") == 4 and J.next_intel_version(role, "briefing", "") == 2 and J.next_intel_version(role, "cheat_sheet", "") == 1


def test_the_after_interview_job_names_transcripts_notes_debrief_and_the_changes_section(tmp_path):
    system, base, role, locate = world(tmp_path)
    write_doc(role, BRIEFING, 1)
    (role / "30 Verlauf" / "Mitschrift_Transkript_2026-09-25.txt").write_text("...", encoding="utf-8")
    (role / "30 Verlauf" / "Notizen Gespräch.md").write_text("...", encoding="utf-8")
    (role / "30 Verlauf" / "Einladung.pdf").write_bytes(b"%PDF")
    res = J.run_job("215", system, base, "2026-09-26", after=True, locate=locate)
    t = open(res["file"], encoding="utf-8").read()
    assert os.path.basename(res["file"]) == "Nachbereitung_Auftrag_Acme_AG_Lagebild.md" and res["version"] == 2 and t.startswith("# Nachbereitungsauftrag")
    assert "Mitschrift_Transkript_2026-09-25.txt" in t and "Notizen Gespräch.md" in t and "Einladung.pdf" not in t.split("Transkripte und Notizen")[1].split("\n")[0]
    assert "Debrief_Acme_AG_2026-09-26.md" in t and "Änderungen seit v1" in t and "Acme_AG_Briefing_2026-09-26_v2.md" in t and "Mitschrift" in t


def test_job_file_is_current_until_inputs_change_and_force_dry_run_and_errors_behave(tmp_path):
    system, base, role, locate = world(tmp_path)
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "written"
    assert J.run_job("215", system, base, "2026-09-27", locate=locate)["status"] == "current"
    (role / "20 Vorbereitung" / "CV_CL_Input_Brief_Acme.md").write_text("x", encoding="utf-8")
    assert J.run_job("215", system, base, "2026-09-28", locate=locate)["status"] == "written"
    assert J.run_job("215", system, base, "2026-09-28", force=True, locate=locate)["status"] == "written"
    dry = J.run_job("215", system, base, "2026-09-28", dry_run=True, locate=locate)
    assert dry["status"] == "written" and dry["text"].startswith("# Rechercheauftrag")
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert J.run_job("215", system, base, "2026-09-28", locate=broken)["status"] == "error"
    open(os.path.join(system, "intel_state.json"), "w", encoding="utf-8").write(json.dumps({"215": {"jobs": "x"}, "9": []}))
    assert J.run_job("215", system, base, "2026-09-29", force=True, locate=locate)["status"] == "written"


def test_the_live_sweep_lists_only_processes_that_need_something(tmp_path, capsys):
    system, base, role, locate = world(tmp_path, stage="Screening")
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert J.main(["--live", "--system", system, "--base-dir", base, "--today", "2026-09-26"]) == 0
        first = capsys.readouterr().out
        assert "intel_job uid 215: written · Cheat Sheet v1" in first
        write_doc(role, "x", 1, doc="CheatSheet")
        assert J.main(["--live", "--system", system, "--base-dir", base, "--today", "2026-09-27"]) == 0
    assert capsys.readouterr().out in ("", first)                                                     # the second sweep printed nothing new (the runner's shim does not reset)


# ---- lint -----------------------------------------------------------------------------------------------------------
def lint(text, doc="briefing", version=1, today="2026-09-26"):
    return IL.lint_text("Acme_AG_Briefing_2026-09-22_v1.md", text, doc, version, today)


def test_a_complete_sourced_and_tagged_briefing_passes():
    assert lint(BRIEFING) == []


def test_missing_sections_and_missing_or_too_few_sources_fail():
    f = lint(BRIEFING.replace("## Risiken\n", "## Sonstiges\n"))
    assert rules(f, "fail") == ["section"] and "Risiken" in f[0]["text"]
    nosrc = BRIEFING.split("## Quellen")[0]
    assert "sources" in rules(lint(nosrc), "fail") and "section" in rules(lint(nosrc), "fail")
    two = BRIEFING.replace("3. https://example.org/market abgerufen 2026-09-21\n", "")
    assert rules(lint(two), "fail") == ["sources"] and "mindestens 3" in lint(two)[0]["text"]
    assert lint(two, doc="cheat_sheet") and rules(lint(BRIEFING.replace("Strategie und Finanzbild", "Das Unternehmen in Zahlen"), doc="cheat_sheet"), "fail") != []


def test_sources_without_a_date_or_too_old_and_untagged_statements_and_unsourced_numbers_warn():
    assert rules(lint(BRIEFING.replace(" abgerufen 2026-09-20\n2. ", "\n2. ", 1)), "warn") == ["sources"]
    assert rules(lint(BRIEFING, today="2026-11-30"), "warn") == ["stale"]
    untagged = BRIEFING.replace("FACT: ", "").replace("INFERENCE: ", "")
    assert "tags" in rules(lint(untagged), "warn")
    head, rest = BRIEFING.split("## Markt und Wettbewerb", 1)
    unsourced = head.replace("[1]", "").replace("[2]", "") + "## Markt und Wettbewerb" + rest             # the first section's paragraph has numbers and no source stamp
    assert "number" in rules(lint(unsourced), "warn")


def test_placeholders_fail_and_length_warns():
    assert "placeholder" in rules(lint(BRIEFING + "\n[FIRMA] TODO\n"), "fail")
    assert "length" in rules(lint(BRIEFING + "\nWort " * 2300), "warn")


def test_a_new_version_needs_the_changes_section_and_inference_to_fact_needs_a_source():
    assert rules(lint(BRIEFING, version=2), "fail") == ["changes"]
    good = BRIEFING + "\n## Änderungen seit v1\n- INFERENCE → FACT: CFO ist Sponsor (Transkript 00:14:20).\n- Neu: Ansprechpartner Erika Muster [2].\n"
    assert lint(good, version=2) == []
    weak = BRIEFING + "\n## Änderungen seit v1\n- INFERENCE → FACT: CFO ist Sponsor.\n"
    assert rules(lint(weak, version=2)) == ["changes"] and lint(weak, version=2)[0]["level"] == "warn"


def test_run_lint_finds_the_latest_version_per_document_and_person_and_records_the_state(tmp_path):
    system, base, role, locate = world(tmp_path)
    write_doc(role, BRIEFING, 1)
    write_doc(role, BRIEFING + "\n## Änderungen seit v1\n- Neu: Punkt mit Quelle [1].\n", 2)
    write_doc(role, BRIEFING.replace("## Risiken", "## X"), 1, person="Erika Muster")
    res = IL.run_lint("215", system, base, "2026-09-26", locate=locate)
    assert res["status"] == "fail" and sorted((r["doc"], r["version"], r["status"]) for r in res["results"]) == [("briefing", 1, "fail"), ("briefing", 2, "pass")]
    st = json.load(open(os.path.join(system, "intel_state.json"), encoding="utf-8"))["215"]["docs"]
    assert st["briefing:"]["latest"] == "v2" and st["briefing:"]["versions"]["v2"]["result"] == "pass" and st["briefing:Erika_Muster"]["versions"]["v1"]["fails"] == 1


def test_run_lint_reports_unreadable_missing_and_odd_state_without_raising(tmp_path):
    system, base, role, locate = world(tmp_path)
    assert IL.run_lint("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    (role / "20 Vorbereitung" / "Acme_AG_Briefing_2026-09-22_v1.md").write_bytes("ü".encode("cp1252"))
    res = IL.run_lint("215", system, base, "2026-09-26", dry_run=True, locate=locate)
    assert res["status"] == "fail" and res["results"][0]["findings"][0]["rule"] == "unreadable"
    open(os.path.join(system, "intel_state.json"), "w", encoding="utf-8").write(json.dumps({"215": {"docs": {"briefing:": {"versions": {"vX": 1, "v1": "x"}}}}}))
    write_doc(role, BRIEFING, 1)
    assert IL.run_lint("215", system, base, "2026-09-26", locate=locate)["status"] == "pass"
    assert IL.run_lint("999", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert IL.run_lint("215", system, base, "2026-09-26", locate=broken)["status"] == "error"


def test_lint_cli_exit_codes(tmp_path, capsys):
    system, base, role, locate = world(tmp_path)
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert IL.main(["--uid", "215", "--system", system, "--base-dir", base]) == 4
        write_doc(role, BRIEFING.replace("## Risiken", "## X"), 1)
        assert IL.main(["--uid", "215", "--system", system, "--base-dir", base, "--dry-run"]) == 2
        assert "FEHLER section" in capsys.readouterr().out
        write_doc(role, BRIEFING, 1)
        assert IL.main(["--uid", "215", "--system", system, "--base-dir", base, "--dry-run"]) == 0


# ---- PDF ------------------------------------------------------------------------------------------------------------
def test_the_intel_page_is_xlrte_styled_and_escapes_everything():
    h = P.intel_html("# <script>x</script>\n\nFACT: ok [1]\n", "briefing", "Acme · Briefing", "Acme · Briefing · v1 · 2026-09-22", brand="XLRTE")
    assert "#E4572E" in h and "Jost" in h and "Nunito+Sans" in h and "<script>" not in h and "&lt;script&gt;" in h and "XLRTE" in h and 'src="data:image/svg+xml;base64,' in h
    assert "<img" not in P.intel_html("x", "briefing", "t", "s", logo="")


def test_pdf_is_made_only_without_lint_errors_named_like_the_document_and_only_when_the_text_changed(tmp_path):
    system, base, role, locate = world(tmp_path)
    good = write_doc(role, BRIEFING, 1)
    write_doc(role, BRIEFING.replace("## Risiken", "## X"), 1, doc="CheatSheet")
    r = TR.Runner()
    res = P.run_pdf("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=r)
    assert res["status"] == "written" and res["files"] == ["Acme_AG_Briefing_2026-09-22_v1.pdf"] and any("kein PDF" in n for n in res["notes"])
    assert (role / "20 Vorbereitung" / "Acme_AG_Briefing_2026-09-22_v1.pdf").exists() and len(r.calls) == 1
    assert P.run_pdf("215", system, base, "2026-09-27", locate=locate, chrome="/fake/chrome", runner=r)["status"] == "current" and len(r.calls) == 1
    good.write_text(BRIEFING + "\nINFERENCE: Ein weiterer Satz mit genug Länge [1].\n", encoding="utf-8")
    assert P.run_pdf("215", system, base, "2026-09-28", locate=locate, chrome="/fake/chrome", runner=r)["status"] == "written"
    import intel_index as II
    assert II.classify("Acme_AG_Briefing_2026-09-22_v1.pdf") == "briefing" and II.classify("Acme_AG_CheatSheet_Erika_2026-09-22_v1.pdf") == "cheat_sheet" and II.classify("Acme_AG_Strategy_Doc_2026-09-22_v1.pdf") == "strategy"


def test_pdf_without_chrome_keeps_html_and_a_new_version_leaves_the_old_pdf(tmp_path):
    system, base, role, locate = world(tmp_path)
    write_doc(role, BRIEFING, 1)
    res = P.run_pdf("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=TR.Runner(ok=False))
    assert res["status"] == "skipped" and (role / "20 Vorbereitung" / "Acme_AG_Briefing_2026-09-22_v1.html").exists() and any("Chrome" in n for n in res["notes"])
    P.run_pdf("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=TR.Runner())
    write_doc(role, BRIEFING + "\n## Änderungen seit v1\n- Neu: Punkt mit Quelle [1].\n", 2)
    res = P.run_pdf("215", system, base, "2026-09-27", locate=locate, chrome="/fake/chrome", runner=TR.Runner())
    assert res["files"] == ["Acme_AG_Briefing_2026-09-22_v2.pdf"] and (role / "20 Vorbereitung" / "Acme_AG_Briefing_2026-09-22_v1.pdf").exists()


def test_pdf_reports_missing_documents_unknown_uids_and_offline_drive(tmp_path):
    system, base, role, locate = world(tmp_path)
    assert P.run_pdf("215", system, base, "2026-09-26", locate=locate, chrome="/f", runner=TR.Runner())["status"] == "skipped"
    assert P.run_pdf("999", system, base, "2026-09-26", locate=locate, chrome="/f", runner=TR.Runner())["status"] == "skipped"
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert P.run_pdf("215", system, base, "2026-09-26", locate=broken, chrome="/f", runner=TR.Runner())["status"] == "error"


def test_job_files_never_count_as_intel_documents_for_the_intel_index_or_the_next_job(tmp_path):
    import intel_index as II
    system, base, role, locate = world(tmp_path)
    J.run_job("215", system, base, "2026-09-26", locate=locate)
    J.run_job("215", system, base, "2026-09-26", after=True, locate=locate)
    names = os.listdir(role / "20 Vorbereitung")
    assert any(n.startswith("Recherche_Auftrag") for n in names) and not any(II.classify(n) for n in names if n.endswith(".md") and "Auftrag" in n)
    assert J.existing_docs(role) == {}
    assert II.classify("Debrief_Acme_AG_2026-09-26.md") is None


# ---- review fix pass -------------------------------------------------------------------------------------------------
def test_strategy_kind_matches_only_the_generated_document_name():
    import intel_index as II
    assert II.classify("Acme_AG_Strategy_Doc_2026-09-22_v1.pdf") == "strategy" and II.classify("Acme Strategy Doc.md") == "strategy"
    for other in ("Acme_Corporate_Strategy_Document_2025.pdf", "Exit strategy doc.md", "Acme_Strategy_Paper.pdf", "IT_Strategy_Roadmap.pdf"):
        assert II.classify(other) is None, other


def test_the_after_interview_job_updates_the_current_document_and_adds_the_stage_document(tmp_path, capsys):
    system, base, role, locate = world(tmp_path, stage="Final")
    write_doc(role, BRIEFING, 1)
    res = J.run_job("215", system, base, "2026-09-26", after=True, locate=locate)
    t = open(res["file"], encoding="utf-8").read()
    assert res["doc"] == "briefing" and res["version"] == 2 and "Änderungen seit v1" in t and "Acme_AG_Briefing_2026-09-26_v2.md" in t
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        J.main(["--uid", "215", "--after-interview", "--system", system, "--base-dir", base, "--today", "2026-09-26", "--force"])
    out = capsys.readouterr().out
    assert "Briefing v2" in out and "Strategy-Dokument v1" in out
    strat = open(role / "20 Vorbereitung" / "Nachbereitung_Auftrag_Acme_AG_Konzept.md", encoding="utf-8").read()
    assert "Änderungen seit" not in strat and "Strategy_Doc_2026-09-26_v1.md" in strat
    system2, base2, role2, locate2 = world(tmp_path / "n", stage="Interviewing")
    first = J.run_job("215", system2, base2, "2026-09-26", after=True, locate=locate2)
    assert first["version"] == 1 and "Änderungen seit" not in open(first["file"], encoding="utf-8").read()


def test_citation_styles_tags_and_html_are_not_placeholders():
    for ok in ("[FACT] Umsatz 1 Mrd. EUR [1]", "[Geschäftsbericht 2025][1]", "Quelle [Transkript 00:14:20]", "Fußnote<sup>1</sup> und <br> <b>fett</b>", "[Link](https://example.org) <https://example.org/x> <a@b.de>",
               "[INFERENCE] Der CFO ist Sponsor"):
        assert "placeholder" not in rules(lint(BRIEFING + "\n" + ok + "\n")), ok
    for bad in ("[FIRMA] sucht", "<Rolle> bei X", "TODO nachtragen", "[COMPANY]"):
        assert "placeholder" in rules(lint(BRIEFING + "\n" + bad + "\n"), "fail"), bad


def test_only_the_sources_heading_is_the_source_list_and_the_h1_is_no_section():
    body = BRIEFING.replace("## Strategie und Finanzbild", "## Datenquellen und Systemlandschaft\nFACT: Zwei ERP-Systeme [1].\n\n## Strategie und Finanzbild")
    assert lint(body) == []
    numbered = BRIEFING.replace("## Quellen", "## 7. Quellen")
    assert lint(numbered) == []
    assert "section" in rules(lint(BRIEFING.replace("## Risiken\n", "# Risiken\n")), "fail")               # only ## and deeper count as sections
    assert "section" in rules(lint(BRIEFING.replace("## Was sie von dieser Rolle brauchen", "## Risiken und Kontrolle")), "fail")


def test_numbers_need_a_source_in_their_paragraph_whatever_the_tag():
    txt = BRIEFING.replace("INFERENCE: Ein Datenbackbone über Standorte hinweg, weil Berichte heute manuell entstehen [1].",
                           "INFERENCE: Der Umsatz liegt bei etwa 480 Mio. EUR und 2.300 Mitarbeitern.")
    assert "number" in rules(lint(txt), "warn")
    assert "number" not in rules(lint(txt.replace("Mitarbeitern.", "Mitarbeitern [1].")))


def test_english_versions_pass_with_english_headings_and_bold_headings():
    for heading in ("## Changes since v1", "## **Änderungen seit v1**", "## 8. Änderungen seit v1"):
        good = BRIEFING + "\n%s\n- Neu: Punkt mit Quelle [1].\n" % heading
        assert lint(good, version=2) == [], heading


def test_source_dates_use_the_access_date_not_a_date_inside_the_url_or_publication():
    src = BRIEFING.replace("1. https://example.org/annual-report abgerufen 2026-09-20", "1. https://example.org/news/2026-05-12-report (veröffentlicht 2026-05-12) abgerufen 2026-09-20")
    assert lint(src) == []


def test_large_hostile_lines_lint_quickly():
    import time
    t = time.time()
    lint(BRIEFING + "\n" + "<ab" * 30000 + "\n" + "[A" * 30000 + "\n")
    assert time.time() - t < 5


def test_today_shows_the_most_advanced_state_and_a_pending_deeper_job_outranks_a_lint_result():
    import today_view as TV
    docs = {"cheat_sheet:": {"doc": "cheat_sheet", "latest": "v1", "versions": {"v1": {"result": "pass"}}}}
    both = {"215": {"docs": docs, "jobs": {"a": {"doc": "cheat_sheet"}, "b": {"doc": "briefing"}}}}
    assert TV._intel_text(both["215"], "") == "Briefing: Auftrag bereit"
    only = {"docs": docs, "jobs": {"a": {"doc": "cheat_sheet"}}}
    assert TV._intel_text(only, "") == "Cheat Sheet v1 · Lint: bestanden"
    two_jobs = {"jobs": {"a": {"doc": "briefing"}, "b": {"doc": "cheat_sheet"}}}
    assert TV._intel_text(two_jobs, "") == "Briefing: Auftrag bereit"


def test_existing_intel_is_found_where_the_intel_index_looks(tmp_path):
    system, base, role, locate = world(tmp_path)
    employer = role.parent
    (employer / "20 Vorbereitung").mkdir(exist_ok=True)
    (employer / "20 Vorbereitung" / "Acme_Briefing_Brandt_2026-09-11.pdf").write_bytes(b"%PDF")
    (role / "Acme_CheatSheet.pdf").write_bytes(b"%PDF")
    assert sorted(J.existing_docs(role)) == ["briefing", "cheat_sheet"]
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"


def test_stage_strings_transcript_names_person_normalisation_and_empty_company_are_handled(tmp_path):
    system, base, role, locate = world(tmp_path, stage=" Interviewing ")
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "written"
    assert not J.TRANSCRIPT.search("Keynote_Acme_CEO.pdf") and not J.TRANSCRIPT.search("Memorandum_of_Understanding.pdf") and J.TRANSCRIPT.search("Mitschrift_Transkript.txt") and J.TRANSCRIPT.search("Notizen Gespräch.md")
    import unicodedata
    write_doc(role, BRIEFING, 2, person=unicodedata.normalize("NFD", "Jürgen Weiß"))
    assert J.next_intel_version(role, "briefing", unicodedata.normalize("NFC", "Jürgen Weiß")) == 3


def test_a_cp1252_pipeline_and_a_corrupt_state_file_are_reported_and_kept(tmp_path, capsys):
    system, base, role, locate = world(tmp_path)
    good = open(os.path.join(system, "pipeline.csv"), "rb").read()
    open(os.path.join(system, "pipeline.csv"), "wb").write(good + "215b,Müller,Rolle,,,Interviewing\n".encode("cp1252"))
    assert J.live_uids(system) == []
    open(os.path.join(system, "pipeline.csv"), "wb").write(good)
    (role / "20 Vorbereitung" / "x").write_text("x")
    open(os.path.join(system, "intel_state.json"), "w", encoding="utf-8").write("{corrupt")
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "written"
    assert any(n.startswith("intel_state.json.corrupt-") for n in os.listdir(system))
    assert isinstance(json.load(open(os.path.join(system, "intel_state.json"), encoding="utf-8")), dict)


def test_the_job_names_the_row_note_and_pdf_exit_code_reports_failed_documents(tmp_path):
    system, base, role, locate = world(tmp_path)
    rows = list(csv.DictReader(open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8")))
    rows[0]["note"] = "Gespräch mit Erika Muster, eigene Mitschrift vom 25.09."
    with open(os.path.join(system, "pipeline.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    t = open(J.run_job("215", system, base, "2026-09-26", locate=locate)["file"], encoding="utf-8").read()
    assert "Zeilennotiz" in t and "Erika Muster" in t
    write_doc(role, BRIEFING.replace("## Risiken", "## X"), 1)
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert P.main(["--uid", "215", "--system", system, "--base-dir", base]) == 1


def test_headhunter_channels_get_no_intel_job_in_the_live_sweep(tmp_path):
    system, base, role, locate = world(tmp_path, stage="Interviewing")
    assert J.live_uids(system) == ["215"]
    open(os.path.join(system, "channels.json"), "w", encoding="utf-8").write(json.dumps({"channels": {"0215": {"type": "headhunter"}}}))
    assert J.live_uids(system) == []
    open(os.path.join(system, "channels.json"), "w", encoding="utf-8").write("{nope")
    assert J.live_uids(system) == ["215"]                                                              # an unreadable file never hides real processes
    open(os.path.join(system, "channels.json"), "w", encoding="utf-8").write(json.dumps({"channels": "x"}))
    assert J.live_uids(system) == ["215"]


# ---- owner decision 2026-10-02: automatic intel orders start at Screening; Applied only on request ---------------------
def test_applied_gets_no_automatic_order_but_one_on_request(tmp_path):
    system, base, role, locate = world(tmp_path, stage="Applied")
    auto = J.run_job("215", system, base, "2026-10-02", locate=locate)
    assert auto["status"] == "skipped" and "auf Zuruf" in auto["reason"] and "--doc" in auto["reason"]
    asked = J.run_job("215", system, base, "2026-10-02", doc="cheat_sheet", locate=locate)
    assert asked["status"] == "written" and asked["doc"] == "cheat_sheet"


def test_the_live_sweep_skips_applied_processes(tmp_path):
    system, base, role, locate = world(tmp_path, stage="Applied")
    assert J.live_uids(system) == []
    system2, _, _, _ = world(tmp_path / "s", stage="Screening")
    assert J.live_uids(system2) == ["215"]



# ---- after-interview orders are written mechanically once the conversation date has passed (RUNBOOK 3j.3) --------------
def _set_row(system, **extra):
    p = os.path.join(system, "pipeline.csv")
    rows = list(csv.DictReader(open(p, newline="", encoding="utf-8")))
    names = list(rows[0].keys()) + [k for k in extra if k not in rows[0]]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=names)
        w.writeheader()
        for r in rows:
            r.update(extra)
            w.writerow(r)


def test_held_sweep_names_a_conversation_only_after_its_date_and_until_a_debrief_exists(tmp_path):
    system, base, role, locate = world(tmp_path, stage="Interviewing")
    _set_row(system, next_action="Gespraech mit Frau X", due="2026-10-14")
    assert J.held_uids(system, base, "2026-10-14", locate=locate) == []                              # on the day itself it may still be ahead
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == ["215"]
    assert J.held_uids(system, base, "2026-10-29", locate=locate) == []                              # older than 14 days: stale data
    (role / "30 Verlauf" / "Debrief_Acme_AG_2026-10-13.md").write_text("x", encoding="utf-8")        # a debrief of an earlier talk does not count
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == ["215"]
    (role / "30 Verlauf" / "Debrief_Acme_AG_2026-10-14.md").write_text("x", encoding="utf-8")
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == []


def test_held_sweep_ignores_other_stages_missing_dates_and_non_conversations(tmp_path):
    system, base, role, locate = world(tmp_path, stage="Screening")
    _set_row(system, next_action="Gespraech", due="2026-10-14")
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == []
    system, base, role, locate = world(tmp_path / "b", stage="Interviewing")
    _set_row(system, next_action="Nachfassen per Mail", due="2026-10-14")
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == []
    _set_row(system, next_action="Gespraech", due="")
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == []
    _set_row(system, next_action="Gespraech", due="kein Datum")
    assert J.held_uids(system, base, "2026-10-15", locate=locate) == []
    assert J.held_uids(system, base, "kaputt", locate=locate) == []


def test_held_flag_writes_the_after_interview_order(tmp_path, capsys):
    system, base, role, locate = world(tmp_path, stage="Interviewing")
    _set_row(system, next_action="Interview Teams", due="2026-10-14")
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert J.main(["--held", "--system", system, "--base-dir", base, "--today", "2026-10-15"]) == 0
    assert "intel_job uid 215: written" in capsys.readouterr().out
    assert any(n.startswith("Nachbereitung_Auftrag_") for n in os.listdir(role / "20 Vorbereitung"))
