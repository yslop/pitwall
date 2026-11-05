import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expert_view as X
import rank as R
import top10 as T
import today_view as TV

TODAY = "2026-09-26"


def prow(uid, stage="Interviewing", company="Beispiel AG", role="Head of Data", idle="3", nxt="Antwort abwarten", due="", note="", folder_id=""):
    return {"uid": str(uid), "company": company, "role": role, "stage": stage, "days_idle": idle, "next_action": nxt, "due": due, "note": note, "folder_id": folder_id}


def tr(uid, datum, von="Screening", nach="Interviewing", why="Fachgespräch"):
    return {"uid": str(uid), "datum": datum, "von": von, "nach": nach, "ausloeser": why, "quelle": "briefing"}


def tree(tmp_path, uid=133):
    base = tmp_path / "career"
    v = base / ("%d Beispiel (active)" % uid) / "Rolle A" / "30 Verlauf"
    v.mkdir(parents=True)
    (base / ("%d Beispiel (active)" % uid) / "Rolle B (rejected)" / "30 Verlauf").mkdir(parents=True)
    return base, v


def test_scan_finds_debriefs_and_transcripts_in_open_role_folders_only(tmp_path):
    base, v = tree(tmp_path)
    (v / "Debrief_Beispiel_AG_2026-09-25.md").write_text("x", encoding="utf-8")
    (v / "Mitschrift_Transkript_2026-09-25.txt").write_text("x", encoding="utf-8")
    (v / "Einladung.pdf").write_bytes(b"%PDF")
    (v / ".DS_Store").write_text("x")
    (base / "133 Beispiel (active)" / "Rolle B (rejected)" / "30 Verlauf" / "Debrief_Alt_2026-01-01.md").write_text("x", encoding="utf-8")
    got = X.scan_folders(str(base), [prow(133), prow(999), prow(5, stage="Applied")])
    assert got["133"] == {"debriefs": [("2026-09-25", "Debrief_Beispiel_AG_2026-09-25.md")], "transcripts": ["Mitschrift_Transkript_2026-09-25.txt"]}
    assert got["999"] == {"debriefs": [], "transcripts": []} and "5" not in got


def test_scan_survives_broken_finders_and_odd_rows(tmp_path):
    def boom(base, uid, fid): raise OSError("Drive offline")
    assert X.scan_folders(str(tmp_path), [prow(1)], finder=boom) == {"1": {"debriefs": [], "transcripts": []}}
    assert X.scan_folders(str(tmp_path), None) == {} and X.scan_folders(str(tmp_path), ["x", None, {"uid": None, "stage": "Final"}], finder=lambda *a: (None, [])) == {"": {"debriefs": [], "transcripts": []}}


def cards(rows, **kw):
    return X.build_expert(rows, kw.pop("transitions", []), kw.pop("today", TODAY), **kw)


def test_cards_cover_only_conversation_stages_final_first_and_skip_channels():
    rows = [prow(1, "Screening"), prow(2, "Interviewing"), prow(3, "Final"), prow(4, "Applied"), prow(5, "Interviewing")]
    got = cards(rows, channels={"channels": {"5": {"type": "headhunter"}}})
    assert [c["uid"] for c in got] == ["3", "2", "1"] and [c["stage"] for c in got] == ["Final", "Interviewing", "Screening"]
    assert cards([]) == [] and cards(None) == [] and X.build_expert(rows, [], "kein Datum") == []


def test_timeline_shows_the_last_four_stage_changes_in_date_order_and_escapes_nothing_itself():
    t = [tr(2, "2026-02-13"), tr(2, "2026-03-01", "Interviewing", "Interviewing", "Runde 2"), tr(2, "2026-04-01", why="<b>x</b>"), tr(2, "2026-05-01"), tr(2, "2026-06-01"), tr(9, "2026-06-02"),
         {"uid": "2", "datum": "kaputt"}, "x", None]
    c = cards([prow(2)], transitions=t)[0]
    assert [x["date"] for x in c["timeline"]] == ["01.03.26", "01.04.26", "01.05.26", "01.06.26"] and c["timeline"][1]["text"].endswith("· <b>x</b>")     # the template escapes
    assert cards([prow(2)], transitions=[])[0]["timeline"] == []


def check(card, label):
    return next(k for k in card["checks"] if k["label"] == label)


