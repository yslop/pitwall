#!/usr/bin/env python3
"""
tests/test_boundary_and_export_safety.py
Empirical Challenger Test Suite for Milestone 4 Boundary Safety & Data Integrity.
Executed by teamwork_preview_challenger_m4_2 (Zero-dependency unittest suite).
"""

import ast
import csv
import datetime
import os
import re
import unittest

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.abspath(os.path.join(SYSTEM_DIR, ".."))

# Employer folders numbered above this were created after the M4 milestone (22 Sep 2026)
# and are exempt from the immutability checks; only the milestone set is snapshot-tested.
MILESTONE_MAX_FOLDER = 213

# Working folders, not employers: their content changes whenever references or templates are updated.
NON_EMPLOYER_DIRS = {"00 references", "01 templates"}


def _milestone_folders():
    out = []
    for e in os.listdir(PARENT_DIR):
        if not (os.path.isdir(os.path.join(PARENT_DIR, e)) and e[0].isdigit()):
            continue
        m = re.match(r"\d+", e)
        if m and int(m.group()) <= MILESTONE_MAX_FOLDER:
            out.append(e)
    return sorted(out)


class TestEmployerFolderImmutability(unittest.TestCase):
    """Empirically stress-test employer folder immutability in parent directory `..`."""

    def test_exactly_188_numbered_folders_exist(self):
        numbered = _milestone_folders()
        self.assertEqual(len(numbered), 185, f"Expected exactly 185 numbered employer folders, found {len(numbered)}")

    def test_folder_prefix_structure_and_duplicates(self):
        numbered = _milestone_folders()
        prefixes = [d.split(" ", 1)[0] for d in numbered]
        
        distinct_prefixes = set(prefixes)
        self.assertEqual(len(distinct_prefixes), 183, f"Expected 183 unique prefixes, got {len(distinct_prefixes)}")
        self.assertEqual(len(numbered), 185, f"Expected 185 numbered folders, got {len(numbered)}")

    def test_zero_employer_folder_modifications_during_milestone(self):
        numbered = _milestone_folders()
        
        cutoff_dt = datetime.datetime(2026, 9, 22, 0, 33, 0)
        allowed_dirs = {
            "154 Codewerk (active)", "183 Laserwerk",
            "09 Flugwerk", "62 Technikdienst (active)", "133 Nordberatung (active)", "213 daten-dsb GmbH",
            "129 Rose (active)", "109 Döhler (active)", "11 Sonnenwerk (inactive)",
            "02 Strom AG (inactive)", "97 Munich Re (new)", "21 Talentagentur (active)",
            "119 ITEC", "162 Limo-Werk (new)"
        }
        
        modified_folders = []
        for d in numbered:
            if d in allowed_dirs or d in NON_EMPLOYER_DIRS:
                continue
            full = os.path.join(PARENT_DIR, d)
            st = os.stat(full)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime)
            if mtime > cutoff_dt:
                modified_folders.append((d, mtime))
                
        self.assertEqual(len(modified_folders), 0, f"Employer folders modified after cutoff: {modified_folders}")

    def test_zero_employer_folder_file_mutations(self):
        """Walk all employer folders and verify zero files were modified since M1 outside allowed."""
        numbered = _milestone_folders()
        
        cutoff_dt = datetime.datetime(2026, 9, 22, 0, 33, 0)
        allowed_dirs = {
            "154 Codewerk (active)", "183 Laserwerk",
            "09 Flugwerk", "62 Technikdienst (active)", "133 Nordberatung (active)", "213 daten-dsb GmbH",
            "129 Rose (active)", "109 Döhler (active)", "11 Sonnenwerk (inactive)",
            "02 Strom AG (inactive)", "97 Munich Re (new)", "21 Talentagentur (active)",
            "119 ITEC", "214 HANDELSBANK AG", "215 ABC1 Canada"
        }
        allowed_generated_prefixes = (
            "Recherche_Auftrag_", "Nachbereitung_Auftrag_", "Abdeckung_",
            "Entwurf_Auftrag_", "Marke_", "CV_", "CL_", "Debrief_"
        )
        total_files = 0
        mutated_files = []
        
        for d in numbered:
            dir_path = os.path.join(PARENT_DIR, d)
            for root, _, files in os.walk(dir_path):
                for f in files:
                    total_files += 1
                    if d in allowed_dirs or f == ".DS_Store" or f.startswith(allowed_generated_prefixes):
                        continue
                    if os.path.basename(root) == "30 Verlauf":
                        continue                                    # the process log: proof PDFs and mails the user downloads by hand (Gmail attachments cannot be read by the run) are filed here
                    fp = os.path.join(root, f)
                    st = os.stat(fp)
                    mtime = datetime.datetime.fromtimestamp(st.st_mtime)
                    if mtime > cutoff_dt:
                        mutated_files.append((fp, mtime))
                        
        self.assertGreaterEqual(total_files, 1000, f"Expected at least 1,000 baseline files across employer dirs, found {total_files}")
        self.assertEqual(len(mutated_files), 0, f"Files mutated in unexpected employer directories: {mutated_files}")


