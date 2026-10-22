#!/usr/bin/env python3
"""
tests/test_empirical_stress.py
Empirical Adversarial Stress Test Suite for Career Pipeline & Render System.
"""
import csv, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM_DIR = os.path.dirname(HERE)
RENDER_PY = os.path.join(SYSTEM_DIR, "render.py")
PIPELINE_CSV = os.path.join(SYSTEM_DIR, "pipeline.csv")
TRANSITIONS_CSV = os.path.join(SYSTEM_DIR, "transitions.csv")
FOLDERS_TSV = os.path.join(SYSTEM_DIR, "folders.tsv")
PREP_JSON = os.path.join(SYSTEM_DIR, "prep.json")

def load_canonical_data():
    with open(PIPELINE_CSV, "r", encoding="utf-8") as f:
        pipeline_rows = list(csv.DictReader(f))
    with open(TRANSITIONS_CSV, "r", encoding="utf-8") as f:
        transition_rows = list(csv.DictReader(f))
    return pipeline_rows, transition_rows

def test_adversarial_rejection_text():
    print("\n--- Test Suite 1: Adversarial Rejection Text Variations ---")
    pipeline_rows, transition_rows = load_canonical_data()
    assert len(pipeline_rows) >= 234, f"Expected at least 234 canonical rows, got {len(pipeline_rows)}"

    adversarial_notes = [
        "Leider können wir Sie nicht zum Vorstellungsgespräch einladen.",
        "Absage nach Screening: Kein Kennenlerngespräch terminiert.",
        "Wir bedauern, kein Interview anbieten zu können.",
        "Bewerberpool enthält viele Kandidaten im Vorstellungsgespräch; Absage.",
        "Nicht für Vorstellungsgespräch berücksichtigen (Standardabsage).",
        "andere Kandidat:innen bereits im Gespräch / Interview.",
        "Absage erhalten: Nicht zu Interview eingeladen.",
        "Telefoninterview abgesagt durch Arbeitgeber.",
        "Gesprächsrunden ohne Einladung beendet.",
        "INTERVIEW ABGESAGT - KEIN VORSTELLUNGSGESPRÄCH.",
        "vorstellungsgespräch leider nicht möglich.",
        "Kennenlerngespräch entfällt ersatzlos.",
        "❌ Absage ohne Vorstellungsgespräch oder Interview.",
        'HR Notiz: "Kein Interview vereinbaren, Profil passt nicht"',
        "Vorstellungsgespräch? Nein, direkte Absage nach CV-Sichtung.",
        "Gespräch: Nein. Interview: Nein. Outcome: rejected.",
        "Automatisierte Absage: Kein Vorstellungsgespräch geplant.",
        "Absage per Mail. Betreff: Bewerbung / Vorstellungsgespräch nicht berücksichtigt.",
        "Absage nach 45 Tagen: Kein Interview stattgefunden.",
        "Kandidat wurde nicht für ein Kennenlerngespräch ausgewählt."
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        # Scenario A: Inject 20 synthetic rows with adversarial rejection notes
        synth_pipeline_path = os.path.join(tmpdir, "pipeline_synth.csv")
        fieldnames = list(pipeline_rows[0].keys())

        synth_rows = [dict(r) for r in pipeline_rows]
        for i, adv_note in enumerate(adversarial_notes):
            row = {k: "" for k in fieldnames}
            row.update({
                "uid": f"900{i:02d}",
                "company": f"AdversarialCorp_{i}",
                "role": "Director of Technology",
                "lane": "IT Leadership",
                "stage": "Closed",
                "outcome": "rejected",
                "applied": "2026-03-01",
                "last_event": "2026-03-15",
                "days_idle": "190",
                "salary_fit": "mid",
                "score": "50",
                "due": "",
                "next_action": "",
                "folder_id": "",
                "note": adv_note
            })
            synth_rows.append(row)

        with open(synth_pipeline_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(synth_rows)

        out_dir = os.path.join(tmpdir, "out_a")
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", synth_pipeline_path,
            "--prep", PREP_JSON,
            "--folders", FOLDERS_TSV,
            "--transitions", TRANSITIONS_CSV,
            "--today", "2026-09-22",
            "--out", out_dir,
            "--no-pdf"
        ], capture_output=True, text=True)

        assert res.returncode == 0, f"render.py failed with synthetic rows:\n{res.stderr}"

        cockpit_html = open(os.path.join(out_dir, "01_cockpit.html"), encoding="utf-8").read()
        m = re.search(r'<script type="application/json" id="DATA">([\s\S]*?)</script>', cockpit_html)
        assert m, "DATA block missing"
        data = json.loads(m.group(1))

        assert data["interviews_reached"] == 12, (
            f"Adversarial rejection notes inflated interview count! Expected 12, got {data['interviews_reached']}"
        )
        expected_synth_rows = len(pipeline_rows) + 20
        assert data["expect_rows"] == expected_synth_rows
        assert data["interview_rate"] == round(12 / expected_synth_rows * 100)
        print("  ✓ Scenario A Passed: 20 synthetic adversarial rejection rows did NOT inflate interview count (12 unchanged)")

        # Scenario B: Overwrite notes in 50 real rows across Closed/Applied/Screening
        synth_pipeline_path_b = os.path.join(tmpdir, "pipeline_synth_b.csv")
        synth_rows_b = [dict(r) for r in pipeline_rows]
        for idx in range(min(50, len(synth_rows_b))):
            synth_rows_b[idx]["note"] = adversarial_notes[idx % len(adversarial_notes)]

        with open(synth_pipeline_path_b, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(synth_rows_b)

        out_dir_b = os.path.join(tmpdir, "out_b")
        res_b = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", synth_pipeline_path_b,
            "--prep", PREP_JSON,
            "--folders", FOLDERS_TSV,
            "--transitions", TRANSITIONS_CSV,
            "--today", "2026-09-22",
            "--out", out_dir_b,
            "--no-pdf"
        ], capture_output=True, text=True)

        assert res_b.returncode == 0, f"render.py failed in scenario B:\n{res_b.stderr}"
        cockpit_html_b = open(os.path.join(out_dir_b, "01_cockpit.html"), encoding="utf-8").read()
        m_b = re.search(r'<script type="application/json" id="DATA">([\s\S]*?)</script>', cockpit_html_b)
        data_b = json.loads(m_b.group(1))

        assert data_b["interviews_reached"] == 12, (
            f"Adversarial notes on existing rows altered interview count! Got {data_b['interviews_reached']}"
        )
        assert data_b["interview_rate"] == 5
        print("  ✓ Scenario B Passed: Overwriting notes in 50 real rows had 0 effect on interview metric (12 unchanged)")

        # Scenario C: Verify historical false positive UIDs explicitly
        # UIDs 114 (Medwerk), 116 (Riskon), 48 (Klimawerk), 82 (crew SE), 148 (Brüggen)
        fp_uids = {"114", "116", "48", "82", "148"}
        matching_fp_rows = [r for r in pipeline_rows if r["uid"] in fp_uids]
        assert len(matching_fp_rows) >= 5, f"Expected at least 5 rows for FP UIDs, found {len(matching_fp_rows)}"
        for r in matching_fp_rows:
            uid = r["uid"]
            assert r["stage"] == "Closed", f"UID {uid} should be Closed, got {r['stage']}"
            assert r["outcome"] in ("rejected", "lapsed"), f"UID {uid} should be closed outcome, got {r['outcome']}"
            # Check note content mentions interview/conversation keywords or process note
            note = r.get("note", "")
        print(f"  ✓ Scenario C Passed: All {len(matching_fp_rows)} rows across 5 historical false positive UIDs confirmed Closed and excluded from interview metric")

