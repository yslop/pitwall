"""The Top-10 pin list (top10.json): which uids the user wants prepared, in order. Jev fills the free slots later.

    {"pinned": [215, 217], "excluded": [42]}

Pure helpers plus atomic file access. A missing or corrupt file is an empty list; nothing here ever raises on bad data.
"""
import json
import os
from datetime import datetime

SLOTS = 10


def _uids(values):
    out = []
    for v in values if isinstance(values, list) else []:
        if isinstance(v, bool):
            continue
        try:
            u = int(str(v).strip())
        except (TypeError, ValueError):
            continue
        if u not in out:
            out.append(u)
    return out


def _normalise(data):
    data = data if isinstance(data, dict) else {}
    excluded = _uids(data.get("excluded"))
    return {"pinned": [u for u in _uids(data.get("pinned")) if u not in excluded], "excluded": excluded}


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return _normalise(data)


def _load_for_write(path):
    """Like load, but a file that exists and cannot be parsed is renamed aside first (a typo in a hand edit must never cost the pins);
    a temporarily unreadable file raises instead of being overwritten."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return _normalise({})
    except ValueError:
        data = None
    if not isinstance(data, dict):
        stamp, n = datetime.now().strftime("%Y%m%d%H%M%S"), 0
        backup = "%s.corrupt-%s" % (path, stamp)
        while os.path.exists(backup):
            n += 1
            backup = "%s.corrupt-%s-%d" % (path, stamp, n)
        os.rename(path, backup)
    return _normalise(data)


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"pinned": data["pinned"], "excluded": data["excluded"]}, f, indent=1)
    os.replace(tmp, path)


def pin(path, uid):
    """Pin a uid (an explicit pin overrides an earlier exclusion). Returns the new state."""
    data, uid = _load_for_write(path), int(uid)
    data["excluded"] = [u for u in data["excluded"] if u != uid]
    if uid not in data["pinned"]:
        data["pinned"].append(uid)
    save(path, data)
    return data


def unpin(path, uid):
    data, uid = _load_for_write(path), int(uid)
    data["pinned"] = [u for u in data["pinned"] if u != uid]
    save(path, data)
    return data


def exclude(path, uid):
    data, uid = _load_for_write(path), int(uid)
    data["pinned"] = [u for u in data["pinned"] if u != uid]
    if uid not in data["excluded"]:
        data["excluded"].append(uid)
    save(path, data)
    return data


def main(argv=None):
    """python3 top10.py pin|unpin|exclude UID [--file top10.json]"""
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Pin, unpin or exclude a uid in the Top-10 list.")
    ap.add_argument("action", choices=["pin", "unpin", "exclude", "show"])
    ap.add_argument("uid", nargs="?")
    ap.add_argument("--file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "top10.json"))
    a = ap.parse_args(argv)
    if a.action == "show":
        print(json.dumps(load(a.file)))
        return 0
    import re
    if not a.uid or not re.fullmatch(r"[0-9]{1,9}", str(a.uid).strip()):
        print("top10: eine numerische uid angeben", file=sys.stderr)
        return 2
    if not os.path.isdir(os.path.dirname(os.path.abspath(a.file))):
        print("top10: Ordner von %s existiert nicht" % a.file, file=sys.stderr)
        return 2
    data = {"pin": pin, "unpin": unpin, "exclude": exclude}[a.action](a.file, int(a.uid))
    print("top10: %s %s -> %d gepinnt" % (a.action, a.uid, len(data["pinned"])))
    return 0


def slots_used(data):
    return min(len(data["pinned"]), SLOTS)


if __name__ == "__main__":
    import sys
    sys.exit(main())
