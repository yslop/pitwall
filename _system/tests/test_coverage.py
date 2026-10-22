import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverage as C
import pytest
PROFILE = """# Capability profile

reviewed: 2026-09-25

## Coverage-gate thresholds (defaults)
proven_share_must_haves: 0.60

## Capabilities
| Capability | current | target | direction | evidence |
|---|---|---|---|---|
| IT strategy and enterprise architecture (hub-and-spoke) | 3 | 3 | hold | CV 2026; CFO letter |
| P&L ownership | 2 | 3 | grow | qualitative only |
| Budget ownership (IT) | 2 | 3 | grow | CV 2026 |
| Hands-on engineering (Python, SQL) | 1 | 1 | hold | CV states not hands-on |
| Unbelegt | 2 | 2 | hold |  |

## Certifications
| Certification | status | date / note |
|---|---|---|
| Splunk Architect (highest level) | held | 2015-2016 |
| PMP | lapsed | certified until 2019 |
| ITIL 5 Foundation | in progress | exam target 2026-10-02 |
| PRINCE2 | requested | start by 2026-10-15 |

## Roles
strongest: x
"""
JD = """Head of Data

Ihre Aufgaben:
- Sie führen das Datenteam und verantworten die Roadmap gemeinsam mit dem Vorstand

Ihr Profil:
- Mehrjährige Erfahrung in der IT-Strategie und Enterprise Architecture
- Budgetverantwortung für einen zweistelligen Millionenbetrag
- PMP oder PRINCE2 Zertifizierung
- Praktische Erfahrung mit Python und SQL im Produktivbetrieb
- Nice to have: ITIL Foundation Zertifikat

Wir bieten:
- Ein tolles Team und flexible Arbeitszeiten für alle Beteiligten
"""


def profile(tmp_path, text=PROFILE):
    p = tmp_path / "capability_profile.md"
    p.write_text(text, encoding="utf-8")
    return C.load_profile(str(p))


def test_profile_parses_thresholds_capabilities_and_certifications(tmp_path):
    p = profile(tmp_path)
    assert p["threshold"] == 0.60 and p["reviewed"] == "2026-09-25"
    assert [c["level"] for c in p["capabilities"]] == [3, 2, 2, 1, 2]
    assert p["capabilities"][1]["name"] == "P&L ownership" and p["capabilities"][1]["evidence"] == "qualitative only"
    assert [(c["name"], c["status"]) for c in p["certs"]][:2] == [("Splunk Architect (highest level)", "held"), ("PMP", "lapsed")]


def test_a_missing_profile_is_none_and_a_missing_threshold_defaults(tmp_path):
    assert C.load_profile(str(tmp_path / "nope.md")) is None
    assert profile(tmp_path, PROFILE.replace("proven_share_must_haves: 0.60", ""))["threshold"] == C.DEFAULT_THRESHOLD


def test_requirements_come_from_the_profile_section_only_and_nice_to_have_is_marked():
    reqs = C.extract_requirements(JD)
    texts = [r["text"] for r in reqs]
    assert not any("Datenteam" in t or "tolles Team" in t for t in texts)                # tasks and offers are not requirements
    assert [r["kind"] for r in reqs] == ["must"] * 4 + ["nice"]
    assert texts[0].startswith("Mehrjährige Erfahrung")


def test_english_headings_and_bullets_without_headings():
    en = "Requirements\n• 10+ years in enterprise data and AI leadership roles\n• Experience with P&L management in a listed group\nBenefits\n• Free coffee and a nice office space"
    assert [r["text"][:8] for r in C.extract_requirements(en)] == ["10+ year", "Experien"]
    bare = "Some intro text that is long enough to be a line.\n- Own the data strategy end to end for the group\n- Nice to have: cloud architecture experience"
    assert [r["kind"] for r in C.extract_requirements(bare)] == ["must", "nice"]


def test_no_requirements_found_is_an_empty_list_and_duplicates_and_cap_hold():
    assert C.extract_requirements("Kein Text mit Struktur, nur ein langer Absatz ohne Listen und ohne Überschriften.") == []
    many = "Requirements\n" + "\n".join("- Anforderung Nummer %d mit genug Text" % n for n in range(40)) + "\n- Anforderung Nummer 1 mit genug Text"
    assert len(C.extract_requirements(many)) == C.MAX_REQS