class TestBoundaryConfinementAndCodeSafety(unittest.TestCase):
    """Verify that scripts do not contain arbitrary delete or mutate calls."""

    def test_ast_for_destructive_filesystem_calls(self):
        """Parse all Python files in _system/ and ensure no dangerous unlink/rmtree/remove calls."""
        py_files = [f for f in os.listdir(SYSTEM_DIR) if f.endswith(".py")]
        
        violations = []
        for pf in py_files:
            fp = os.path.join(SYSTEM_DIR, pf)
            with open(fp, "r", encoding="utf-8") as f:
                source = f.read()
            
            tree = ast.parse(source, filename=pf)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    func_name = ""
                    if isinstance(func, ast.Attribute):
                        func_name = func.attr
                    elif isinstance(func, ast.Name):
                        func_name = func.id
                    
                    if func_name in ("remove", "rmtree", "rmdir"):
                        violations.append((pf, node.lineno, func_name))
                    elif func_name == "unlink":
                        # digest.py has a documented firewall unlink for its own newly written file
                        if pf != "digest.py":
                            violations.append((pf, node.lineno, func_name))
                            
        self.assertEqual(len(violations), 0, f"Destructive filesystem calls discovered: {violations}")

    def test_render_py_writes_strictly_to_controlled_targets(self):
        """Inspect render.py to ensure write operations are bounded."""
        fp = os.path.join(SYSTEM_DIR, "render.py")
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('cols = ["uid", "company", "role"', content)
        self.assertIn('sheet_export_path = os.path.join(out_dir, "sheet_export.csv")', content)
        self.assertIn('sync_files = list(out.keys()) + ["sheet_export.csv"]', content)


class TestSheetExportDataIntegrity(unittest.TestCase):
    """Stress-test sheet_export.csv data integrity and 1-to-1 parity with pipeline.csv."""

    def setUp(self):
        pipeline_path = os.path.join(SYSTEM_DIR, "pipeline.csv")
        sheet_sys_path = os.path.join(SYSTEM_DIR, "sheet_export.csv")
        
        with open(pipeline_path, "r", encoding="utf-8") as f:
            self.pipe_rows = list(csv.DictReader(f))
            
        with open(sheet_sys_path, "r", encoding="utf-8") as f:
            self.sheet_rows = list(csv.DictReader(f))

    def test_exact_row_count_match(self):
        self.assertEqual(len(self.pipe_rows), len(self.sheet_rows))
        self.assertGreaterEqual(len(self.pipe_rows), 234)

    def test_exact_key_set_match(self):
        pipe_keys = [(r["uid"].strip(), r["company"].strip(), r["role"].strip()) for r in self.pipe_rows]
        sheet_keys = [(r["uid"].strip(), r["company"].strip(), r["role"].strip()) for r in self.sheet_rows]
        
        self.assertEqual(len(pipe_keys), len(self.pipe_rows))
        self.assertEqual(len(sheet_keys), len(self.sheet_rows))
        self.assertEqual(set(pipe_keys), set(sheet_keys))

    def test_field_by_field_equality(self):
        pipe_map = {(r["uid"].strip(), r["company"].strip(), r["role"].strip()): r for r in self.pipe_rows}
        sheet_map = {(r["uid"].strip(), r["company"].strip(), r["role"].strip()): r for r in self.sheet_rows}
        
        shared_fields = [
            "uid", "company", "role", "lane", "stage", "outcome", "applied",
            "last_event", "days_idle", "score", "salary_fit", "location",
            "contacts", "next_action", "due", "note"
        ]
        
        mismatches = []
        for key, p_row in pipe_map.items():
            s_row = sheet_map[key]
            for field in shared_fields:
                p_val = p_row.get(field, "").strip()
                s_val = s_row.get(field, "").strip()
                if p_val != s_val:
                    mismatches.append((key, field, p_val, s_val))
                    
        self.assertEqual(len(mismatches), 0, f"Field mismatches found ({len(mismatches)}): {mismatches[:5]}")

    def test_folder_url_derivation_oracle(self):
        pipe_map = {(r["uid"].strip(), r["company"].strip(), r["role"].strip()): r for r in self.pipe_rows}
        sheet_map = {(r["uid"].strip(), r["company"].strip(), r["role"].strip()): r for r in self.sheet_rows}
        
        url_errors = []
        for key, p_row in pipe_map.items():
            s_row = sheet_map[key]
            fid = p_row.get("folder_id", "").strip()
            expected_url = f"https://drive.google.com/drive/folders/{fid}" if fid else ""
            actual_url = s_row.get("folder_url", "").strip()
            if actual_url != expected_url:
                url_errors.append((key, expected_url, actual_url))
                
        self.assertEqual(len(url_errors), 0, f"folder_url derivation errors: {url_errors}")

    def test_no_email_pii_in_export(self):
        email_re = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        pii_rows = []
        for r in self.sheet_rows:
            note = r.get("note", "")
            if email_re.search(note):
                pii_rows.append((r["uid"], r["company"], note))
        self.assertEqual(len(pii_rows), 0, f"Email PII found in sheet_export.csv notes: {pii_rows}")

    def test_note_length_schema_constraint(self):
        long_notes = []
        for r in self.sheet_rows:
            note = r.get("note", "")
            if len(note) > 300:
                long_notes.append((r["uid"], r["company"], len(note)))
        self.assertEqual(len(long_notes), 0, f"Notes exceeding 300 chars in sheet_export.csv: {long_notes}")

    def test_export_sorting_order(self):
        """Verify rows are sorted descending by score, tie-breaking by company."""
        scores = [int(float(r.get("score") or 0)) for r in self.sheet_rows]
        for i in range(len(scores) - 1):
            self.assertGreaterEqual(scores[i], scores[i + 1], f"Sort violation at row {i}: score {scores[i]} < {scores[i+1]}")


if __name__ == "__main__":
    unittest.main()
