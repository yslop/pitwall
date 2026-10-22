"""kit_setup.py: a fresh customer install renders, keeps existing files, and contains nothing of the owner."""
import json, os, shutil, sys
SYSTEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM)
import kit_setup

TERMS = ("Testvorname", "Testnachname", "Etikettenwerk")


def engine_copy(dst):
    """The engine as a customer gets it: code, templates, theme, core.js, examples; no data, no tests, no assets."""
    os.makedirs(dst)
    for name in os.listdir(SYSTEM):
        if name.endswith(".py") and name not in ("update_pipeline.py", "test_milestone4_acceptance.py", "draft_job.py", "browser_pick.py"):
            shutil.copy(os.path.join(SYSTEM, name), dst)
    for name in ("theme.css", "core.js"):
        shutil.copy(os.path.join(SYSTEM, name), dst)
    shutil.copytree(os.path.join(SYSTEM, "templates"), os.path.join(dst, "templates"))
    shutil.copytree(os.path.join(SYSTEM, "kit_examples"), os.path.join(dst, "kit_examples"))


def test_install_creates_profile_pipeline_and_bio_files(tmp_path):
    system = str(tmp_path / "_system")
    engine_copy(system)
    res = kit_setup.install(system, "Erika Muster")
    assert os.path.exists(os.path.join(system, "profile.json")) and os.path.exists(os.path.join(system, "pipeline.csv"))
    assert os.path.exists(tmp_path / "00 references" / "Bio_Bausteine.json") and os.path.exists(tmp_path / "00 references" / "Gespraechs_Playbook.json")
    assert json.load(open(os.path.join(system, "profile.json"), encoding="utf-8"))["name"] == "Erika Muster"
    assert open(os.path.join(system, "pipeline.csv"), encoding="utf-8").read().strip() == ",".join(kit_setup.HEADER)
    assert res["kept"] == [] and len(res["created"]) == 6
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude_md == (tmp_path / "AGENTS.md").read_text(encoding="utf-8") and len(claude_md.encode("utf-8")) < 32 * 1024


def test_install_twice_keeps_everything(tmp_path):
    system = str(tmp_path / "_system")
    engine_copy(system)
    kit_setup.install(system, "Erika Muster")
    with open(os.path.join(system, "pipeline.csv"), "a", encoding="utf-8") as f:
        f.write("7,Acme,Lead,,Applied,,,,,,,,,,,,,,,\n")
    again = kit_setup.install(system, "Anderer Name")
    assert len(again["kept"]) == 6 and again["created"] == []
    assert "Acme" in open(os.path.join(system, "pipeline.csv"), encoding="utf-8").read()
    assert json.load(open(os.path.join(system, "profile.json"), encoding="utf-8"))["name"] == "Erika Muster"


def test_fresh_install_renders_all_pages_with_the_customer_name_and_no_owner_text(tmp_path):
    system = str(tmp_path / "_system")
    engine_copy(system)
    kit_setup.install(system, "Erika Muster")
    assert kit_setup.render(system, "2026-10-07") == 0
    pages = [n for n in os.listdir(tmp_path) if n.endswith(".html")]
    assert {"00_today.html", "01_cockpit.html", "02_pipeline_crm.html", "03_briefings.html"} <= set(pages)
    for name in pages:
        text = open(tmp_path / name, encoding="utf-8").read()
        assert not any(t in text for t in TERMS), name
    assert "Erika Muster" in open(tmp_path / "04_agentur_report.html", encoding="utf-8").read()