def test_certifications_are_checked_against_the_profile_without_a_model(tmp_path):
    p = profile(tmp_path)
    assert C.cert_verdict("PMP-Zertifizierung", p)[0] == C.GAP                                        # lapsed
    assert C.cert_verdict("PRINCE2 Practitioner Zertifizierung", p)[0] == C.IN_PROGRESS and "2026-10-15" in C.cert_verdict("PRINCE2 Zertifizierung", p)[2]
    assert C.cert_verdict("ITIL Foundation Zertifikat", p)[0] == C.IN_PROGRESS
    assert C.cert_verdict("Splunk certified architect", p)[0] == C.PROVEN
    assert C.cert_verdict("TOGAF 9 Zertifizierung", p)[0] == C.GAP and C.cert_verdict("TOGAF 9 Zertifizierung", p)[2] == "nicht im Profil"
    assert C.cert_verdict("Führungserfahrung", p) is None


def test_a_cert_term_inside_another_word_does_not_match(tmp_path):
    assert C.cert_verdict("Zertifizierung: Kenntnisse der SAFEty Standards", profile(tmp_path)) is None
    assert C.cert_verdict("PMPX Zertifikat", profile(tmp_path)) is None


def fake_judge(answers):
    def judge(items, prof):
        return {i: answers.get(text[:6], {"cap": None, "cover": 0}) for i, text in items}
    return judge


def test_classification_bar_is_level_two_with_evidence_and_real_coverage():
    strong = {"level": 3, "evidence": "CV 2026"}
    assert C.classify(strong, 3) == C.PROVEN and C.classify(strong, 2) == C.PROVEN
    assert C.classify(strong, 1) == C.ADJACENT and C.classify(strong, 0) == C.GAP
    assert C.classify({"level": 1, "evidence": "CV"}, 3) == C.ADJACENT                                 # basic level never proves
    assert C.classify({"level": 2, "evidence": " "}, 3) == C.ADJACENT                                  # no named evidence never proves
    assert C.classify(None, 3) == C.GAP


def test_rows_mix_certificates_and_model_verdicts_and_keep_the_order(tmp_path):
    p = profile(tmp_path)
    reqs = C.extract_requirements(JD)
    rows = C.build_rows(reqs, p, fake_judge({"Mehrjä": {"cap": 0, "cover": 3}, "Budget": {"cap": 2, "cover": 2}, "Prakti": {"cap": 3, "cover": 2}}))
    assert [r["state"] for r in rows] == [C.PROVEN, C.PROVEN, C.IN_PROGRESS, C.ADJACENT, C.IN_PROGRESS]
    assert rows[3]["cap"].startswith("Hands-on") and rows[2]["cap"] == "PRINCE2"              # 'PMP oder PRINCE2': the best of them counts


def test_a_model_failure_returns_an_error_and_no_rows(tmp_path):
    assert C.build_rows(C.extract_requirements(JD), profile(tmp_path), lambda items, prof: {"error": "down"}) == {"error": "down"}


def test_summary_share_threshold_and_hard_gaps(tmp_path):
    rows = [{"text": "a", "kind": "must", "state": C.PROVEN}, {"text": "b", "kind": "must", "state": C.GAP},
            {"text": "PMP zertifiziert", "kind": "must", "state": C.GAP, "cert": True}, {"text": "n", "kind": "nice", "state": C.GAP}]
    s = C.summarise(rows, 0.6)
    assert s["must"] == 3 and s["proven"] == 1 and round(s["share"], 2) == 0.33 and s["below"] and s["hard_gaps"] == ["PMP zertifiziert"]
    assert C.summarise([{"text": "n", "kind": "nice", "state": C.GAP}], 0.6)["share"] is None
    assert not C.summarise([{"text": "a", "kind": "must", "state": C.PROVEN}], 0.6)["below"]


