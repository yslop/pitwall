import csv, json, os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverage as C
import draft_lint as L
import test_coverage as TC

NARRATIVE = """# Canonical Exit Narrative

## Guardrails — do not deviate from these in any draft
- **Never claim** the candidate "personally led the restructuring programme," or "engineered the dissolution of his own division," or was the architect.
- It is fine to say he managed the transition professionally.
"""

COVERAGE = """# Abdeckung — Müller AG · Head of Data

| # | Anforderung | Art | Einstufung | Fähigkeit | Beleg |
|---|---|---|---|---|---|
| 1 | Mehrjährige Erfahrung in der IT-Strategie | Muss | Proven | IT strategy | CV 2026 |
| 2 | Praktische Kubernetes-Erfahrung im Produktivbetrieb | Muss | Gap |  |  |
| 3 | PMP oder PRINCE2 Zertifizierung | Muss | In progress | PRINCE2 | requested |
"""

MASTER = ["MAX MUSTERMANN", "6.000+ Nutzer weltweit, 56 Standorte, 150 Nutzer im BI", "Hub-and-Spoke Architektur"]

_N = [0]


def make_docx(path, paragraphs):
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paragraphs)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body>%s</w:body></w:document>" % body)


def world(tmp_path, jd=TC.JD, with_narrative=True, with_cov=True):
    base = tmp_path / "career"
    system = base / "_system"
    role = base / "215 Müller AG" / "Head of Data"
    (role / "10 Bewerbung").mkdir(parents=True)
    (role / "20 Vorbereitung").mkdir(parents=True)
    (base / "00 references").mkdir()
    (base / "01 templates").mkdir()
    system.mkdir()
    (system / "capability_profile.md").write_text(TC.PROFILE, encoding="utf-8")
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "folder_id"])
        w.writeheader()
        w.writerow({"uid": "215", "company": "Müller AG", "role": "Head of Data", "folder_id": ""})
    (system / "jd_cache.json").write_text(json.dumps({"215": jd}), encoding="utf-8")
    if with_narrative:
        (base / "00 references" / "Exit_Narrative_AllForLabels_CANONICAL.md").write_text(NARRATIVE, encoding="utf-8")
    make_docx(str(base / "01 templates" / "CV_Executive_v2_MASTER.docx"), MASTER)
    make_docx(str(base / "01 templates" / "CL_Executive_v2_MASTER.docx"), ["Dear [Hiring Manager]"])
    if with_cov:
        (role / "20 Vorbereitung" / "Abdeckung_Müller_AG.md").write_text(COVERAGE, encoding="utf-8")
    (role / "10 Bewerbung" / "Ausschreibung.pdf").write_bytes(b"%PDF x")
    return str(system), str(base), role, (lambda b, u, r, fid="": (role, []))


def ctx_for(tmp_path, **kw):
    _N[0] += 1
    system, base, role, locate = world(tmp_path / ("w%d" % _N[0]), **kw)
    return L.load_context(system, base, "215", role, "de")


def lint(text, tmp_path, kind="CV", **kw):
    return L.lint_text("CV_x_v1.md" if kind == "CV" else "CL_x_v1.md", text, ctx_for(tmp_path, **kw), kind)


def rules(findings, level=None):
    return sorted({f["rule"] for f in findings if level is None or f["level"] == level})


def test_docx_and_markdown_are_read_and_unreadable_files_give_empty_text(tmp_path):
    make_docx(str(tmp_path / "a.docx"), ["Eins", "Zwei"])
    assert L.read_text(str(tmp_path / "a.docx")).split() == ["Eins", "Zwei"]
    (tmp_path / "b.md").write_text("hallo", encoding="utf-8")
    assert L.read_text(str(tmp_path / "b.md")) == "hallo"
    (tmp_path / "c.gdoc").write_bytes(b"\xff\xfe\x00")
    assert L.read_text(str(tmp_path / "c.gdoc")) == "" and L.read_text(str(tmp_path / "missing.md")) == "" and L.read_text(str(tmp_path / "x.docx")) == ""


