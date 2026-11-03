#!/usr/bin/env python3
"""Build an installer that needs nothing preinstalled: Pitwall plus its own Python (python-build-standalone) and packages.

    python3 installer/build.py --target darwin-arm64 --version 0.2.0      # on macOS  -> dist/Pitwall-0.2.0-mac-arm64.dmg
    python3 installer/build.py --target windows-x64 --version 0.2.0       # on Windows (Inno Setup 6) -> dist/Pitwall-0.2.0-windows-setup.exe
    python3 installer/build.py --target linux-x64 --version 0.2.0         # on Linux -> dist/Pitwall-0.2.0-linux-x64.tar.gz

Runs on the operating system it builds for (CI does this for every release, see .github/workflows/installers.yml).
The runtime is pinned with a SHA-256 in installer/runtime.json; a mismatch stops the build. Nothing personal goes in:
the payload is the files git tracks, minus CI, the installer itself and the README GIFs.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://github.com/astral-sh/python-build-standalone/releases/download/%s/%s"
SKIP_PREFIX = (".github/", "installer/", "docs/media/")
NAMES = {"darwin-arm64": "mac-arm64", "darwin-x64": "mac-intel", "windows-x64": "windows", "linux-x64": "linux-x64"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_runtime(target, work):
    with open(os.path.join(HERE, "runtime.json"), encoding="utf-8") as f:
        lock = json.load(f)
    entry = lock["targets"][target]
    path = os.path.join(work, entry["asset"])
    if not os.path.exists(path):
        print("Lade Python-Laufzeit:", entry["asset"], flush=True)
        with urllib.request.urlopen(URL % (lock["tag"], entry["asset"].replace("+", "%2B")), timeout=600) as r, open(path, "wb") as out:
            shutil.copyfileobj(r, out)
    if sha256(path) != entry["sha256"]:
        os.remove(path)
        sys.exit("Prüfsumme der Laufzeit stimmt nicht: " + entry["asset"])
    return path


def tracked_files():
    try:
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, check=True).stdout.decode("utf-8")
        files = [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):                     # not a git checkout (e.g. a ZIP download): take the tree
        files = []
        for d, dirs, names in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in (".git", "dist", "__pycache__", ".venv", "config", "logs", "feedback")]
            files += [os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/") for n in names]
    return [f for f in files if not f.startswith(SKIP_PREFIX)]


def make_payload(dest, runtime_archive, target):
    for rel in tracked_files():
        src = os.path.join(ROOT, rel)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
            shutil.copy2(src, os.path.join(dest, rel))
    tmp = tempfile.mkdtemp()
    with tarfile.open(runtime_archive) as t:
        t.extractall(tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    shutil.move(os.path.join(tmp, "python"), os.path.join(dest, "runtime"))
    py = os.path.join(dest, "runtime", "python.exe" if target.startswith("windows") else os.path.join("bin", "python3"))
    subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "--no-cache-dir", "-q",
                    "-r", os.path.join(dest, "requirements.txt")], check=True)
    subprocess.run([py, "-c", "import jinja2, requests, bs4; print('Pakete in der Laufzeit: ok')"], check=True)
    return py


def build(target, version, out):
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, "_work")
    os.makedirs(work, exist_ok=True)
    runtime = fetch_runtime(target, work)
    name = "Pitwall-%s-%s" % (version, NAMES[target])
    stage = os.path.join(work, name)
    shutil.rmtree(stage, ignore_errors=True)
    if target.startswith("darwin"):
        payload = os.path.join(stage, "payload")
        make_payload(payload, runtime, target)
        shutil.copy(os.path.join(HERE, "mac", "install.command"), os.path.join(stage, "Pitwall installieren.command"))
        os.chmod(os.path.join(stage, "Pitwall installieren.command"), 0o755)
        shutil.copy(os.path.join(HERE, "mac", "LIESMICH.txt"), os.path.join(stage, "LIESMICH · README.txt"))
        dmg = os.path.join(out, name + ".dmg")
        if os.path.exists(dmg):
            os.remove(dmg)
        subprocess.run(["hdiutil", "create", "-volname", "Pitwall", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg], check=True)
        return dmg
    if target.startswith("windows"):
        make_payload(stage, runtime, target)
        iscc = shutil.which("ISCC") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        subprocess.run([iscc, "/DVersion=" + version, "/DPayload=" + stage, "/DOutDir=" + out, "/DOutName=" + name + "-setup",
                        os.path.join(HERE, "windows", "pitwall.iss")], check=True)
        return os.path.join(out, name + "-setup.exe")
    make_payload(os.path.join(stage, "pitwall"), runtime, target)
    tgz = os.path.join(out, name + ".tar.gz")
    with tarfile.open(tgz, "w:gz") as t:
        t.add(os.path.join(stage, "pitwall"), arcname="pitwall")
    return tgz


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a Pitwall installer with its own Python")
    ap.add_argument("--target", required=True, choices=sorted(NAMES))
    ap.add_argument("--version", default="dev")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args(argv)
    print(build(a.target, a.version.lstrip("v"), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
