"""kit_profile.py: who the kit serves; a broken file never raises."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit_profile as K


def test_defaults_without_a_file(tmp_path):
    p = K.load_profile(str(tmp_path))
    assert p["name"] == "Bewerber:in" and p["brand_name"] == "STAR" and p["photo"] == "" and p["exit_file"] == ""
    assert p["exit_summary"] == {"de": "", "en": ""} and p["proof_examples"] == []


def test_values_are_read_and_trimmed(tmp_path):
    (tmp_path / "profile.json").write_text(json.dumps({
        "name": "  Erika Müller-O'Neil ", "brand_name": "Muster Consulting", "photo": "00 references/foto.jpg",
        "exit_file": "00 references/Exit.md", "exit_summary": {"de": " Kosten. ", "en": "Costs."},
        "proof_examples": [" Programm A ", "", 5, "Programm B"]}), encoding="utf-8")
    p = K.load_profile(str(tmp_path))
    assert p["name"] == "Erika Müller-O'Neil" and p["brand_name"] == "Muster Consulting" and p["photo"].endswith("foto.jpg")
    assert p["exit_summary"] == {"de": "Kosten.", "en": "Costs."} and p["proof_examples"] == ["Programm A", "Programm B"]


def test_broken_or_wrongly_typed_files_fall_back_to_defaults(tmp_path):
    for text in ("{kaputt", "[]", "null", '{"name": 5, "brand_name": "", "exit_summary": "x", "proof_examples": "a"}'):
        (tmp_path / "profile.json").write_text(text, encoding="utf-8")
        p = K.load_profile(str(tmp_path))
        assert p["name"] == "Bewerber:in" and p["brand_name"] == "STAR" and p["exit_summary"] == {"de": "", "en": ""} and p["proof_examples"] == []


def test_results_are_independent_copies(tmp_path):
    a = K.load_profile(str(tmp_path))
    a["proof_examples"].append("x")
    a["exit_summary"]["de"] = "y"
    b = K.load_profile(str(tmp_path))
    assert b["proof_examples"] == [] and b["exit_summary"]["de"] == ""