def test_the_checklist_flags_what_is_missing_after_the_last_conversation():
    t = [tr(2, "2026-09-24")]
    c = cards([prow(2)], transitions=t, scan={"2": {"debriefs": [], "transcripts": []}})[0]
    assert check(c, "Debrief zum letzten Gespräch")["ok"] == "" and "--after-interview" in check(c, "Debrief zum letzten Gespräch")["todo"]
    assert check(c, "Notizen oder Gedächtnisprotokoll abgelegt")["ok"] == "" and check(c, "Briefing oder Cheat Sheet")["ok"] == "" and c["open_items"] == 3
    done = cards([prow(2)], transitions=t, scan={"2": {"debriefs": [("2026-09-25", "Debrief_X_2026-09-25.md")], "transcripts": ["Notizen.md"]}},
                 intel_state={"2": {"docs": {"briefing:": {"doc": "briefing", "latest": "v1", "versions": {"v1": {"result": "pass"}}}}}})[0]
    assert done["open_items"] == 0 and check(done, "Briefing oder Cheat Sheet")["detail"] == "Briefing v1 · Lint: bestanden"
    old = cards([prow(2)], transitions=t, scan={"2": {"debriefs": [("2026-09-01", "Debrief_Alt_2026-09-01.md")], "transcripts": []}})[0]
    assert check(old, "Debrief zum letzten Gespräch")["ok"] == ""                                              # a debrief from before the last conversation does not count


def test_an_existing_intel_file_counts_and_follow_up_is_flagged_after_a_week_of_silence():
    intel = {"uids": {"2": {"items": [{"name": "Cheat Sheet"}]}}}
    c = cards([prow(2, idle="9")], intel=intel)[0]
    assert check(c, "Briefing oder Cheat Sheet")["ok"] == "ja" and check(c, "Nachfassen")["ok"] == "" and "9 Tage" in check(c, "Nachfassen")["detail"]
    assert check(cards([prow(2, idle="3")])[0], "Nachfassen")["ok"] == "ja" and check(cards([prow(2, "Final", idle="10")])[0], "Nachfassen")["ok"] == "ja" and check(cards([prow(2, "Screening", idle="30")])[0], "Nachfassen")["ok"] == "ja"


def test_next_step_due_dates_overdue_coverage_and_hostile_values():
    c = cards([prow(2, due="2026-09-20", nxt="Termin klären")], coverage={"2": {"share": 0.5, "proven": 2, "must": 4}})[0]
    assert c["overdue"] == "overdue" and c["due"] == "2026-09-20" and c["next_action"] == "Termin klären" and c["coverage"] == "Abdeckung 50 % (2 von 4 Muss)"
    weird = cards([prow(2, idle="x", due="TBD", nxt="", note="n" * 500), {"uid": "3", "stage": "Final", "days_idle": None, "due": None}])
    assert [w["idle"] for w in weird] == [0, 0] and weird[1]["due"] == "" and weird[1]["next_action"] == "—" and len(weird[0]["note"]) <= 200
    assert cards([prow(2)], coverage=[], intel_state="x", scan=5, channels="x", intel=[])[0]["coverage"] == ""


def test_suggestions_show_on_today_with_score_reasons_and_skip_pinned_rows():
    state = {"date": "2026-09-26", "suggested": ["5", "6"], "ranked": [{"uid": "5", "company": "A", "role": "R", "stage": "Watchlist", "score": 71, "reasons": ["Fit 80 %", "Abdeckung offen", "Lane X"]},
                                                                      {"uid": "6", "company": "B", "role": "S", "stage": "Applied", "score": "x", "reasons": "kaputt"}, "junk", {"uid": "7"}]}
    rows = [{"uid": "1", "company": "C", "role": "D", "stage": "Watchlist", "note": "", "lane": ""}]
    ctx = TV.build_context(rows, None, TODAY, top10={"pinned": [1], "excluded": []}, rank_state=state)
    assert [(s["uid"], s["score"], s["why"]) for s in ctx["suggestions"]] == [("5", 71, "Fit 80 % · Abdeckung offen · Lane X"), ("6", 0, "")] and ctx["free_places"] == 9
    ctx2 = TV.build_context(rows, None, TODAY, top10={"pinned": [5], "excluded": []}, rank_state=state)
    assert [s["uid"] for s in ctx2["suggestions"]] == ["6"]
    for bad in (None, [], {"ranked": "x"}, {"ranked": [1], "suggested": 5}):
        assert TV.build_context(rows, None, TODAY, rank_state=bad)["suggestions"] == []