def test_drafts_are_found_by_name_and_version(tmp_path):
    system, base, role, _ = world(tmp_path)
    b = role / "10 Bewerbung"
    for n in ("CV_Müller_AG_Head_of_Data_v1.md", "CL_Müller_AG_Head_of_Data_v1.md", "CV_Müller_AG_Head_of_Data_v2.md", "CV_notes.md", "Rückmeldung_v1.md"):
        (b / n).write_text("x", encoding="utf-8")
    got = L.find_drafts(role)
    assert sorted(got) == [1, 2] and sorted(got[1]) == ["CL", "CV"] and sorted(got[2]) == ["CV"]


def test_forbidden_phrases_come_from_the_narrative_and_the_defaults():
    ph = L.forbidden_phrases(NARRATIVE)
    assert "personally led the restructuring programme" in ph and "engineered the dissolution of his own division" in ph
    assert "architect of the elimination" in ph and L.forbidden_phrases("") == sorted(L.FORBIDDEN_DEFAULT)


def test_certifications_must_match_the_profile_status(tmp_path):
    f = lint("PMP-zertifiziert mit langjähriger Erfahrung.", tmp_path)
    assert [x["rule"] for x in f if x["level"] == "fail"] == ["certification"] and "lapsed" in f[0]["text"]
    assert not rules(lint("PMP (zertifiziert bis 2019).", tmp_path), "fail")
    assert not rules(lint("Splunk Architect, höchste Stufe.", tmp_path), "fail")                       # held
    assert not rules(lint("ITIL 5 Foundation: Prüfung geplant am 02.10.2026.", tmp_path), "fail")        # in progress with a date
    assert rules(lint("ITIL 5 Foundation zertifiziert.", tmp_path), "fail") == ["certification"]         # in progress claimed as held
    assert rules(lint("TOGAF 9 zertifiziert.", tmp_path), "fail") == ["certification"]                   # not in the profile


def test_exit_narrative_phrases_fail_in_any_case(tmp_path):
    f = lint("I Personally Led the Restructuring Programme at the company.", tmp_path)
    assert rules(f, "fail") == ["exit-narrative"]
    assert not rules(lint("Managed the transition professionally and ensured continuity.", tmp_path), "fail")


def test_gap_terms_from_the_coverage_table_are_warned_not_failed(tmp_path):
    f = lint("Ich bringe tiefe Kubernetes-Expertise mit.", tmp_path)
    assert rules(f) == ["gap-claim"] and rules(f, "fail") == []
    assert not lint("Ich führe Datenteams und verantworte die IT-Strategie.", tmp_path)


def test_numbers_with_units_must_appear_in_an_evidence_text(tmp_path):
    assert not lint("6.000+ Nutzer weltweit und 56 Standorte begleitet.", tmp_path)                    # in the master
    f = lint("Verantwortung für 44 Standorte und 900 Mitarbeitende.", tmp_path)
    assert rules(f) == ["number"] and len(f) == 2
    assert not lint("Seit 2019 tätig; Jahrgang 1980.", tmp_path)                                       # bare numbers are not claims


def test_placeholders_length_greeting_and_language(tmp_path):
    assert rules(lint("Sehr geehrte Damen und Herren, [FIRMA] sucht <Rolle>. TODO", tmp_path, "CL"), "fail") == ["placeholder"]
    assert "greeting" in rules(lint("Sehr geehrte Damen und Herren", tmp_path, "CL"))
    long_cl = "Wort " * 450
    assert rules(lint(long_cl, tmp_path, "CL")) == ["length"] and rules(lint(long_cl, tmp_path, "CL"), "fail") == []
    assert rules(lint("Wort " * 750, tmp_path, "CL"), "fail") == ["length"]
    assert "length" not in rules(lint(long_cl, tmp_path, "CV"))                                        # length applies to the letter only
    en = "The candidate leads teams and delivers the strategy for the whole company with the board and the group."
    assert "language" in rules(lint(en, tmp_path))                                                     # context language is 'de'


