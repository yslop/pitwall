"""Where an engine script lives: source (x.py) in development, compiled (x.pyc) in the installed kit. Python 3.9 compatible."""
import os
import sys

# Children of the engine write German text and symbols into pipes: Windows would otherwise use the ANSI code page and crash on them.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def script_path(system_dir, name):
    base = name[:-3] if name.endswith(".py") else name
    for ext in (".py", ".pyc"):
        path = os.path.join(system_dir, base + ext)
        if os.path.exists(path):
            return path
    return os.path.join(system_dir, base + ".py")


def script_cmd(system_dir, name, *args):
    return [sys.executable, script_path(system_dir, name)] + list(args)
