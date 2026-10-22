"""folder_utils.py: role folder matching."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import folder_utils as FU  # noqa: E402


def test_role_folder_matches_by_plain_name_when_all_words_are_stopwords(tmp_path):
    # Kekswerk uid 41: "Lead Data & AI" has no tokens; "(m/w/d)" and "(rejected)" must not matter
    co = tmp_path / "41 Kekswerk (rejected)"
    (co / "Lead Data & AI (rejected)").mkdir(parents=True)
    (co / "Head of Global Application Management (rejected)").mkdir()
    folder, flags = FU.find_role_folder(co, "Lead Data & AI (m/w/d)")
    assert folder.name == "Lead Data & AI (rejected)" and not flags