def test_markdown_carries_the_table_the_share_and_never_blocks(tmp_path):
    p = profile(tmp_path)
    rows = C.build_rows(C.extract_requirements(JD), p, fake_judge({}))
    md = C.render_markdown("Müller AG", "Head of Data", "2026-09-26", p, rows, C.summarise(rows, 0.6))
    assert md.startswith("# Abdeckung — Müller AG · Head of Data") and "berät, blockiert nicht" in md and "| 1 | Mehrjährige" in md
    assert "Unter der Schwelle" in md and "0 % der Muss-Anforderungen" in md and md.count("\n| ") >= 6
    hard = C.render_markdown("X", "Y", "2026-09-26", p, [{"text": "TOGAF 9", "kind": "must", "state": C.GAP, "cap": "TOGAF", "evidence": "nicht im Profil"}], C.summarise([{"text": "TOGAF 9", "kind": "must", "state": C.GAP, "cert": True}], 0.6))
    assert "Hinweis, harte Lücken" in hard and "- TOGAF 9" in hard


def test_the_model_call_sends_names_levels_and_evidence_only_in_batches(tmp_path, monkeypatch):
    p = profile(tmp_path)
    sent = []
    class Resp:
        def __init__(s, body): s.body = body
        def read(s): return s.body
        def __enter__(s): return s
        def __exit__(s, *a): return False
    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data)
        sent.append(payload)
        answers = {}
        for q in payload["questions"]:
            answers[q] = {"choice": "c0"} if q.startswith("cap") else {"score": 2.4}
        return Resp(json.dumps({"answers": answers}).encode())
    monkeypatch.setattr(C.urllib.request, "urlopen", fake_urlopen)
    items = [(i, "Anforderung %d" % i) for i in range(7)]
    out = C.jev_judge(items, p, api_key="k")
    assert len(sent) == 2 and len(sent[0]["questions"]) == 10 and len(sent[1]["questions"]) == 4
    assert out[3] == {"cap": 0, "cover": 2} and set(out) == set(range(7))
    assert "hub-and-spoke" in sent[0]["state"] and "evidence: yes" in sent[0]["state"] and "CV 2026" not in sent[0]["state"]
    assert "none" in sent[0]["questions"]["cap0"]["criteria"]


def test_the_model_call_reports_errors_and_a_missing_key(tmp_path, monkeypatch):
    p = profile(tmp_path)
    monkeypatch.setattr(C, "get_typesafe_api_key", lambda: "")
    assert C.jev_judge([(0, "x" * 20)], p) == {"error": "TYPESAFE_API_KEY not set"}
    def boom(req, timeout=0): raise OSError("offline")
    monkeypatch.setattr(C.urllib.request, "urlopen", boom)
    assert "offline" in C.jev_judge([(0, "x" * 20)], p, api_key="k")["error"]


def env(tmp_path, jd=JD, uid="215"):
    system = tmp_path / "_system"
    system.mkdir(parents=True)
    (system / "capability_profile.md").write_text(PROFILE, encoding="utf-8")
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "folder_id"])
        w.writeheader()
        w.writerow({"uid": uid, "company": "Müller AG", "role": "Head of Data", "folder_id": ""})
    (system / "jd_cache.json").write_text(json.dumps({uid: jd}), encoding="utf-8")
    role = tmp_path / "215 Müller AG" / "Head of Data"
    (role / "20 Vorbereitung").mkdir(parents=True)
    return str(system), str(tmp_path), lambda base, u, r, fid="": (role, [])


def test_run_writes_the_table_and_the_state_then_skips_while_current(tmp_path):
    system, base, locate = env(tmp_path)
    calls = []
    def judge(items, prof):
        calls.append(len(items))
        return {i: {"cap": 0, "cover": 3} for i, _ in items}
    res = C.run_uid("215", system, base, "2026-09-26", judge=judge, locate=locate)
    assert res["status"] == "written" and os.path.basename(res["file"]) == "Abdeckung_Müller_AG.md" and os.path.exists(res["file"])
    st = json.load(open(os.path.join(system, "coverage_state.json"), encoding="utf-8"))["215"]
    assert st["must"] == 4 and st["proven"] == 3 and st["file"] == "Abdeckung_Müller_AG.md"
    assert C.run_uid("215", system, base, "2026-09-27", judge=judge, locate=locate)["status"] == "current" and len(calls) == 1
    assert C.run_uid("215", system, base, "2026-09-27", force=True, judge=judge, locate=locate)["status"] == "written" and len(calls) == 2


