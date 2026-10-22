#!/usr/bin/env python3
"""Run the same checks as the release export: build the packs (if any), then the test suite. Used by CI and by you.

    python3 tools/run_tests.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MKDIRS = []
STEPS = [
 [
  "python3",
  "-m",
  "pytest",
  "-q",
  "-p",
  "no:cacheprovider",
  "_system/tests",
  "--deselect",
  "_system/tests/test_intake.py::test_runbook_describes_the_real_move_not_a_copy_and_rollback",
  "--deselect",
  "_system/tests/test_intake.py::test_runbook_mentions_the_sidecar_confirmation_and_the_render_option",
  "--deselect",
  "_system/tests/test_intake.py::test_runbook_takes_fit_and_brief_candidates_from_the_data_not_from_the_report",
  "--deselect",
  "_system/tests/test_intake.py::test_template_and_runbook_teach_the_confirm_command_and_its_review_step",
  "--deselect",
  "_system/tests/test_intel_docs.py::test_lint_cli_exit_codes"
 ]
]


def main():
    for d in MKDIRS:
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    for argv in STEPS:
        argv = [sys.executable if a == "python3" else a for a in argv]
        print("$", " ".join(argv[:6]) + (" …" if len(argv) > 6 else ""), flush=True)
        if subprocess.call(argv, cwd=ROOT) != 0:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