def test_missing_inputs_are_warned_not_guessed(tmp_path):
    system, base, role, _ = world(tmp_path, with_narrative=False, with_cov=False)
    ctx = L.load_context(system, base, "215", role, "de")
    status, findings = L.lint_drafts({"CV_x_v1.md": "Ein harmloser Satz über Führung."}, ctx)
    assert status == "warn" and sum(f["rule"] == "input" for f in findings) == 2
    assert L.lint_drafts({"CV_x_v1.md": "Ein harmloser Satz über Führung."}, ctx)[0] == "warn"


def test_status_pass_warn_fail_and_the_report(tmp_path):
    ctx = ctx_for(tmp_path)
    assert L.lint_drafts({"CV_x_v1.md": "Ich führe Datenteams."}, ctx)[0] == "pass"
    s, f = L.lint_drafts({"CV_x_v1.md": "PMP-zertifiziert. Kubernetes-Erfahrung."}, ctx)
    assert s == "fail" and L.render_report("v1", s, f).splitlines()[0] == "Lint v1: Fehler (1 Fehler, 1 Warnungen)"


def write_drafts(role, cv, cl=None, version=1):
    b = role / "10 Bewerbung"
    (b / ("CV_Müller_AG_Head_of_Data_v%d.md" % version)).write_text(cv, encoding="utf-8")
    if cl is not None:
        (b / ("CL_Müller_AG_Head_of_Data_v%d.md" % version)).write_text(cl, encoding="utf-8")


def test_run_lint_records_the_result_and_keeps_earlier_versions(tmp_path):
    system, base, role, locate = world(tmp_path)
    write_drafts(role, "Ich führe Datenteams.", "Guten Tag Frau Meier, ich freue mich auf das Gespräch über die Rolle als Head of Data in Ihrem Team.")
    res = L.run_lint("215", system, base, "2026-09-26", locate=locate)
    assert res["status"] == "pass" and res["version"] == "v1"
    write_drafts(role, "PMP-zertifiziert.", None, version=2)
    res2 = L.run_lint(215, system, base, "2026-09-27", locate=locate)
    assert res2["status"] == "fail" and res2["version"] == "v2"
    st = json.load(open(os.path.join(system, "draft_state.json"), encoding="utf-8"))["215"]
    assert st["latest"] == "v2" and st["versions"]["v1"]["result"] == "pass" and st["versions"]["v2"]["fails"] == 1
    assert L.run_lint("215", system, base, "2026-09-27", version="v1", locate=locate)["version"] == "v1"