def test_a_changed_posting_or_profile_makes_the_table_stale(tmp_path):
    system, base, locate = env(tmp_path)
    j = lambda items, prof: {i: {"cap": 0, "cover": 3} for i, _ in items}
    C.run_uid("215", system, base, "2026-09-26", judge=j, locate=locate)
    prof = os.path.join(system, "capability_profile.md")
    open(prof, "a", encoding="utf-8").write("\nreviewed again\n")
    assert C.run_uid("215", system, base, "2026-09-27", judge=j, locate=locate)["status"] == "written"


def test_run_fails_open_and_writes_nothing_when_something_is_missing(tmp_path):
    system, base, locate = env(tmp_path, jd="")
    assert C.run_uid("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    system, base, locate = env(tmp_path / "b", jd="nur Fließtext ohne Listen oder Überschriften, einfach ein langer Satz.")
    assert C.run_uid("215", system, base, "2026-09-26", locate=locate)["reason"].startswith("keine Anforderungen")
    system, base, locate = env(tmp_path / "c")
    os.remove(os.path.join(system, "capability_profile.md"))
    assert C.run_uid("215", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    assert C.run_uid("999", system, base, "2026-09-26", locate=locate)["status"] == "skipped"
    system, base, locate = env(tmp_path / "d")
    down = C.run_uid("215", system, base, "2026-09-26", judge=lambda i, p: {"error": "down"}, locate=locate)
    assert down["status"] == "error" and not os.path.exists(os.path.join(str(tmp_path / "d" / "_system"), "coverage_state.json"))


def test_dry_run_writes_nothing_and_returns_the_text(tmp_path):
    system, base, locate = env(tmp_path)
    res = C.run_uid("215", system, base, "2026-09-26", dry_run=True, judge=lambda items, prof: {i: {"cap": 0, "cover": 3} for i, _ in items}, locate=locate)
    assert res["status"] == "written" and "| 1 |" in res["text"] and not os.path.exists(os.path.join(system, "coverage_state.json"))


# ---- review fix pass -----------------------------------------------------------------------------
def test_ordinary_words_and_acronyms_are_not_certifications_and_terms_need_certificate_wording(tmp_path):
    p = profile(tmp_path)
    assert C.cert_verdict("Ensure safe and responsible use of AI across the group", p) is None            # 'safe' is not SAFe
    assert C.cert_verdict("Erfahrung mit agilen Methoden (Scrum, SAFe, Kanban)", p) is None                # named as a method, no certificate wording
    assert C.cert_verdict("Monitoring mit Splunk oder Datadog", p) is None
    assert C.cert_verdict("Kenntnisse in ITIL-Prozessen", p) is None
    assert C.cert_verdict("PRINCE2 Practitioner Zertifizierung", p)[0] == C.IN_PROGRESS
    assert C.cert_verdict("Splunk certified architect", p)[0] == C.PROVEN


def test_slashes_do_not_hide_the_second_certificate_and_iso_spellings_match(tmp_path):
    p = profile(tmp_path, PROFILE.replace("| PRINCE2 |", "| ISO/IEC 42001 (AI management) | planned | course material |\n| PRINCE2 |"))
    assert C.cert_verdict("Zertifizierung PMP/PRINCE2 erforderlich", p)[0] == C.IN_PROGRESS               # PMP is lapsed, PRINCE2 counts
    assert C.cert_verdict("ISO 42001 Zertifikat", p)[0] == C.IN_PROGRESS and C.cert_verdict("ISO/IEC 42001 certification", p)[0] == C.IN_PROGRESS
    assert C.cert_verdict("ISO/IEC 27001 Zertifizierung", p)[0] == C.GAP


def test_the_best_matching_profile_entry_wins_not_the_first(tmp_path):
    p = profile(tmp_path, PROFILE.replace("| PMP | lapsed | certified until 2019 |", "| ITIL 3 Foundation | lapsed | old |\n| ITIL 4 Foundation | held | 2024 |"))
    assert C.cert_verdict("ITIL Zertifizierung", p)[0] == C.PROVEN


def test_requirement_lines_that_look_like_headings_do_not_flip_the_section():
    jd = ("Ihr Profil:\n- Erfahrung in der IT-Strategie und Architektur\nHohe Kontaktfreude und Kommunikationsstärke\n"
          "- Budgetverantwortung im zweistelligen Millionenbereich\nErfahrung mit SAP ist ein Plus\n- Führungserfahrung mit mehr als zehn Personen\n")
    got = [(r["text"][:12], r["kind"]) for r in C.extract_requirements(jd)]
    assert ("Budgetverant", "must") in got and ("Führungserfa", "must") in got and ("Hohe Kontakt", "must") in got
    assert C.extract_requirements("Salary, Bonus & Benefits\n- Betriebliche Altersvorsorge und 30 Urlaubstage\n") == []


def test_company_prose_footers_and_bullets_of_unrecognised_sections_are_not_requirements():
    jd = ("Über das Unternehmen\nWir sind ein führender Anbieter mit über 200 Mitarbeitenden in Hamburg.\nStellenprofil\nWir suchen Verstärkung für unser Team.\n"
          "27.09.26, 10:15 Head of IT | LinkedIn\nhttps://www.linkedin.com/jobs/view/123456789\n")
    assert C.extract_requirements(jd) == []
    structured = "Responsibilities\n- Own the AI roadmap for the whole group\nWho you are\n- 10+ years leading enterprise data teams\nWhat we offer\n- Hybrid working model and 30 days holiday\n"
    assert [r["text"][:6] for r in C.extract_requirements(structured)] == ["10+ ye"]
    only_tasks = "Responsibilities\n- Own the AI roadmap for the whole group\nWhat we offer\n- Hybrid working model and 30 days holiday\n"
    assert C.extract_requirements(only_tasks) == []                                                    # structure recognised, no requirements: no guessing


def test_uid_formats_match_between_pipeline_pins_and_state(tmp_path):
    system, base, locate = env(tmp_path, uid="09")
    j = lambda items, prof: {i: {"cap": 0, "cover": 3} for i, _ in items}
    assert C.run_uid(9, system, base, "2026-09-26", judge=j, locate=locate)["status"] == "written"
    assert list(json.load(open(os.path.join(system, "coverage_state.json"), encoding="utf-8"))) == ["9"]
    assert C.run_uid("09", system, base, "2026-09-26", judge=j, locate=locate)["status"] == "current"


def test_a_capability_whose_evidence_is_still_to_be_added_never_proves():
    assert not C.has_evidence("qualitative: strong ownership. Evidence to add: unit, scale, outcome") and not C.has_evidence("")
    assert C.has_evidence("CV 2026; CFO letter")
    assert C.classify({"level": 2, "evidence": "Evidence to add: unit"}, 3) == C.ADJACENT


def test_the_model_sees_names_levels_and_only_whether_evidence_exists(tmp_path, monkeypatch):
    p = profile(tmp_path, PROFILE.replace("CV 2026; CFO letter", "CV 2026; EUR 500K budget note"))
    sent = []
    class Resp:
        def __init__(s, b): s.b = b
        def read(s): return s.b
        def __enter__(s): return s
        def __exit__(s, *a): return False
    def fake(req, timeout=0):
        pl = json.loads(req.data); sent.append(pl)
        return Resp(json.dumps({"answers": {q: ({"choice": "c0"} if q.startswith("cap") else {"score": 1.5}) for q in pl["questions"]}}).encode())
    monkeypatch.setattr(C.urllib.request, "urlopen", fake)
    out = C.jev_judge([(0, "Anforderung eins mit Text")], p, api_key="k")
    assert "EUR 500K" not in sent[0]["state"] and "CV 2026" not in sent[0]["state"] and "evidence: yes" in sent[0]["state"] and "evidence: no" in sent[0]["state"]
    assert out[0]["cover"] == 2                                                                        # 1.5 rounds up, not to even


def test_run_reports_instead_of_raising_and_a_moved_table_is_rewritten(tmp_path):
    system, base, locate = env(tmp_path)
    j = lambda items, prof: {i: {"cap": 0, "cover": 3} for i, _ in items}
    res = C.run_uid("215", system, base, "2026-09-26", judge=j, locate=locate)
    os.rename(res["file"], res["file"] + ".moved")
    assert C.run_uid("215", system, base, "2026-09-27", judge=j, locate=locate)["status"] == "written"   # 'current' needs the file to exist
    open(os.path.join(system, "capability_profile.md"), "wb").write(b"\xff\xfe not utf8 \xff")
    assert C.run_uid("215", system, base, "2026-09-28", judge=j, locate=locate)["status"] in ("skipped", "error")
    system2, base2, _ = env(tmp_path / "x")
    def broken(base, uid, role, fid=""): raise OSError("Drive offline")
    assert C.run_uid("215", system2, base2, "2026-09-26", judge=j, locate=broken)["status"] == "error"


def test_two_runs_do_not_lose_each_others_state_entries(tmp_path):
    system, base, locate = env(tmp_path)
    def other_run(items, prof):
        json.dump({"7": {"hash": "x", "share": 0.1, "proven": 1, "must": 2}}, open(os.path.join(system, "coverage_state.json"), "w"))
        return {i: {"cap": 0, "cover": 3} for i, _ in items}
    C.run_uid("215", system, base, "2026-09-26", judge=other_run, locate=locate)
    assert set(json.load(open(os.path.join(system, "coverage_state.json"))) ) == {"7", "215"}


PDF_LAYOUT = """9/25/26, 3:58 PM                     Director, Analytics - Toronto
  Director, Analytics

  The role leads a team of analysts and translates data into clear recommendations for senior leadership.

  Key Responsibilities
       Build, lead, and mature the business intelligence and analytics capability, including enterprise
       analytics and growth insights.

  Skills, Knowledge & Expertise
       10+ years of progressive experience in business intelligence, analytics, strategy, or related business
       leadership roles.
       Demonstrated experience building or transforming an analytics function, including changes to operating models,
       processes, tools, and team capabilities.
       Experience supporting executive leadership and Board-level reporting.
  Experience in B2B, data services, SaaS, retail, healthcare, or member-based organizations
  is an asset.

  Skills & Capabilities
       Strong people leadership with the ability to elevate the quality and strategic impact of team outputs.
       Sound understanding of data governance, privacy, security, responsible AI, and reporting standards,
       control and analytical quality.

  About the Employer
  The employer is committed to helping all employees, customers and stakeholders in an effective and timely manner.
  Apply Now
  Find out more about our benefits and culture on our careers page for candidates.
"""


def test_printed_pdf_text_without_bullets_wrapped_lines_and_skills_headings_gives_whole_requirements():
    reqs = C.extract_requirements(PDF_LAYOUT)
    texts = [r["text"] for r in reqs]
    assert len(reqs) == 6, texts
    assert texts[0].startswith("10+ years of progressive experience") and texts[0].endswith("leadership roles.")            # wrapped line joined
    assert any(t.startswith("Demonstrated experience building") and t.endswith("team capabilities.") for t in texts)
    assert any(t.startswith("Sound understanding of data governance") and "analytical quality" in t for t in texts)
    assert [r["kind"] for r in reqs] == ["must"] * 5 + ["nice"] and reqs[-1]["text"].startswith("Experience in B2B") and reqs[-1]["text"].endswith("is an asset.")
    assert not any("committed to helping" in t or "Build, lead" in t or "Find out more" in t or "The role leads" in t for t in texts)      # employer text, tasks and calls to action are out


def test_an_item_longer_than_the_limit_is_cut_not_dropped_and_about_you_is_a_requirements_heading():
    long_item = "Erfahrung " + "mit sehr vielen unterschiedlichen Themen " * 12
    reqs = C.extract_requirements("About you\n- " + long_item + "\n")
    assert len(reqs) == 1 and len(reqs[0]["text"]) <= C.REQ_MAX and reqs[0]["text"].endswith("…")