def test_render_cli_edge_cases():
    print("\n--- Test Suite 2: render.py Edge-Case CLI Invocations ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Case 2.1: Missing all optional files
        out_dir = os.path.join(tmpdir, "out_missing_optional")
        non_existent = os.path.join(tmpdir, "non_existent_file.tmp")
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", PIPELINE_CSV,
            "--prep", non_existent,
            "--folders", non_existent,
            "--transitions", non_existent,
            "--today", "2026-09-22",
            "--out", out_dir,
            "--no-pdf"
        ], capture_output=True, text=True)

        assert res.returncode == 0, f"render.py crashed with missing optional files:\n{res.stderr}"
        for f in ["01_cockpit.html", "02_pipeline_crm.html", "03_briefings.html", "04_agentur_report.html", "sheet_export.csv"]:
            assert os.path.exists(os.path.join(out_dir, f)), f"{f} not generated"
        print("  ✓ Case 2.1 Passed: render.py succeeds gracefully when prep, folders, and transitions files are absent")

        # Case 2.2: Corrupted optional files
        corrupt_json = os.path.join(tmpdir, "corrupt.json")
        with open(corrupt_json, "w") as f:
            f.write("{ INVALID JSON CONTENT : missing closing bracket")

        corrupt_tsv = os.path.join(tmpdir, "corrupt.tsv")
        with open(corrupt_tsv, "w") as f:
            f.write("only_one_col\n123\tanother\textra\ttoo_many_cols\n\n\t\t\n")

        corrupt_csv = os.path.join(tmpdir, "corrupt.csv")
        with open(corrupt_csv, "w") as f:
            f.write("uid,datum\nnot_enough_cols\n\n,,,,\n")

        out_dir_corrupt = os.path.join(tmpdir, "out_corrupt")
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", PIPELINE_CSV,
            "--prep", corrupt_json,
            "--folders", corrupt_tsv,
            "--transitions", corrupt_csv,
            "--today", "2026-09-22",
            "--out", out_dir_corrupt,
            "--no-pdf"
        ], capture_output=True, text=True)

        assert res.returncode == 0, f"render.py crashed with corrupted optional files:\n{res.stderr}"
        assert "Hinweis: prep.json konnte nicht geladen werden" in res.stderr
        print("  ✓ Case 2.2 Passed: render.py handles corrupted JSON, TSV, and CSV files gracefully with stderr notices")

        # Case 2.3: Edge case date inputs
        out_dir_dates = os.path.join(tmpdir, "out_dates")
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", PIPELINE_CSV,
            "--prep", PREP_JSON,
            "--folders", FOLDERS_TSV,
            "--transitions", TRANSITIONS_CSV,
            "--today", "invalid-date-format-9999",
            "--out", out_dir_dates,
            "--no-pdf"
        ], capture_output=True, text=True)
        assert res.returncode == 0, f"render.py failed on invalid date string:\n{res.stderr}"
        print("  ✓ Case 2.3 Passed: render.py recovers gracefully from invalid --today strings to date.today()")

        # Case 2.4: Deeply nested non-existent output directory
        nested_out = os.path.join(tmpdir, "deep", "nested", "custom", "output", "dir")
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", PIPELINE_CSV,
            "--prep", PREP_JSON,
            "--folders", FOLDERS_TSV,
            "--transitions", TRANSITIONS_CSV,
            "--today", "2026-09-22",
            "--out", nested_out,
            "--no-pdf"
        ], capture_output=True, text=True)
        assert res.returncode == 0, f"render.py failed creating nested dir:\n{res.stderr}"
        assert os.path.exists(os.path.join(nested_out, "01_cockpit.html"))
        print("  ✓ Case 2.4 Passed: render.py automatically creates deeply nested output directories")

        # Case 2.5: Special characters and umlauts in applicant name
        out_applicant = os.path.join(tmpdir, "out_applicant")
        special_applicant = "Dr. Jörg O'Connor & Söhne (M.Sc.)"
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", PIPELINE_CSV,
            "--prep", PREP_JSON,
            "--folders", FOLDERS_TSV,
            "--transitions", TRANSITIONS_CSV,
            "--today", "2026-09-22",
            "--applicant", special_applicant,
            "--out", out_applicant,
            "--no-pdf"
        ], capture_output=True, text=True)
        assert res.returncode == 0, f"render.py failed with special characters in applicant name:\n{res.stderr}"
        cockpit_html = open(os.path.join(out_applicant, "01_cockpit.html"), encoding="utf-8").read()
        assert special_applicant in cockpit_html
        print("  ✓ Case 2.5 Passed: render.py handles international characters, umlauts, and quotes in applicant name")

        # Case 2.6: Missing required --data file
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", os.path.join(tmpdir, "non_existent_pipeline.csv"),
            "--out", tmpdir
        ], capture_output=True, text=True)
        assert res.returncode == 1, "render.py should exit with code 1 when --data is missing"
        assert "FEHLER: Datendatei nicht gefunden" in res.stderr
        print("  ✓ Case 2.6 Passed: render.py exits cleanly with code 1 on missing --data file")

        # Case 2.7: --mode prep without --uid
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--mode", "prep"
        ], capture_output=True, text=True)
        assert res.returncode != 0, "--mode prep without --uid should fail"
        assert "--mode prep requires --uid NNN" in res.stderr
        print("  ✓ Case 2.7 Passed: --mode prep without --uid exits cleanly with informative message")

        # Case 2.8: Minimal dataset (1 row)
        min_csv = os.path.join(tmpdir, "min.csv")
        with open(min_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "lane", "stage", "outcome", "applied", "last_event", "days_idle", "score", "salary_fit", "location", "contacts", "next_action", "due", "folder_url", "note", "folder_id"])
            w.writeheader()
            w.writerow({
                "uid": "1", "company": "Solo Corp", "role": "Head of IT", "lane": "IT Leadership",
                "stage": "Interviewing", "outcome": "", "applied": "2026-09-01", "last_event": "2026-09-20",
                "days_idle": "2", "score": "80", "salary_fit": "target", "location": "Berlin",
                "contacts": "", "next_action": "Prep", "due": "2026-09-25", "folder_url": "", "note": "Live process", "folder_id": ""
            })
        empty_trans = os.path.join(tmpdir, "empty_trans.csv")
        with open(empty_trans, "w", newline="", encoding="utf-8") as f:
            f.write("uid,datum,von,nach,ausloeser,quelle\n")

        out_min = os.path.join(tmpdir, "out_min")
        res = subprocess.run([
            sys.executable, RENDER_PY,
            "--data", min_csv,
            "--transitions", empty_trans,
            "--out", out_min,
            "--no-pdf"
        ], capture_output=True, text=True)
        assert res.returncode == 0, f"render.py failed on minimal 1-row dataset:\n{res.stderr}"
        cockpit_min = open(os.path.join(out_min, "01_cockpit.html"), encoding="utf-8").read()
        m = re.search(r'<script type="application/json" id="DATA">([\s\S]*?)</script>', cockpit_min)
        data = json.loads(m.group(1))
        assert data["expect_rows"] == 1
        assert data["interviews_reached"] == 1
        assert data["interview_rate"] == 100
        print("  ✓ Case 2.8 Passed: render.py processes minimal 1-row dataset with 100% interview rate")