def test_top10_cli_pins_unpins_excludes_and_validates(tmp_path, capsys):
    f = str(tmp_path / "top10.json")
    assert T.main(["pin", "215", "--file", f]) == 0 and T.main(["pin", "216", "--file", f]) == 0 and T.main(["exclude", "216", "--file", f]) == 0
    assert T.load(f) == {"pinned": [215], "excluded": [216]}
    assert T.main(["unpin", "215", "--file", f]) == 0 and T.load(f)["pinned"] == []
    assert T.main(["pin", "abc", "--file", f]) == 2 and T.main(["pin", "--file", f]) == 2
    assert T.main(["show", "--file", f]) == 0
    assert "gepinnt" in capsys.readouterr().out


def test_the_expert_page_and_the_alias_are_rendered_with_the_nav_entry(tmp_path):
    render_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "render.py")
    cols = "uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,contacts,folder_id,next_action,due,note,ts_confidence,ts_fit_score\n"
    data = tmp_path / "pipeline.csv"
    data.write_text(cols + "2,Beispiel <AG>,Head,Executive,Interviewing,,,2026-09-24,2,0,0,,HH,,,Antwort abwarten,,n,,\n3,Neu,Rolle,Executive,Applied,,,2026-09-24,2,0,0,,HH,,,,,n,,\n", encoding="utf-8")
    trans = tmp_path / "transitions.csv"
    trans.write_text("uid,datum,von,nach,ausloeser,quelle\n2,2026-09-24,Screening,Interviewing,Fachgespräch,briefing\n", encoding="utf-8")
    rank = tmp_path / "rank_state.json"
    rank.write_text(json.dumps({"date": TODAY, "suggested": ["3"], "ranked": [{"uid": "3", "company": "Neu", "role": "Rolle", "stage": "Applied", "score": 60, "reasons": ["Fit 60 %"]}]}), encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, render_py, "--data", str(data), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"), "--transitions", str(trans),
                          "--rank", str(rank), "--today", TODAY, "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    import re
    page = (out / "05_expert.html").read_text(encoding="utf-8")
    body = re.sub(r"<script.*?</script>", "", page, flags=re.S)                                          # the data block carries the raw value; the markup must not
    assert "Beispiel &lt;AG&gt;" in body and "Beispiel <AG>" not in body and "Nächster Schritt" in body and "Screening → Interviewing" in body and "Debrief zum letzten Gespräch" in body
    assert (out / "expert.html").read_text(encoding="utf-8") == page
    assert 'href="05_expert.html"' in (out / "00_today.html").read_text(encoding="utf-8") and "Fokus: aussichtsreichste Verfahren" in (out / "00_today.html").read_text(encoding="utf-8")
    empty = tmp_path / "e.csv"
    empty.write_text(cols, encoding="utf-8")
    res2 = subprocess.run([sys.executable, render_py, "--data", str(empty), "--prep", str(tmp_path / "n.json"), "--folders", str(tmp_path / "n.tsv"), "--transitions", str(tmp_path / "nope.csv"),
                           "--rank", str(tmp_path / "kaputt.json"), "--today", TODAY, "--out", str(tmp_path / "o2"), "--no-pdf"], capture_output=True, text=True)
    assert res2.returncode == 0 and "kein Verfahren in einer Gesprächsphase" in (tmp_path / "o2" / "05_expert.html").read_text(encoding="utf-8")


# ---- review fix pass -------------------------------------------------------------------------------------------------------
def test_only_a_real_conversation_counts_for_the_debrief_check_not_an_invitation_or_a_planned_date():
    scan = {"2": {"debriefs": [("2026-09-20", "Debrief_X_2026-09-20.md")], "transcripts": []}}
    planned = cards([prow(2)], transitions=[tr(2, "2026-09-18"), tr(2, "2026-10-05", "Interviewing", "Interviewing", "2. Runde geplant")], scan=scan)[0]
    assert check(planned, "Debrief zum letzten Gespräch")["ok"] == "ja"                                    # a future date is not a conversation yet
    invited = cards([prow(2, "Screening")], transitions=[tr(2, "2026-09-25", "Applied", "Screening", "Einladung zum Termin")], scan={"2": {"debriefs": [], "transcripts": []}})[0]
    assert check(invited, "Debrief zum letzten Gespräch")["ok"] == "ja"                                    # an invitation is not a conversation
    talked = cards([prow(2, "Screening")], transitions=[tr(2, "2026-09-25", "Applied", "Screening", "Telefonat mit HR geführt")], scan={"2": {"debriefs": [], "transcripts": []}})[0]
    assert check(talked, "Debrief zum letzten Gespräch")["ok"] == ""
    none = cards([prow(2)], transitions=[])[0]
    assert check(none, "Debrief zum letzten Gespräch")["detail"] == "kein Gespräch in transitions.csv"


def test_the_scan_uses_the_role_folder_of_the_process_and_only_real_transcript_names(tmp_path):
    base = tmp_path / "career"
    for role, deb in (("Governance Officer", "Debrief_A_2026-09-25.md"), ("Analytics Officer", None)):
        v = base / "7 Acme (active)" / role / "30 Verlauf"
        v.mkdir(parents=True)
        if deb:
            (v / deb).write_text("x", encoding="utf-8")
    ai = base / "7 Acme (active)" / "Analytics Officer" / "30 Verlauf"
    for n in ("Notes_Einladung.pdf", "Release-Notes_Produkt.pdf", "Memo-Gehalt.pdf", "Protokoll_Absage.pdf", "Keynote.pdf"):
        (ai / n).write_text("x", encoding="utf-8")
    got = X.scan_folders(str(base), [prow(7, role="Analytics Officer")])
    assert got["7"] == {"debriefs": [], "transcripts": []}
    (ai / "Mitschrift_Transkript_2026-09-20.txt").write_text("x", encoding="utf-8")
    (ai / "Gespraechsnotizen_Runde1.md").write_text("x", encoding="utf-8")
    assert sorted(X.scan_folders(str(base), [prow(7, role="Analytics Officer")])["7"]["transcripts"]) == ["Gespraechsnotizen_Runde1.md", "Mitschrift_Transkript_2026-09-20.txt"]
    assert X.scan_folders(str(base), [prow(7, role="Governance Officer")])["7"]["debriefs"] == [("2026-09-25", "Debrief_A_2026-09-25.md")]


def test_a_failed_lint_is_not_a_ready_briefing_final_needs_follow_up_after_two_weeks_and_dates_carry_the_year():
    failed = cards([prow(2)], intel_state={"2": {"docs": {"briefing:": {"doc": "briefing", "latest": "v1", "versions": {"v1": {"result": "fail"}}}}}})[0]
    assert check(failed, "Briefing oder Cheat Sheet")["ok"] == ""
    assert check(cards([prow(2, "Final", idle="20")])[0], "Nachfassen")["ok"] == "" and check(cards([prow(2, "Final", idle="10")])[0], "Nachfassen")["ok"] == "ja"
    assert cards([prow(2)], transitions=[tr(2, "2026-02-13")])[0]["timeline"][0]["date"] == "13.02.26"


def test_debriefs_with_german_dates_count_too(tmp_path):
    base = tmp_path / "career"
    v = base / "7 Acme (active)" / "Rolle" / "30 Verlauf"
    v.mkdir(parents=True)
    (v / "Debrief_Acme_15.09.2026.md").write_text("x", encoding="utf-8")
    assert X.scan_folders(str(base), [prow(7, role="Rolle")])["7"]["debriefs"] == [("2026-09-15", "Debrief_Acme_15.09.2026.md")]


def test_top10_cli_rejects_lookalike_digits_and_a_missing_folder(tmp_path, capsys):
    f = str(tmp_path / "x" / "top10.json")
    assert T.main(["pin", "²", "--file", f]) == 2
    assert T.main(["pin", "5", "--file", f]) == 2 and "top10:" in capsys.readouterr().err


def test_suggestions_name_the_stage_in_words_and_the_card_explains_the_top_10():
    state = {"date": TODAY, "suggested": ["5", "6"], "ranked": [{"uid": "5", "company": "A", "role": "R", "stage": "Applied", "score": 50, "reasons": []},
                                                              {"uid": "6", "company": "B", "role": "S", "stage": "Watchlist", "score": 40, "reasons": []}]}
    ctx = TV.build_context([], None, TODAY, top10={"pinned": [], "excluded": []}, rank_state=state)
    assert [s["stage"] for s in ctx["suggestions"]] == ["beworben", "noch nicht beworben"]
