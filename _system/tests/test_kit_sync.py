"""sync.py --kit skips the owner-only steps and still runs the engine steps."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sync


class Done:
    returncode, stdout, stderr = 0, "ok", ""


def test_kit_mode_skips_owner_only_scripts(monkeypatch):
    called = []
    monkeypatch.setattr(sync.subprocess, "run", lambda cmd, **kw: called.append(os.path.basename(cmd[1])) or Done())
    assert sync.main(["--kit", "--skip-preflight", "--quiet", "--today", "2026-10-07"]) == 0
    assert not set(called) & set(sync.KIT_SKIP)
    assert {"revisit.py", "intel_job.py", "prep_engine.py", "health.py", "intel_index.py", "intel_queue.py", "render.py"} <= set(called)


def test_default_mode_still_runs_everything(monkeypatch):
    called = []
    monkeypatch.setattr(sync.subprocess, "run", lambda cmd, **kw: called.append(os.path.basename(cmd[1])) or Done())
    sync.main(["--skip-preflight", "--quiet", "--today", "2026-10-07"])
    assert set(sync.KIT_SKIP) <= set(called)
