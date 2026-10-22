"""core.js intel helpers (intelHtml, intelCount, intelStamp), run under Node with a stubbed browser. Skipped without Node."""
import json
import os
import shutil
import subprocess
import sys

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_JS = os.path.join(SYSTEM_DIR, "core.js")
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const stub = () => new Proxy(function () {}, { get: (t, k) => (k in t ? t[k] : k === Symbol.toPrimitive ? () => "" : k === "then" ? undefined : stub()), apply: () => stub(), construct: () => stub() });
const doc = stub();
const root = stub();
root.dataset = { today: "2026-09-25" };
doc.documentElement = root;
doc.readyState = "complete";
const ctx = { document: doc, window: stub(), localStorage: stub(), console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[process.argv.length - 1], "utf8") + "\n;globalThis.__JS26 = JS26;", ctx);
const J = ctx.__JS26;
const input = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify({ out: input.entries.map(e => ({ html: J.intelHtml(e), count: J.intelCount(e) })), stamp: J.intelStamp(input.idx), keys: ["09", "119", "007", "abc", "", 5].map(J.intelKey) }));
"""


def run_all_js(entries, idx=None):
    """intelHtml / intelCount per entry and intelStamp(idx), computed by the real core.js under Node."""
    res = subprocess.run([NODE, "-e", HARNESS, CORE_JS], input=json.dumps({"entries": entries, "idx": idx}), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr[-600:]
    return json.loads(res.stdout.strip().splitlines()[-1])


def run_js(entries):
    return run_all_js(entries)["out"]


def item(name="Cheat.pdf", kind="cheat_sheet", path="133 X/Cheat.pdf", where="", modified="2026-09-11", link=None, superseded=False):
    return {"name": name, "kind": kind, "path": path, "where": where, "modified": modified, "link": link, "superseded": superseded}



# ---- intelHtml ----------------------------------------------------------------------------------
def test_missing_entry_and_empty_entry_say_so():
    if not NODE:
        return
    out = run_js([None, {"folders": ["133 X"], "items": [], "warnings": []}])
    assert "intel_index.py nicht gelaufen" in out[0]["html"] and out[0]["count"] == 0
    assert "Noch kein Cheat Sheet" in out[1]["html"] and out[1]["count"] == 0


def test_warnings_are_shown_even_without_files():
    if not NODE:
        return
    out = run_js([{"folders": [], "items": [], "warnings": ["Kein Ordner mit dem Präfix 184 gefunden"]}])
    assert "Kein Ordner mit dem Präfix 184" in out[0]["html"] and "intel-warn" in out[0]["html"]


def test_links_are_encoded_relative_paths_or_the_docs_url():
    if not NODE:
        return
    e = {"folders": ["133 X"], "warnings": [], "items": [
        item(path="133 Nordberatung (active)/Rolle Ä/20 Vorbereitung/Cheat #1?.pdf"),
        item(name="Gdoc", path="131 Hansehandel/x.gdoc", link="https://docs.google.com/document/d/1Arfe/edit")]}
    html = run_js([e])[0]["html"]
    assert 'href="133%20Nordberatung%20(active)/Rolle%20%C3%84/20%20Vorbereitung/Cheat%20%231%3F.pdf"' in html
    assert 'href="https://docs.google.com/document/d/1Arfe/edit"' in html


def test_names_and_paths_are_escaped():
    if not NODE:
        return
    e = {"folders": ["1 X"], "warnings": ["<b>warn</b>"], "items": [
        item(name="<img src=x onerror=alert(1)>.pdf", path='1 X/a"b.pdf', where="<i>role</i>")]}
    html = run_js([e])[0]["html"]
    assert "<img" not in html and "<b>" not in html and "<i>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;.pdf" in html and 'a%22b.pdf' in html


def test_labels_dates_superseded_and_default_location():
    if not NODE:
        return
    e = {"folders": ["1 X"], "warnings": [], "items": [
        item(kind="cheat_sheet", where="", modified="2026-09-11"),
        item(name="Old.pdf", kind="cockpit", where="Rolle A", modified="2026-09-01", superseded=True)]}
    out = run_js([e])[0]
    assert "Cheat Sheet" in out["html"] and "Cockpit" in out["html"]
    assert "Arbeitgeber-Ordner · 11.09.2026" in out["html"] and "Rolle A · 01.09.2026 · ältere Fassung" in out["html"]
    assert 'class="intel-item old"' in out["html"] and out["count"] == 1        # only current files count for the badge


# ---- index age ----------------------------------------------------------------------------------
def test_stamp_shows_the_index_date_and_warns_when_old():
    if not NODE:
        return
    assert "Index vom 25.09.2026" in run_all_js([], {"generated": "2026-09-25T09:00:00", "uids": {}})["stamp"]
    assert "veraltet" not in run_all_js([], {"generated": "2026-09-24T09:00:00", "uids": {}})["stamp"]      # 1 day: fine
    old = run_all_js([], {"generated": "2026-09-20T09:00:00", "uids": {}})["stamp"]
    assert "Index vom 20.09.2026" in old and "veraltet" in old
    assert run_all_js([], None)["stamp"] == "" and run_all_js([], {})["stamp"] == ""


def test_intel_key_normalises_zero_padded_uids_like_the_index_does():
    if not NODE:
        return
    assert run_all_js([])["keys"] == ["9", "119", "7", "abc", "", "5"]


COCKPIT_HARNESS = HARNESS.replace(
    'console.log(JSON.stringify({ out: input.entries.map(e => ({ html: J.intelHtml(e), count: J.intelCount(e) })), stamp: J.intelStamp(input.idx), keys: ["09", "119", "007", "abc", "", 5].map(J.intelKey) }));',
    'console.log(JSON.stringify({ links: input.uids.map(u => J.cockpitLink(u, input.idx)) }));')


def run_cockpit_links(uids, idx):
    res = subprocess.run([NODE, "-e", COCKPIT_HARNESS, CORE_JS], input=json.dumps({"uids": uids, "idx": idx}), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr[-600:]
    return json.loads(res.stdout.strip().splitlines()[-1])["links"]


def test_cockpit_link_points_to_the_newest_generated_conversation_cockpit_only():
    if not NODE:
        return
    idx = {"uids": {
        "41": {"items": [item("Cockpit_Kekswerk_2026-10-01.html", "cockpit", "41 B/20 V/Cockpit_Kekswerk_2026-10-01.html", modified="2026-10-01", superseded=True),
                         item("Cockpit_Kekswerk_2026-10-07.html", "cockpit", "41 B/20 V/Cockpit_Kekswerk_2026-10-07.html", modified="2026-10-07")]},
        "133": {"items": [item("Nordberatung_Cockpit_Brandt_20260911.pdf", "cockpit", "133 M/Nordberatung_Cockpit_Brandt_20260911.pdf", modified="2026-09-08")]},
        "182": {"items": [item("DAK_Briefing_v1.pdf", "briefing", "182 D/DAK_Briefing_v1.pdf")]}}}
    links = run_cockpit_links(["41", "041", "133", "182", "999"], idx)
    assert links[0]["href"] == "41%20B/20%20V/Cockpit_Kekswerk_2026-10-07.html" and links[0]["modified"] == "2026-10-07"
    assert links[1] == links[0]                                  # leading zeros are the same uid
    assert links[2] is None and links[3] is None and links[4] is None
