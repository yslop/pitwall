"""Reading pane data: which documents (cheat sheet, briefing, strategy, JD intel, prep brief) a live position offers.

Input is intel_index.json (written by intel_index.py) and the pipeline rows. Markdown files are rendered to safe HTML
(md_safe) so the page can show them inline. HTML files are shown in a frame by relative path, everything else is a link.
Only files inside the career folder are ever read. Python 3.9 compatible.
"""
import os

import intel_job
import intel_quality
import md_safe

STAGE_DOC = {"Applied": "cheat_sheet", "Screening": "cheat_sheet", "Interviewing": "briefing", "Final": "strategy"}
READ_STAGES = tuple(STAGE_DOC)
KIND_ORDER = ("cheat_sheet", "briefing", "strategy", "jd_intel", "prep_brief", "cockpit")
KIND_LABEL = {"cheat_sheet": "Cheat Sheet", "briefing": "Briefing", "strategy": "Strategy-Dokument", "jd_intel": "JD-Intel",
              "prep_brief": "Prep-Brief", "cockpit": "Cockpit"}
MAX_CHARS = 60000       # a longer markdown file is cut with a note (the pages are already large)
MAX_PAGE_CHARS = 150000  # a larger HTML file is framed by path instead of being embedded
_EXTRA_CI = (".intel-header,.pb-hdr{background:#1A1A1A!important;border-top:4px solid #E4572E}"
             ".fit-fill,.salary-fill{background:#E4572E!important}")


def _ci_style():
    """The XLRTE layer of theme.css (single source) plus the two employer-colored spots of older pages, as a <style> element."""
    css = ""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.css"), encoding="utf-8") as f:
            css = f.read()
    except OSError:
        pass
    block = ""
    mark = css.find("XLRTE Brand v0.4")
    if mark >= 0:
        start = css.rfind("/*", 0, mark)
        end = css.find("Briefing tabs", mark)
        end = css.rfind("/*", 0, end) if end > 0 else len(css)
        block = css[start:end]
    return "<style>/* XLRTE Brand layer (reading pane) */\n%s\n%s</style>" % (block, _EXTRA_CI)


def _restyle(page):
    """Older JD-intel and prep-brief files were made with the blue theme: append the XLRTE layer (the file itself is not touched)."""
    style = _ci_style()
    i = page.lower().rfind("</body>")
    return page + style if i < 0 else page[:i] + style + page[i:]


def _key(uid):
    s = str(uid if uid is not None else "").strip()
    return str(int(s)) if s.isdigit() else s


def _safe_path(root, rel):
    """Absolute path of rel inside root, or None (absolute paths and .. escapes are refused)."""
    if not rel or os.path.isabs(rel):
        return None
    full = os.path.realpath(os.path.join(root, rel))
    base = os.path.realpath(root)
    return full if full.startswith(base + os.sep) else None


def _read(root, rel):
    full = _safe_path(root, rel)
    if not full:
        return None
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _quality(kind, name, text, today):
    """Evidence metrics for a generated intel document (by its file name rules), None for any other file or on any problem."""
    m = intel_job.INTEL_NAME.match(name or "")
    if kind not in ("cheat_sheet", "briefing", "strategy") or not m:
        return None
    try:
        return intel_quality.metrics(text, kind, int(m.group("v")), today, name)
    except Exception:
        return None


def _doc(root, kind, picked, group, today=None):
    """picked: the preferred file of a group; group: all files of it (same folder, same name, other extensions)."""
    ext = os.path.splitext(picked.get("name") or "")[1].lower()
    doc = {"kind": kind, "label": KIND_LABEL.get(kind, kind), "name": picked.get("name") or "", "path": picked.get("path") or "",
           "where": picked.get("where") or "", "modified": picked.get("modified") or "", "link": picked.get("link"),
           "mode": "link", "html": None, "truncated": False, "quality": None}
    if ext == ".md":
        text = _read(root, picked.get("path"))
        if text is not None:
            doc["html"], doc["truncated"] = md_safe.render_capped(text, MAX_CHARS)
            doc["mode"] = "md"
            doc["quality"] = _quality(kind, picked.get("name"), text, today)
            return doc
        for other in group:                          # the markdown is gone: fall back to an html sibling
            if os.path.splitext(other.get("name") or "")[1].lower() == ".html":
                doc.update(name=other.get("name") or "", path=other.get("path") or "", mode="frame")
                return doc
    elif ext == ".html":
        text = _read(root, picked.get("path"))
        if text is not None and len(text) <= MAX_PAGE_CHARS:
            doc["html"], doc["mode"] = _restyle(text), "page"
        elif text is not None:
            doc["mode"] = "frame"
    return doc


def _rank_of(name):
    ext = os.path.splitext(name or "")[1].lower()
    return {".md": 0, ".html": 1}.get(ext, 2)


def build(intel, rows, root, today=None):
    """{uid: {"docs": [...], "primary": 0, "stage": ...}} for the rows of a live stage that have documents."""
    uids = (intel or {}).get("uids") if isinstance(intel, dict) else None
    if not isinstance(uids, dict):
        return {}
    normalised = {_key(k): v for k, v in uids.items()}
    out = {}
    for r in rows or []:
        stage, key = r.get("stage"), _key(r.get("uid"))
        if stage not in READ_STAGES or not key or key in out:
            continue
        entry = normalised.get(key)
        items = entry.get("items") if isinstance(entry, dict) else None
        if not isinstance(items, list):
            continue
        groups = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            path = it.get("path") or ""
            stem = os.path.splitext(os.path.basename(path))[0]
            groups.setdefault((os.path.dirname(path), stem, it.get("kind")), []).append(it)
        docs = []
        for (_, _, kind), group in groups.items():
            if all(g.get("superseded") for g in group):          # an older version: only the current one is offered
                continue
            picked = sorted(group, key=lambda g: _rank_of(g.get("name")))[0]
            docs.append(_doc(root, kind, picked, group, today))
        if not docs:
            continue
        docs.sort(key=lambda d: d["modified"], reverse=True)
        want = STAGE_DOC[stage]
        docs.sort(key=lambda d: (0 if d["kind"] == want else 1, KIND_ORDER.index(d["kind"]) if d["kind"] in KIND_ORDER else 99))
        out[key] = {"docs": docs, "primary": 0, "stage": stage}
    return out