def test_run_lint_dry_run_writes_nothing_and_missing_things_are_reported(tmp_path):
    system, base, role, locate = world(tmp_path)
    assert L.run_lint("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"          # no drafts yet
    write_drafts(role, "Ich führe Datenteams.")
    assert L.run_lint("215", system, base, "2026-09-26", dry_run=True, locate=locate)["status"] == "pass"
    assert not os.path.exists(os.path.join(system, "draft_state.json"))
    assert L.run_lint("215", system, base, "2026-09-26", version="v9", locate=locate)["status"] == "skipped"
    assert L.run_lint("999", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert L.run_lint("215", system, base, "2026-09-26", locate=broken)["status"] == "error"


def test_cli_exit_codes(tmp_path, capsys):
    system, base, role, locate = world(tmp_path)
    write_drafts(role, "PMP-zertifiziert.")
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert L.main(["--uid", "215", "--system", system, "--base-dir", base, "--today", "2026-09-26", "--dry-run"]) == 2
        assert "FEHLER certification" in capsys.readouterr().out
        write_drafts(role, "Ich führe Datenteams.")
        assert L.main(["--uid", "215", "--system", system, "--base-dir", base, "--dry-run"]) == 0
        assert L.main(["--uid", "999", "--system", system, "--base-dir", base, "--dry-run"]) == 4


import draft_job as J


def job(tmp_path, **kw):
    system, base, role, locate = world(tmp_path, **kw)
    return system, base, role, locate


def test_the_job_file_is_self_contained_and_lists_every_input_the_rules_and_the_lint_command(tmp_path):
    system, base, role, locate = job(tmp_path)
    res = J.run_job("215", system, base, "2026-09-26", locate=locate)
    assert res["status"] == "written" and res["version"] == 1
    text = open(res["file"], encoding="utf-8").read()
    assert text.startswith("# Entwurfsauftrag — Müller AG · Head of Data") and "Sprache der Entwürfe: **Deutsch, Sie-Form**" in text
    for path in ("Ausschreibung.pdf", "CV_Executive_v2_MASTER.docx", "capability_profile.md", "Abdeckung_Müller_AG.md", "Exit_Narrative_AllForLabels_CANONICAL.md"):
        assert path in text
    assert "← FEHLT" not in text.split("## Anforderungen")[0].replace("(noch kein CV_CL_Input_Brief)", "")                    # every named file exists
    assert "| Praktische Kubernetes-Erfahrung im Produktivbetrieb | Muss | Gap |" in text and "Nichts wird gesendet" in text
    assert "CV_Müller_AG_Head_of_Data_v1.md" in text and "draft_lint.py --uid 215 --version v1" in text
    assert "Überschreibe nie eine frühere Version" in text and "Änderungen_v<N+1>.md" in text and "Never claim" in text
    st = json.load(open(os.path.join(system, "draft_state.json"), encoding="utf-8"))["215"]
    assert st["job"]["version"] == 1 and st["job"]["language"] == "de"


def test_missing_inputs_are_marked_and_english_postings_get_english_drafts(tmp_path):
    en = "Requirements\n- 10+ years leading enterprise data and analytics teams in a listed group\n- Experience with the board and the CFO on strategy and budget\n"
    system, base, role, locate = job(tmp_path, jd=en)
    os.remove(os.path.join(base, "01 templates", "CL_Executive_v2_MASTER.docx"))
    text = open(J.run_job("215", system, base, "2026-09-26", locate=locate)["file"], encoding="utf-8").read()
    assert "**English**" in text and "CL_Executive_v2_MASTER.docx`  ← FEHLT" in text and "CV_Executive_v2_MASTER.docx`  ← FEHLT" not in text


def test_without_a_coverage_table_nothing_is_written_and_the_reason_is_named(tmp_path):
    system, base, role, locate = job(tmp_path, with_cov=False)
    res = J.run_job("215", system, base, "2026-09-26", locate=locate)
    assert res["status"] == "skipped" and "coverage.py" in res["reason"] and not os.path.exists(os.path.join(system, "draft_state.json"))


def test_the_job_file_is_current_until_the_target_version_changes_and_feedback_moves_it_to_v2(tmp_path):
    system, base, role, locate = job(tmp_path)
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "written"
    assert J.run_job("215", system, base, "2026-09-27", locate=locate)["status"] == "current"
    b = role / "10 Bewerbung"
    (b / "CV_Müller_AG_Head_of_Data_v1.md").write_text("Ich führe Datenteams.", encoding="utf-8")
    res = J.run_job("215", system, base, "2026-09-28", locate=locate)
    assert res["status"] == "current" and res["version"] == 1                                            # drafts exist, no feedback yet: still v1 work
    (b / "Rückmeldung_v1.md").write_text("Bitte kürzer.", encoding="utf-8")
    res = J.run_job("215", system, base, "2026-09-29", locate=locate)
    assert res["status"] == "written" and res["version"] == 2
    text = open(res["file"], encoding="utf-8").read()
    assert "Zu schreibende Version: **v2**" in text and "Rückmeldung vorhanden: Rückmeldung_v1.md" in text and "CV_Müller_AG_Head_of_Data_v2.md" in text
    assert (b / "CV_Müller_AG_Head_of_Data_v1.md").read_text(encoding="utf-8") == "Ich führe Datenteams."     # v1 untouched


def test_the_last_lint_result_is_carried_into_a_regenerated_job_file(tmp_path):
    system, base, role, locate = job(tmp_path)
    J.run_job("215", system, base, "2026-09-26", locate=locate)
    (role / "10 Bewerbung" / "CV_Müller_AG_Head_of_Data_v1.md").write_text("PMP-zertifiziert.", encoding="utf-8")
    L.run_lint("215", system, base, "2026-09-27", locate=locate)
    (role / "10 Bewerbung" / "Rückmeldung_v1.md").write_text("Bitte korrigieren.", encoding="utf-8")
    text = open(J.run_job("215", system, base, "2026-09-28", locate=locate)["file"], encoding="utf-8").read()
    assert "Letztes Lint-Ergebnis: v1: Fehler (1 Fehler, 0 Warnungen)" in text


def test_job_dry_run_force_and_error_reporting(tmp_path, capsys):
    system, base, role, locate = job(tmp_path)
    res = J.run_job("215", system, base, "2026-09-26", dry_run=True, locate=locate)
    assert res["status"] == "written" and res["text"].startswith("# Entwurfsauftrag") and not os.path.exists(os.path.join(system, "draft_state.json"))
    J.run_job("215", system, base, "2026-09-26", locate=locate)
    assert J.run_job("215", system, base, "2026-09-27", force=True, locate=locate)["status"] == "written"
    assert J.run_job("999", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert J.run_job("215", system, base, "2026-09-26", locate=broken)["status"] == "error"


def test_the_job_file_entry_and_the_lint_entry_share_one_state_record(tmp_path):
    system, base, role, locate = job(tmp_path)
    J.run_job("215", system, base, "2026-09-26", locate=locate)
    (role / "10 Bewerbung" / "CV_Müller_AG_Head_of_Data_v1.md").write_text("Ich führe Datenteams.", encoding="utf-8")
    L.run_lint("215", system, base, "2026-09-27", locate=locate)
    st = json.load(open(os.path.join(system, "draft_state.json"), encoding="utf-8"))["215"]
    assert st["job"]["version"] == 1 and st["latest"] == "v1" and st["versions"]["v1"]["result"] == "pass"


def test_job_cli_pinned_writes_for_pinned_rows_only(tmp_path, capsys):
    system, base, role, locate = job(tmp_path)
    open(os.path.join(system, "top10.json"), "w", encoding="utf-8").write(json.dumps({"pinned": [215, 300]}))
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert J.main(["--pinned", "--system", system, "--base-dir", base, "--today", "2026-09-26"]) == 0
    out = capsys.readouterr().out
    assert "draft_job uid 215: written · v1" in out and "draft_job uid 300: skipped" in out


# ---- review fix pass ------------------------------------------------------------------------------
def test_a_hedge_must_sit_next_to_the_certificate_and_match_whole_words(tmp_path):
    for bad in ("PMP-certified leader who targeted cost savings.", "PMP-certified, for example in SAP roll-outs.", "PMP-zertifizierter Programmleiter, bis 2030 Ziel: Cloud-first.",
                "Zertifikate: PMP (bis 2019), ITIL 5 Foundation, PRINCE2"):
        assert "certification" in rules(lint(bad, tmp_path), "fail"), bad
    for ok in ("PMP (2012 – 2019), zertifiziert.", "Zertifikate: PMP (bis 2019); ITIL 5 Foundation (in Vorbereitung); PRINCE2 (beantragt).", "PMP-zertifiziert bis 2019."):
        assert not rules(lint(ok, tmp_path), "fail"), ok


def test_bullets_under_a_certification_heading_count_and_methods_named_in_prose_do_not(tmp_path):
    assert rules(lint("Zertifizierungen:\n- PMP\n- ITIL 5 Foundation\n", tmp_path), "fail") == ["certification"]
    assert not rules(lint("Zertifizierungen:\n- PMP (bis 2019)\n- ITIL 5 Foundation (in Vorbereitung)\n", tmp_path), "fail")
    for method in ("Einführung von ITIL-Prozessen im Betrieb.", "Led a SAFe transformation across four programmes.", "IT-Governance nach COBIT und ISO 27001."):
        assert not rules(lint(method, tmp_path), "fail"), method


def test_prince2_in_mixed_case_is_recognised(tmp_path):
    assert rules(lint("Prince2 zertifiziert.", tmp_path), "fail") == ["certification"]


def test_german_and_line_broken_exit_narrative_claims_fail(tmp_path):
    assert rules(lint("Ich habe die Restrukturierung persönlich geleitet.", tmp_path), "fail") == ["exit-narrative"]
    assert rules(lint("I personally led the\nrestructuring programme at the group.", tmp_path), "fail") == ["exit-narrative"]
    assert not rules(lint("Ich habe den Übergang professionell gesteuert und Kontinuität gesichert.", tmp_path), "fail")


def test_unreadable_drafts_and_missing_evidence_never_pass_silently(tmp_path):
    system, base, role, locate = world(tmp_path)
    b = role / "10 Bewerbung"
    (b / "CV_Müller_AG_Head_of_Data_v1.md").write_bytes("PMP-zertifiziert, TODO [FIRMA]".encode("cp1252") + b"\xfc")
    (b / "CL_Müller_AG_Head_of_Data_v1.md").write_text("", encoding="utf-8")
    res = L.run_lint("215", system, base, "2026-09-26", locate=locate)
    assert res["status"] == "fail" and {"unreadable"} <= {f["rule"] for f in res["findings"]}
    (tmp_path / "w2").mkdir()
    system, base, role, locate = world(tmp_path / "w2")
    (role / "10 Bewerbung" / "CV_x_v1.md").mkdir()
    write_drafts(role, "Ich führe Datenteams.")
    assert L.run_lint("215", system, base, "2026-09-26", locate=locate)["status"] == "pass"                   # the directory is not a draft
    for name in os.listdir(os.path.join(base, "01 templates")):
        os.remove(os.path.join(base, "01 templates", name))
    ctx = L.load_context(system, base, "215", role, "de")
    assert any("MASTER" in m for m in ctx["missing"])
    (role / "20 Vorbereitung" / "Abdeckung_Müller_AG.md").write_bytes(b"\xff\xfe\x00")
    assert any("Abdeckung" in m for m in L.load_context(system, base, "215", role, "de")["missing"])


def test_hostile_draft_state_never_crashes_today_the_job_file_or_the_lint(tmp_path):
    import today_view as TV
    for bad in ({"215": {"latest": ["v1"], "versions": {}}}, {"215": {"latest": "v1", "versions": {"v1": "pass"}}}, {"215": {"job": "x"}}, {"215": {"versions": {"vX": {}, "old": 1}, "latest": "vX"}}):
        TV.build_context([{"uid": "215", "company": "A", "role": "B", "stage": "Watchlist", "note": ""}], None, "2026-09-26", top10={"pinned": [215]}, drafts=bad)
        system, base, role, locate = world(tmp_path / ("h%d" % id(bad)))
        open(os.path.join(system, "draft_state.json"), "w", encoding="utf-8").write(json.dumps(bad))
        write_drafts(role, "Ich führe Datenteams.")
        assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] in ("written", "current")
        assert J.run_job("215", system, base, "2026-09-27", locate=locate)["status"] in ("written", "current")
        assert L.run_lint("215", system, base, "2026-09-26", locate=locate)["status"] == "pass"
        assert json.load(open(os.path.join(system, "draft_state.json"), encoding="utf-8"))["215"]["latest"] == "v1"


def test_inflected_units_currencies_and_team_sizes_are_claims(tmp_path):
    for claim in ("an 57 Standorten", "mit 151 Mitarbeitern", "für 152 Mitarbeitende", "in 13 Ländern", "für 7.000 Nutzern", "81 Systemen", "31 Prozent",
                  "Team of 26 engineers", "Team von 27 Personen", "$3M budget", "€4bn revenue", "EUR 8 Mio.", "78 direct reports"):
        assert "number" in rules(lint("Ich verantwortete " + claim + " weltweit.", tmp_path)), claim
    assert not lint("Ich verantwortete 56 Standorte und 6.000+ Nutzer, 150 Nutzer im BI.", tmp_path)


def test_numbers_only_the_table_copied_from_the_posting_or_the_index_do_not_count_as_evidence(tmp_path):
    md = "| # | Anforderung | Art | Einstufung | Fähigkeit | Beleg |\n|---|---|---|---|---|---|\n| 12 | 10+ Jahre Erfahrung | Muss | Proven | IT strategy | CV 2026; 77 Projekte |\n"
    assert "77" in L.coverage_evidence(md) and "10+" not in L.coverage_evidence(md) and "| 12 |" not in L.coverage_evidence(md)
    assert "number" in rules(lint("Ich habe 12 Länder betreut.", tmp_path))
    assert "number" in rules(lint("Ich bringe 10+ Jahre Erfahrung mit.", tmp_path))                          # copied from the posting row


def test_markdown_links_emails_and_urls_are_not_placeholders(tmp_path):
    ok = "[LinkedIn](https://example.org/in/x) und <max@example.com> sowie <https://example.org/x>."
    assert not rules(lint(ok, tmp_path), "fail")
    assert rules(lint("Bewerbung als [ROLE] bei [COMPANY] <Rolle> TODO", tmp_path), "fail") == ["placeholder"]
    assert not rules(lint("Meine to-do Liste und das todo-Board sind kein Platzhalter.", tmp_path), "fail")


def test_gap_terms_match_whole_words_and_use_the_full_evidence(tmp_path):
    assert "gap-claim" in rules(lint("Kubernetes-Erfahrung im Betrieb.", tmp_path))
    assert "gap-claim" not in rules(lint("Kubernetesbasierte Plattformen leiten.", tmp_path))                  # no substring hits inside longer words
    assert "gap-claim" not in rules(lint("Die Studium der Modernisierung war teil des Programms.", tmp_path))


def test_cover_letter_length_ignores_links_and_addresses(tmp_path):
    filler = "Wort " * 380 + "max.mustermann@example.org https://example.org/" + "seite/" * 30 + " +49 160 1234567"
    assert "length" not in rules(lint(filler, tmp_path, "CL"))


def test_feedback_file_variants_move_the_target_and_are_not_listed_as_postings(tmp_path):
    for i, name in enumerate(("Rückmeldung_v1.md", "Rueckmeldung_v1.md", "Rückmeldung v1.gdoc", "Rückmeldung_v1.docx")):
        system, base, role, locate = world(tmp_path / ("f%d" % i))
        (role / "10 Bewerbung" / "CV_Müller_AG_Head_of_Data_v1.md").write_text("Ich führe Datenteams.", encoding="utf-8")
        (role / "10 Bewerbung" / name).write_text("Bitte kürzer.", encoding="utf-8")
        res = J.run_job("215", system, base, "2026-09-26", locate=locate)
        text = open(res["file"], encoding="utf-8").read()
        assert res["version"] == 2, name
        assert "Ausschreibung (Original, nicht ändern):\n  - `%s" % role not in text.replace("Ausschreibung.pdf", "") or name.split(".")[0] not in text.split("## Anforderungen")[0].split("Master")[0]


def test_the_job_file_says_when_the_target_version_already_exists_and_carries_no_personal_names(tmp_path):
    system, base, role, locate = world(tmp_path)
    (role / "10 Bewerbung" / "CV_Müller_AG_Head_of_Data_v1.md").write_text("Ich führe Datenteams.", encoding="utf-8")
    text = open(J.run_job("215", system, base, "2026-09-26", locate=locate)["file"], encoding="utf-8").read()
    assert "existiert bereits" in text and "Testvorname" not in text


def test_a_changed_input_makes_the_job_file_stale(tmp_path):
    system, base, role, locate = world(tmp_path)
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] == "written"
    assert J.run_job("215", system, base, "2026-09-27", locate=locate)["status"] == "current"
    (role / "20 Vorbereitung" / "Abdeckung_Müller_AG.md").write_text(COVERAGE + "| 4 | Neue Zeile mit genug Text | Muss | Proven | IT | CV |\n", encoding="utf-8")
    assert J.run_job("215", system, base, "2026-09-28", locate=locate)["status"] == "written"


def test_rows_with_empty_fields_are_reported_not_raised(tmp_path):
    system, base, role, locate = world(tmp_path)
    with open(os.path.join(system, "pipeline.csv"), "w", newline="", encoding="utf-8") as f:
        f.write("uid,company,role,folder_id\n215,,,\n")
    assert J.run_job("215", system, base, "2026-09-26", locate=locate)["status"] in ("written", "skipped", "error")
    write_drafts(role, "Ich führe Datenteams.")
    assert L.run_lint("215", system, base, "2026-09-26", locate=locate)["status"] in ("pass", "warn", "skipped", "error")
