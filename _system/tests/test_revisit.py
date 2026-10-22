"""revisit.py: new files in '30 Verlauf' (the landing zone) of processes in conversation. Warranty: nothing is overlooked, nothing is echoed, no note is lost."""
import csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import revisit as RV


def career(tmp_path, stage="Interviewing", note="Kein Nachfassen vor Ende naechster Woche", files=()):
    base = tmp_path / "career"
    role = base / "215 Acme AG" / "Head of Data"
    (role / "30 Verlauf").mkdir(parents=True)
    (base / "_system").mkdir()
    for name in files:
        (role / "30 Verlauf" / name).write_text("x", encoding="utf-8")
    pipe = base / "_system" / "pipeline.csv"
    with open(pipe, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "stage", "folder_id", "last_event", "note"])
        w.writeheader()
        w.writerow({"uid": "215", "company": "Acme AG", "role": "Head of Data", "stage": stage, "folder_id": "", "last_event": "2026-09-20", "note": note})
    return base, role, pipe


def run(base, pipe, today, dry=False):
    args = ["--pipeline", str(pipe), "--base-dir", str(base), "--state", str(base / "_system" / "revisit_state.json"), "--today", today]
    RV.main(args + (["--dry-run"] if dry else []))
    return list(csv.DictReader(open(pipe, newline="", encoding="utf-8")))[0]


def test_files_the_system_wrote_itself_are_not_new_input():
    for name in ("Debrief_Nordberatung__a_Sportwagen_Company_2026-10-01.md", "Nachbereitung_Auftrag_Acme_Lagebild.md", "Recherche_Auftrag_Acme_Lagebild.md"):
        assert RV.is_generated(name), name
    for name in ("09-24 Bewerbungsgespraech_ Naechste Schritte-transcript.txt", "Mail_2026-09-02_Amazon_Application.pdf", "Codewerk Fachinterview.html"):
        assert not RV.is_generated(name), name


def test_the_note_keeps_what_was_there_and_replaces_an_older_revisit_stamp():
    old = "Kein Nachfassen vor Ende naechster Woche; Rueckmeldung bis 09./10.10. (Jonas Weber)"
    n1 = RV.compose_note(old, "2026-10-02", 2, ["Gespraech gefuehrt"], "2026-10-01")
    assert n1.startswith("[Revisit 2026-10-02]") and "Kein Nachfassen vor Ende naechster Woche" in n1 and len(n1) <= RV.NOTE_MAX
    n2 = RV.compose_note(n1, "2026-10-03", 1, ["Korrespondenz"], "2026-10-03")
    assert n2.count("[Revisit") == 1 and "[Revisit 2026-10-03]" in n2 and "Kein Nachfassen vor Ende naechster Woche" in n2


def test_a_long_old_note_is_cut_but_the_revisit_stamp_survives():
    n = RV.compose_note("x" * 900, "2026-10-02", 3, ["Gespraech gefuehrt", "Korrespondenz"], "2026-10-02")
    assert len(n) <= RV.NOTE_MAX and n.startswith("[Revisit 2026-10-02] 3 neue Datei(en)")


def test_screening_is_watched_and_applied_is_not(tmp_path):
    base, role, pipe = career(tmp_path, stage="Screening", files=["10-01 Telefonat HR-transcript.txt"])
    row = run(base, pipe, "2026-10-02")
    assert "[Revisit 2026-10-02]" in row["note"] and "Kein Nachfassen" in row["note"] and row["last_event"] == "2026-10-02" or "[Revisit" in row["note"]
    base2, _, pipe2 = career(tmp_path / "b", stage="Applied", files=["10-01 Telefonat HR-transcript.txt"])
    assert "[Revisit" not in run(base2, pipe2, "2026-10-02")["note"]


def delta(first, second):
    """Output of the second call only: the runner's capsys shim does not reset between reads, pytest's does."""
    return second[len(first):] if second.startswith(first) else second


def test_the_debrief_the_system_wrote_is_neither_reported_nor_ordered_again(tmp_path, capsys):
    base, role, pipe = career(tmp_path, files=["09-24 Gespraech-transcript.txt"])
    run(base, pipe, "2026-10-01")
    first = capsys.readouterr().out
    (role / "30 Verlauf" / "Debrief_Acme_AG_2026-10-01.md").write_text("debrief", encoding="utf-8")
    row = run(base, pipe, "2026-10-02")
    out = delta(first, capsys.readouterr().out)
    assert "new artifact(s)" not in out and "No new artifacts" in out and row["note"].count("[Revisit") == 1
    state = open(base / "_system" / "revisit_state.json", encoding="utf-8").read()
    assert "Debrief_Acme_AG_2026-10-01.md" in state                                   # remembered, so it can never be reported later either


def test_a_real_new_input_after_the_debrief_is_still_reported(tmp_path, capsys):
    base, role, pipe = career(tmp_path, files=["09-24 Gespraech-transcript.txt", "Debrief_Acme_AG_2026-10-01.md"])
    run(base, pipe, "2026-10-01")
    first = capsys.readouterr().out
    (role / "30 Verlauf" / "Mail_2026-10-02_Acme_Einladung.pdf").write_text("m", encoding="utf-8")
    run(base, pipe, "2026-10-02")
    out = delta(first, capsys.readouterr().out)
    assert "Mail_2026-10-02_Acme_Einladung.pdf" in out and "Debrief_Acme_AG" not in out