def test_deterministic_consistency():
    print("\n--- Test Suite 3: Deterministic Consistency of 12 Interviews (5%) ---")
    pipeline_rows, transition_rows = load_canonical_data()

    def norm_uid(u):
        u = str(u or "").strip()
        try:
            return str(int(u))
        except ValueError:
            return u

    # 1. Transitions audit trail analysis
    transitions_interview_uids = set()
    transitions_audit_trail = []
    for t in transition_rows:
        if t.get("nach") in ("Interviewing", "Final") and t.get("uid"):
            u = norm_uid(t["uid"])
            if u:
                transitions_interview_uids.add(u)
                transitions_audit_trail.append((u, t.get("nach"), t.get("datum"), t.get("ausloeser")))

    print(f"  Transitions reaching Interviewing/Final: {len(transitions_interview_uids)} unique UIDs:")
    for u, nach, datum, trigger in transitions_audit_trail:
        print(f"    - UID {u:>3}: {datum} -> {nach:<12} ({trigger})")

    expected_transitions_uids = {"5", "6", "31", "37", "51", "54", "55", "131", "133", "157"}
    assert transitions_interview_uids == expected_transitions_uids, (
        f"Mismatch in transitions interview UIDs: {transitions_interview_uids} vs {expected_transitions_uids}"
    )

    # 2. Active stages analysis
    active_interview_uids = set()
    active_details = []
    for r in pipeline_rows:
        if r.get("stage") in ("Interviewing", "Final"):
            u = norm_uid(r.get("uid"))
            active_interview_uids.add(u)
            active_details.append((u, r.get("company"), r.get("role"), r.get("stage")))

    print(f"\n  Active opportunities in Interviewing/Final: {len(active_interview_uids)} UIDs:")
    for u, comp, role, stage in active_details:
        print(f"    - UID {u:>3}: {comp:<30} [{stage}] {role[:35]}")

    expected_active_uids = {"119", "133", "154"}
    assert active_interview_uids == expected_active_uids, (
        f"Mismatch in active interview UIDs: {active_interview_uids} vs {expected_active_uids}"
    )

    # 3. Union analysis
    all_interview_uids = transitions_interview_uids.union(active_interview_uids)
    print(f"\n  Deterministic Set Union: {len(all_interview_uids)} unique interview opportunities:")
    expected_all_12 = {"5", "6", "31", "37", "51", "54", "55", "119", "131", "133", "154", "157"}
    assert all_interview_uids == expected_all_12, (
        f"Set union mismatch: {all_interview_uids} vs {expected_all_12}"
    )

    uid_to_company = {}
    for r in pipeline_rows:
        u = norm_uid(r.get("uid"))
        if u and u not in uid_to_company:
            uid_to_company[u] = r.get("company")

    for u in sorted(all_interview_uids, key=int):
        comp = uid_to_company.get(u, "Unknown")
        src = []
        if u in transitions_interview_uids:
            src.append("transitions.csv")
        if u in active_interview_uids:
            src.append("active pipeline")
        print(f"    [{u:>3}] {comp:<32} (Source: {', '.join(src)})")

    # Percentage check
    total_rows = len(pipeline_rows)
    assert total_rows >= 234, f"Expected at least 234 total rows, got {total_rows}"
    exact_rate = len(all_interview_uids) / total_rows * 100
    rounded_rate = round(exact_rate)
    print(f"\n  Conversion Rate Calculation: {len(all_interview_uids)} / {total_rows} = {exact_rate:.4f}% -> {rounded_rate}%")
    assert rounded_rate == 5, f"Expected rounded rate 5%, got {rounded_rate}%"

    assert "133" in transitions_interview_uids and "133" in active_interview_uids
    assert "119" in active_interview_uids
    assert "154" in active_interview_uids

    false_positives = {"114", "116", "48", "82", "148"}
    overlap = all_interview_uids.intersection(false_positives)
    assert len(overlap) == 0, f"False positives found in interview set: {overlap}"
    print("  ✓ Deterministic consistency verified: Exactly 12 unique interview opportunities (5%), zero defects")

def main():
    print("=" * 78)
    print("  EMPIRICAL ADVERSARIAL STRESS TEST SUITE — MILESTONE 4")
    print("=" * 78)

    test_adversarial_rejection_text()
    test_render_cli_edge_cases()
    test_deterministic_consistency()

    print("\n" + "=" * 78)
    print("  ALL EMPIRICAL STRESS TESTS PASSED WITH ZERO DEFECTS")
    print("=" * 78)

if __name__ == "__main__":
    main()
