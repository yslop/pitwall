"""top10.py: pins survive bad files and bad values; pin/unpin/exclude semantics."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import top10 as T  # noqa: E402


def test_missing_and_corrupt_files_are_empty_lists(tmp_path):
    assert T.load(str(tmp_path / "none.json")) == {"pinned": [], "excluded": []}
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert T.load(str(bad)) == {"pinned": [], "excluded": []}
    for shape in ("[]", '"x"', "null", '{"pinned": "215"}', '{"pinned": {"a": 1}}'):
        bad.write_text(shape, encoding="utf-8")
        assert T.load(str(bad)) == {"pinned": [], "excluded": []}, shape


def test_values_are_normalised_deduplicated_and_junk_is_dropped(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"pinned": [215, "215", "0216", True, None, "abc", 1.5, [3]], "excluded": []}), encoding="utf-8")
    assert T.load(str(p))["pinned"] == [215, 216]                   # bool, None, text, floats and lists are dropped


def test_pin_is_idempotent_keeps_order_and_writes_atomically(tmp_path):
    p = str(tmp_path / "t.json")
    T.pin(p, 215)
    T.pin(p, "217")
    T.pin(p, 215)
    assert T.load(p)["pinned"] == [215, 217] and not os.path.exists(p + ".tmp")


def test_unpin_and_exclude_and_pin_overrides_exclude(tmp_path):
    p = str(tmp_path / "t.json")
    for u in (1, 2, 3):
        T.pin(p, u)
    assert T.unpin(p, 2)["pinned"] == [1, 3]
    d = T.exclude(p, 3)
    assert d["pinned"] == [1] and d["excluded"] == [3]
    assert T.pin(p, 3)["pinned"] == [1, 3] and T.load(p)["excluded"] == []
    assert T.unpin(p, 999)["pinned"] == [1, 3]                       # unknown uid is a no-op


def test_a_pinned_uid_that_is_also_excluded_on_disk_counts_as_excluded(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"pinned": [5, 6], "excluded": [6]}), encoding="utf-8")
    assert T.load(str(p)) == {"pinned": [5], "excluded": [6]}


def test_slots_are_capped_at_ten():
    assert T.slots_used({"pinned": list(range(15)), "excluded": []}) == 10 and T.slots_used({"pinned": [1], "excluded": []}) == 1


# ---- final review, fix pass ---------------------------------------------------------------------
def test_a_hand_edited_file_with_a_syntax_error_is_backed_up_before_pin_overwrites_it(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('{"pinned": [5, 6], "excluded": [9],}', encoding="utf-8")            # trailing comma: invalid JSON
    T.pin(str(p), 7)
    backups = [f for f in os.listdir(tmp_path) if f.startswith("t.json.corrupt-")]
    assert len(backups) == 1 and (tmp_path / backups[0]).read_text(encoding="utf-8") == '{"pinned": [5, 6], "excluded": [9],}'
    assert T.load(str(p))["pinned"] == [7]
    assert T.unpin(str(tmp_path / "missing.json"), 1)["pinned"] == []                   # no file: no backup, no crash
