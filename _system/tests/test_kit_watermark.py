"""kit_watermark.py: every pilot gets a slightly different text so a leaked copy can be traced."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit_watermark as W

TEXT = "Kit-ID: {{KIT_ID}}\n{{MARK:send}} Weiter. {{MARK:overwrite}} Und {{MARK:open}}\n"


def test_apply_is_deterministic_and_leaves_no_markers():
    a1, a2 = W.apply(TEXT, "pilot_a"), W.apply(TEXT, "pilot_a")
    assert a1 == a2 and "{{" not in a1 and W.kit_id("pilot_a") in a1


def test_different_pilots_get_different_ids_and_usually_different_wording():
    ids = {W.kit_id("pilot_%d" % i) for i in range(6)}
    assert len(ids) == 6
    texts = {W.apply(TEXT, "pilot_%d" % i).split("\n", 1)[1] for i in range(6)}
    assert len(texts) >= 3


def test_identify_finds_the_pilot_by_id_and_by_wording_without_the_id():
    pilots = ["pilot_%d" % i for i in range(6)]
    leaked = W.apply(TEXT, "pilot_3")
    assert W.identify(leaked, pilots)[0] == "pilot_3"
    stripped = "\n".join(l for l in leaked.split("\n") if "Kit-ID" not in l)
    assert "pilot_3" in W.identify(stripped, pilots)
