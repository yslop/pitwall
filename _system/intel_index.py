#!/usr/bin/env python3
"""Index of cheat sheets, briefings and intel files per live process -> intel_index.json.

    python3 _system/intel_index.py [--data pipeline.csv] [--root ..] [--out intel_index.json]

For every uid with a live row (Applied, Screening, Interviewing, Final) it looks in the employer folder
`NNN Name`: files directly in it, files directly in each role folder below it, and files directly in a
`20 ...` or `30 ...` subfolder of either. Nothing deeper. It only reads names and modification dates
(and the doc id inside a .gdoc pointer); it never opens, edits or moves your files.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_STAGES = ("Applied", "Screening", "Interviewing", "Final")
EXTENSIONS = (".pdf", ".md", ".gdoc", ".html")
# (kind, pattern) in priority order. "Debriefing" must not count as a briefing: no letter before "briefing".
KINDS = [("cheat_sheet", r"cheat[\s_-]*sheet"), ("briefing", r"(?<![a-z])briefing"), ("cockpit", r"cockpit"),
         ("jd_intel", r"jd[\s_-]*intel"), ("prep_brief", r"prep[\s_-]*brief"), ("strategy", r"(?<!exit[\s_-])(?<![a-z])strategy[\s_-]*doc(?![a-z])")]
KIND_ORDER = {k: i for i, (k, _) in enumerate(KINDS)}
PHASE_DIR = re.compile(r"^(20|30)(\s|_|-|$)")
CLOSED_ROLE = re.compile(r"\((rejected|inactive)\)\s*$", re.I)      # status suffix your role folders carry when a role is over


def classify(name):
    """Kind of intel file for a file name, or None (also None for the wrong extension)."""
    low = name.lower()
    if not low.endswith(EXTENSIONS):
        return None
    for kind, pattern in KINDS:
        if re.search(pattern, low):
            return kind
    return None


def version_key(name):
    """File name without extensions, dates and version tags: dated/versioned copies share one key."""
    low = name.lower()
    for ext in EXTENSIONS + (".md",):
        if low.endswith(ext):
            low = low[: -len(ext)]
    low = re.sub(r"\d{4}-?\d{2}-?\d{2}", " ", low)
    low = re.sub(r"(^|[\s_-])v\d+(?=$|[\s_-])", " ", low)
    return re.sub(r"[\s_-]+", " ", low).strip()


def version_no(name):
    """Explicit version number in a file name (v2, _v10), 0 if none: 'X v2.pdf' beats 'X.pdf' saved the same day."""
    low = name.lower()
    for ext in EXTENSIONS + (".md",):
        if low.endswith(ext):
            low = low[: -len(ext)]
    m = re.search(r"(?:^|[\s_-])v(\d+)(?=$|[\s_-])", low)
    return int(m.group(1)) if m else 0


def gdoc_url(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc_id = json.load(f).get("doc_id")
        return "https://docs.google.com/document/d/%s/edit" % doc_id if doc_id else None
    except (OSError, ValueError, AttributeError):
        return None


def _dirs(path):
    try:
        return sorted(e for e in os.listdir(path) if not e.startswith(".") and os.path.isdir(os.path.join(path, e)))
    except OSError:
        return []


def _files(path):
    try:
        return sorted(e for e in os.listdir(path) if not e.startswith(".") and os.path.isfile(os.path.join(path, e)))
    except OSError:
        return []


def employer_folders(root, uid):
    """Folders of the root named 'NNN Something' (leading zeros allowed) for this uid."""
    pattern = re.compile(r"^0*%d\s" % uid)
    return [d for d in _dirs(root) if pattern.match(d)]


def spots(root, employer):
    """(label, folder relative to root): the employer folder, each role folder below it, and the 20/30 subfolders of both."""
    out = []
    dirs = [d for d in _dirs(os.path.join(root, employer)) if not PHASE_DIR.match(d)]       # 20/30 are phases
    roles = [d for d in dirs if not CLOSED_ROLE.search(d)]                                    # rejected/inactive roles are over ...
    roles = roles or [d for d in dirs if CLOSED_ROLE.search(d)]                               # ... unless the live row has no other role folder (process re-opened)
    for label, rel in [("", employer)] + [(role, os.path.join(employer, role)) for role in roles]:
        out.append((label, rel))
        out += [(label, os.path.join(rel, sub)) for sub in _dirs(os.path.join(root, rel)) if PHASE_DIR.match(sub)]
    return out


def scan_folder(root, employer):
    """Intel files for one employer folder, as dicts (see build). Bounded: see spots()."""
    found = []
    for label, rel in spots(root, employer):
        for name in _files(os.path.join(root, rel)):
            kind = classify(name)
            if not kind:
                continue
            full = os.path.join(root, rel, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            modified = datetime.fromtimestamp(mtime).date().isoformat()
            found.append({"name": name, "kind": kind, "modified": modified, "mtime": mtime, "path": os.path.join(rel, name).replace(os.sep, "/"),
                          "where": label, "link": gdoc_url(full) if name.lower().endswith(".gdoc") else None,
                          "superseded": False})
    return found


def mark_superseded(items):
    """Within files sharing a version key only the newest is current (ties: the later name)."""
    groups = {}
    for it in items:                                                # same employer folder + role folder + kind + base name
        groups.setdefault((it["path"].split("/")[0], it["where"], it["kind"], version_key(it["name"])), []).append(it)
    for group in groups.values():
        group.sort(key=lambda i: (i["mtime"], version_no(i["name"]), i["name"]), reverse=True)
        for old in group[1:]:
            old["superseded"] = True
    items = sorted(items, key=lambda i: i["modified"], reverse=True)            # newest first, then stable by kind
    return sorted(items, key=lambda i: (i["superseded"], KIND_ORDER[i["kind"]]))


def load_channels(channels_path):
    if not channels_path or not os.path.exists(channels_path):
        return set()
    try:
        with open(channels_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        chans = data.get("channels") if isinstance(data, dict) else None
        if isinstance(chans, dict):
            return {int(k) for k in chans if str(k).strip().isdigit()}
    except (OSError, ValueError, TypeError):
        pass
    return set()


def build(root, rows, now, channels=None):
    channel_set = {int(x) for x in channels if str(x).strip().isdigit()} if channels else set()
    uids = sorted({int(r["uid"]) for r in rows if r.get("stage") in LIVE_STAGES and str(r.get("uid", "")).strip().isdigit() and int(r["uid"]) not in channel_set})
    out = {}
    for uid in uids:
        folders = employer_folders(root, uid)
        items = []
        for folder in folders:
            items += scan_folder(root, folder)
        warnings = []
        if not folders:
            warnings.append("Kein Ordner mit dem Präfix %d gefunden" % uid)
        elif len(folders) > 1:
            warnings.append("Mehrere Ordner für uid %d: %s" % (uid, ", ".join(folders)))
        out[str(uid)] = {"folders": folders, "items": mark_superseded(items), "warnings": warnings}
    return {"generated": now.isoformat(timespec="seconds"), "uids": out}


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--root", default=os.path.join(HERE, ".."), help="folder holding the employer folders")
    ap.add_argument("--channels", default=os.path.join(HERE, "channels.json"), help="channels.json file to exclude channel UIDs")
    ap.add_argument("--out", default=os.path.join(HERE, "intel_index.json"))
    a = ap.parse_args(argv)
    try:
        with open(a.data, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, csv.Error, UnicodeDecodeError) as e:
        print("intel_index: cannot read %s (%s)" % (a.data, e), file=sys.stderr)
        return 1
    channels = load_channels(a.channels)
    index = build(os.path.abspath(a.root), rows, datetime.now(), channels=channels)
    write_atomic(a.out, index)
    total = sum(1 for e in index["uids"].values() for i in e["items"] if not i["superseded"])
    print("intel index: %d live employers, %d current files -> %s" % (len(index["uids"]), total, a.out))
    for uid, e in index["uids"].items():
        for w in e["warnings"]:
            print("  ! %s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
