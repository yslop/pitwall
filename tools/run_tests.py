#!/usr/bin/env python3
"""Run the same checks as the release export: build the packs (if any), then the test suite. Used by CI and by you.

    python3 tools/run_tests.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
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
    for stream in (sys.stdout, sys.stderr):                         # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    for d in MKDIRS:
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    for argv in STEPS:
        argv = [sys.executable if a == "python3" else a for a in argv]
        print("$", " ".join(argv[:6]) + (" …" if len(argv) > 6 else ""), flush=True)
        proc = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV)
        out = proc.stdout.decode("utf-8", "replace")
        print(out, flush=True)
        if proc.returncode != 0:
            if os.environ.get("GITHUB_ACTIONS"):                       # show the failure in the PR, not only in the raw log
                tail = "\n".join(out.strip().splitlines()[-60:])
                tail = tail.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
                print("::error title=%s::%s" % (" ".join(argv[1:4]).replace(":", " "), tail), flush=True)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
