"""kit_run.py: engine scripts live as source in development and as compiled files in the installed kit."""
import os, re, sys
SYSTEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM)
import kit_run as K


def test_source_wins_then_compiled_then_the_source_path_for_a_clear_error(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "a.pyc").write_bytes(b"x")
    (tmp_path / "b.pyc").write_bytes(b"x")
    assert K.script_path(str(tmp_path), "a").endswith("a.py")
    assert K.script_path(str(tmp_path), "b.py").endswith("b.pyc")
    assert K.script_path(str(tmp_path), "missing").endswith("missing.py")


def test_script_cmd_starts_with_the_running_interpreter(tmp_path):
    cmd = K.script_cmd(str(tmp_path), "render", "--today", "2026-10-07")
    assert cmd[0] == sys.executable and cmd[1].endswith("render.py") and cmd[2:] == ["--today", "2026-10-07"]


def test_no_engine_module_builds_a_render_or_career_check_path_by_hand():
    pattern = re.compile(r'os\.path\.join\([^()]*,\s*"(render|career_check)\.py"\)')
    for name in ("health.py", "coverage.py", "intel_job.py", "intake.py", "recompute_scores.py"):
        assert not pattern.search(open(os.path.join(SYSTEM, name), encoding="utf-8").read()), name


def test_children_of_the_engine_use_utf8_so_that_windows_pipes_do_not_crash_on_symbols():
    import subprocess
    out = subprocess.run([sys.executable, "-c", "import kit_run, os; print(os.environ.get('PYTHONUTF8'), os.environ.get('PYTHONIOENCODING'))"],
                         cwd=SYSTEM, capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")})
    assert out.stdout.split() == ["1", "utf-8"], out.stdout + out.stderr
