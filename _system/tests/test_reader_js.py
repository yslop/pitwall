"""core.js reading pane helpers (readerGroups, readerDocHtml, readerSwitchHtml), run under Node with a stubbed browser."""
import json
import os
import shutil
import subprocess

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_JS = os.path.join(SYSTEM_DIR, "core.js")
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const stub = () => new Proxy(function () {}, { get: (t, k) => (k in t ? t[k] : k === Symbol.toPrimitive ? () => "" : k === "then" ? undefined : stub()), apply: () => stub() });
const doc = stub();
const root = stub();
root.dataset = { today: "2026-10-02" };
doc.documentElement = root;
doc.readyState = "complete";
const ctx = { document: doc, window: stub(), localStorage: stub(), console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[process.argv.length - 1], "utf8") + "\n;globalThis.__JS26 = JS26;", ctx);
const J = ctx.__JS26;
const input = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(J[input.fn].apply(null, input.args)));
"""


def call(fn, *args):
    res = subprocess.run([NODE, "-e", HARNESS, CORE_JS], input=json.dumps({"fn": fn, "args": list(args)}), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr[-600:]
    return json.loads(res.stdout.strip().splitlines()[-1])


def doc(kind="briefing", mode="md", name="B.md", path="1 A/B.md", html="<p>x</p>", modified="2026-10-01", link=None, label="Briefing", truncated=False):
    return {"kind": kind, "label": label, "name": name, "path": path, "where": "", "modified": modified, "link": link, "mode": mode, "html": html, "truncated": truncated}


def row(uid, stage, score=50, company="Firma", role="Rolle"):
    return {"uid": uid, "stage": stage, "score": score, "company": company, "role": role}


def test_groups_follow_the_stage_order_and_sort_by_score():
    if not NODE:
        return
    rows = [row("1", "Applied", 10), row("2", "Final", 40), row("3", "Interviewing", 70), row("4", "Interviewing", 90), row("5", "Closed"), row("6", "Screening")]
    reader = {k: {"docs": [doc()], "primary": 0} for k in ("1", "2", "3", "4", "5")}
    groups = call("readerGroups", rows, reader)
    assert [g["stage"] for g in groups] == ["Final", "Interviewing", "Applied"]          # Screening has no documents, Closed is no reading stage
    assert [i["r"]["uid"] for i in groups[1]["items"]] == ["4", "3"]


def test_uids_are_matched_like_the_index_does():
    if not NODE:
        return
    groups = call("readerGroups", [row("09", "Final")], {"9": {"docs": [doc()], "primary": 0}})
    assert len(groups) == 1 and groups[0]["items"][0]["entry"]["docs"][0]["name"] == "B.md"


def test_markdown_documents_show_their_html_and_escape_the_name():
    if not NODE:
        return
    h = call("readerDocHtml", doc(name="<img src=x onerror=alert(1)>.md", html="<h1>Titel</h1>"))
    assert "<h1>Titel</h1>" in h and "<img" not in h and "&lt;img src=x onerror=alert(1)&gt;.md" in h


def test_frames_are_sandboxed_and_use_the_encoded_relative_path():
    if not NODE:
        return
    h = call("readerDocHtml", doc(kind="jd_intel", mode="frame", name="JD #1.html", path="133 X/Rolle Ä/JD #1?.html", html=None))
    assert "<iframe" in h and 'sandbox=""' in h and 'src="133%20X/Rolle%20%C3%84/JD%20%231%3F.html"' in h


def test_links_open_the_file_and_do_not_embed_anything():
    if not NODE:
        return
    h = call("readerDocHtml", doc(kind="cheat_sheet", mode="link", name="Cheat.pdf", path="1 A/Cheat.pdf", html=None))
    assert "<iframe" not in h and 'href="1%20A/Cheat.pdf"' in h
    g = call("readerDocHtml", doc(mode="link", html=None, link="https://docs.google.com/document/d/1Arfe/edit"))
    assert 'href="https://docs.google.com/document/d/1Arfe/edit"' in g


def test_a_cut_document_says_so_and_unknown_modes_are_harmless():
    if not NODE:
        return
    assert "gekürzt" in call("readerDocHtml", doc(truncated=True, html="<p>a</p>"))
    odd = call("readerDocHtml", doc(mode="evil", html="<script>alert(1)</script>"))
    assert "<script" not in odd.lower()
    assert call("readerDocHtml", None) != ""


def test_switcher_marks_the_active_document_and_escapes_text():
    if not NODE:
        return
    docs = [doc(label="Briefing", modified="2026-10-01"), doc(kind="jd_intel", label="<b>JD-Intel</b>", modified="2026-09-29")]
    h = call("readerSwitchHtml", docs, 1)
    assert h.count("data-doc=") == 2 and 'data-doc="1"' in h and "<b>JD-Intel</b>" not in h
    assert h.count('aria-pressed="true"') == 1 and "29.09.2026" in h
    assert call("readerSwitchHtml", [], 0) == ""


def test_restyled_pages_are_shown_through_a_sandboxed_srcdoc():
    if not NODE:
        return
    h = call("readerDocHtml", doc(kind="jd_intel", mode="page", name="JD.html", path="1 A/JD.html", html='<html><body onload="alert(1)">"x"</body></html>'))
    assert 'sandbox=""' in h and 'srcdoc="' in h and "<body onload" not in h and "&lt;body onload=" in h and "&quot;x&quot;" in h


def quality(**over):
    q = {"lint": "pass", "lint_rules": [], "facts": 4, "inferences": 6, "facts_unsourced": 0, "sources": 3, "domains": 3, "oldest_source_age": 5,
         "unverified": 0, "open_section": True, "dangling": []}
    q.update(over)
    return q


def test_the_quality_strip_shows_lint_counts_sources_and_age():
    if not NODE:
        return
    h = call("readerQualityHtml", quality())
    for needle in ("Lint bestanden", "4 Fakten", "6 Schlüsse", "3 Quellen", "3 Domänen", "älteste Quelle 5 Tage", "qchip ok"):
        assert needle in h, needle
    assert "qchip warn" not in h and "qchip fail" not in h


def test_the_quality_strip_flags_problems_and_escapes_rule_names():
    if not NODE:
        return
    h = call("readerQualityHtml", quality(lint="fail", lint_rules=["<b>x</b>"], facts_unsourced=2, domains=1, oldest_source_age=40, unverified=3,
                                         open_section=False, dangling=[9]))
    assert "qchip fail" in h and "Lint: Fehler" in h and "&lt;b&gt;x&lt;/b&gt;" in h and "<b>x</b>" not in h
    for needle in ("2 Fakten ohne Quelle", "1 Domänen", "40 Tage", "3 nicht verifiziert", "Abschnitt „Offen“ fehlt", "Verweis [9] ohne Quelle"):
        assert needle in h, needle


def test_no_quality_no_strip_and_the_document_view_includes_it_when_present():
    if not NODE:
        return
    assert call("readerQualityHtml", None) == "" and call("readerQualityHtml", "x") == ""
    d = doc(html="<p>x</p>")
    d["quality"] = quality()
    assert "reader-quality" in call("readerDocHtml", d) and "reader-quality" not in call("readerDocHtml", doc(html="<p>x</p>"))
