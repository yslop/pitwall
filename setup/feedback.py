#!/usr/bin/env python3
"""Pilot feedback: a short, anonymous usage summary that YOU review and then paste into a GitHub issue.

    ./star feedback        (or ./mastery feedback, or python3 setup/feedback.py)
    python3 setup/feedback.py --no-open      only write the file, do not open the browser

Nothing is sent anywhere. The summary contains only counts and settings (product, version, system, language, the TYPE of
AI connection, how many days you used it), never names, companies, notes, questions, answers or keys. It is written to
feedback/pilot-<date>.md; the browser then opens the pilot form on GitHub with the summary filled in, so you can read it,
change it or delete it before you submit.
"""
import argparse
import collections
import csv
import datetime as dt
import json
import os
import platform
import re
import subprocess
import sys
import urllib.parse
import webbrowser

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEFAULT_REPO = {"star": "xlrte/xlrte-star", "mastery": "xlrte/xlrte-mastery"}


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def product():
    if os.path.isdir(os.path.join(ROOT, "_xlrte")):
        return "mastery"
    if os.path.isdir(os.path.join(ROOT, "_system")):
        return "star"
    return (_read_json(os.path.join(ROOT, "config", "settings.json"), {}) or {}).get("product", "xlrte")


def repo_slug(prod):
    try:
        url = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return DEFAULT_REPO.get(prod, "xlrte/xlrte-star")


def _system_name():
    if platform.system() == "Darwin":
        return "macOS %s" % (platform.mac_ver()[0] or "?")
    if platform.system() == "Windows":
        return "Windows %s" % platform.release()
    try:
        info = platform.freedesktop_os_release()                      # Python 3.10+
        return "%s %s" % (info.get("NAME", "Linux"), info.get("VERSION_ID", ""))
    except (AttributeError, OSError):
        return "Linux"


def environment(prod):
    s = _read_json(os.path.join(ROOT, "config", "settings.json"), {}) or {}
    ai = s.get("ai") or {}
    try:
        version = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except OSError:
        version = "?"
    return collections.OrderedDict([
        ("Produkt / product", prod),
        ("Version", version),
        ("System", _system_name()),
        ("Python", platform.python_version()),
        ("Sprache / language", s.get("language", "?")),
        ("KI / AI", ai.get("provider") or "keine / none"),
        ("Nur lokal / local only", "ja / yes" if (s.get("privacy") or {}).get("local_only") else "nein / no"),
        ("Eingerichtet / set up", (s.get("setup_completed") or "?")[:10]),
    ])


def _ai_log():
    calls = errors = 0
    try:
        with open(os.path.join(ROOT, "logs", "ai_calls.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                calls += 1
                errors += 0 if e.get("ok", True) else 1
    except OSError:
        pass
    return calls, errors


def usage_star():
    """Numbers from _system/pilot_report.py (demo rows never count there); demo rows are counted separately."""
    out = collections.OrderedDict()
    system_dir = os.path.join(ROOT, "_system")
    rows = []
    try:
        with open(os.path.join(system_dir, "pipeline.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, csv.Error):
        pass
    demo = sum(1 for r in rows if "DEMO" in (r.get("note") or "")[:12])
    out["Eigene Verfahren / own processes"] = len(rows) - demo
    out["Beispiel-Verfahren / demo processes"] = demo
    try:
        sys.path.insert(0, system_dir)
        import pilot_report
        rep = pilot_report.build_report(system_dir, ROOT, dt.date.today().isoformat())
        out["Nach Stufe / by stage"] = ", ".join("%s %d" % kv for kv in sorted(rep["processes_by_stage"].items())) or "-"
        out["Nutzungstage (7 Tage) / days used (7 days)"] = rep["usage_days"]
        out["Gesprächs-Cockpits neu (7 Tage) / new interview cockpits"] = rep["cockpits_created"]
        out["Cockpits aktuell / cockpits up to date"] = rep["cockpits_current"]
        out["Recherche offen / erledigt · research open / done"] = "%s / %s" % (rep["queue_open"], rep["queue_done"])
        if rep.get("lint_pass_rate") is not None:
            out["Qualitäts-Check bestanden / quality check pass rate"] = rep["lint_pass_rate"]
    except Exception as e:                                             # the summary must never fail the pilot
        out["Bericht / report"] = "nicht verfügbar / unavailable (%s)" % type(e).__name__
    return out


def usage_mastery():
    out = collections.OrderedDict()
    rows = []
    try:
        with open(os.path.join(ROOT, "_xlrte", "state", "events.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        pass
    days = sorted({r.get("date") for r in rows if r.get("date")})
    kinds = collections.Counter(r.get("kind") or "?" for r in rows)
    minutes = 0.0
    for r in rows:
        try:
            minutes += float(r.get("minutes") or 0)
        except ValueError:
            pass
    cfg = _read_json(os.path.join(ROOT, "_xlrte", "config.json"), {}) or {}
    exams = sorted((cfg.get("exams") or {}).keys()) or sorted({r.get("exam") for r in rows if r.get("exam")})
    out["Prüfung / exam"] = ", ".join(exams) or "?"
    out["Lerntage / study days"] = "%d (%s – %s)" % (len(days), days[0], days[-1]) if days else "0"
    out["Antworten / answers"] = kinds.get("attempt", 0)
    out["Recaps"] = kinds.get("recap", 0)
    out["Lernminuten / minutes"] = int(minutes)
    return out


def summary(prod):
    env = environment(prod)
    use = usage_mastery() if prod == "mastery" else usage_star()
    calls, errors = _ai_log()
    use["KI-Aufrufe / AI calls"] = "%d (Fehler / errors: %d)" % (calls, errors)
    env_md = "\n".join("- %s: %s" % kv for kv in env.items())
    use_md = "\n".join("- %s: %s" % kv for kv in use.items())
    return env_md, use_md


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anonymous pilot feedback summary (nothing is sent)")
    ap.add_argument("--no-open", action="store_true", help="only write the file")
    a = ap.parse_args(argv)
    prod = product()
    env_md, use_md = summary(prod)
    today = dt.date.today().isoformat()
    os.makedirs(os.path.join(ROOT, "feedback"), exist_ok=True)
    path = os.path.join(ROOT, "feedback", "pilot-%s.md" % today)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Pilot %s\n\n## System\n%s\n\n## Nutzung / usage\n%s\n" % (today, env_md, use_md))
    print(open(path, encoding="utf-8").read())
    print("Gespeichert / saved: %s" % os.path.relpath(path, ROOT))
    print("Enthält nur Zahlen und Einstellungen, keine Namen, Notizen oder Schlüssel. Bitte trotzdem kurz lesen.")
    url = "https://github.com/%s/issues/new?%s" % (repo_slug(prod), urllib.parse.urlencode(
        {"template": "pilot.yml", "title": "Pilot %s" % today, "system": env_md, "usage": use_md}))
    print("Formular / form: %s" % url)
    if not a.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
