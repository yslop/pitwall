"""intake.py: inbox -> pipeline row, folders, archive move, pin. Synthetic trees only."""
import builtins
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import intake as I  # noqa: E402
import top10  # noqa: E402

HEADER = ("uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,contacts,"
          "folder_id,next_action,due,note,ts_confidence,ts_fit_score\n")
TODAY = "2026-09-26"
POSTING = "Firma: Blanco GmbH + Co KG\nRolle: Head of Global E-Commerce (m/w/d)\nLink: https://example.org/job/1\nOrt: Oberderdingen\nNotiz: von Frau Beispiel empfohlen\n\nWir suchen eine Führungskraft für Data & AI.\nAufgaben: Plattform, Governance.\n"


def env(tmp_path, rows=""):
    root = tmp_path / "root"
    system = root / "_system"
    system.mkdir(parents=True)
    (root / "_Eingang").mkdir()
    (system / "pipeline.csv").write_text(HEADER + rows, encoding="utf-8")
    (system / "folders.tsv").write_text("133\t133 Nordberatung\tid133\n", encoding="utf-8")
    (system / "jd_cache.json").write_text(json.dumps({"215": "orphan from an old discovery run"}), encoding="utf-8")
    (root / "133 Nordberatung (active)").mkdir()
    (root / "214 HANDELSBANK AG").mkdir()
    return root, system, root / "_Eingang"


def rows_of(system):
    with open(system / "pipeline.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(root, system, dry_run=False, extractor=None):
    return I.run(str(root), str(system), TODAY, dry_run=dry_run, extractor=extractor or (lambda p: None))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def drop(inbox, name, text=POSTING):
    p = inbox / name
    p.write_text(text, encoding="utf-8")
    return p


# ---- parsing ------------------------------------------------------------------------------------
def test_headers_and_body_are_split():
    fields, body = I.parse_headers(POSTING)
    assert fields == {"company": "Blanco GmbH + Co KG", "role": "Head of Global E-Commerce (m/w/d)", "link": "https://example.org/job/1",
                      "location": "Oberderdingen", "note": "von Frau Beispiel empfohlen"}
    assert body.startswith("Wir suchen") and "Firma:" not in body


def test_file_name_pattern_variants():
    assert I.name_pattern("Blanco GmbH - Head of E-Commerce") == ("Blanco GmbH", "Head of E-Commerce")
    assert I.name_pattern("Blanco – Head of E-Commerce") == ("Blanco", "Head of E-Commerce")
    assert I.name_pattern("Blanco — Head") == ("Blanco", "Head")
    assert I.name_pattern("Stellenanzeige") is None and I.name_pattern(" - x") is None


def test_normalisation_for_duplicate_detection():
    assert I.norm_company("Blanco GmbH + Co KG") == I.norm_company("BLANCO")
    assert I.norm_company("Nordberatung (a Sportwagen Company)") == "nordberatung"
    assert I.norm_role("Head of Global E-Commerce (m/w/d)") == I.norm_role("head of global e-commerce")


# ---- the happy path -----------------------------------------------------------------------------
def test_markdown_posting_becomes_row_folders_cache_pin_and_is_archived(tmp_path):
    root, system, inbox = env(tmp_path, "133,Nordberatung,Manager,Data/AI Arch,Interviewing,,,,,,,,,,,,,n,,\n")
    src = drop(inbox, "blanco.md")
    digest = sha(src)
    rep = run(root, system)
    assert [n["uid"] for n in rep["new"]] == [215]                       # above pipeline (133) and existing folders (214)
    row = rows_of(system)[-1]
    assert (row["uid"], row["company"], row["stage"], row["location"]) == ("215", "Blanco GmbH + Co KG", "Watchlist", "Oberderdingen")
    assert row["role"] == "Head of Global E-Commerce (m/w/d)" and row["last_event"] == TODAY and row["days_idle"] == "0"
    assert row["note"].startswith("Eigener Fund (Eingang 2026-09-26)") and "von Frau Beispiel empfohlen" in row["note"] and "https://example.org/job/1" in row["note"]
    role = root / "215 Blanco GmbH + Co KG" / "Head of Global E-Commerce (m-w-d)"
    for sub in ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf"):
        assert (role / sub).is_dir(), sub
    archived = role / "10 Bewerbung" / "blanco.md"
    assert archived.exists() and sha(archived) == digest and not src.exists()      # moved, content identical
    assert json.loads((system / "jd_cache.json").read_text(encoding="utf-8"))["215"].startswith("Wir suchen")   # orphan entry replaced
    assert top10.load(str(system / "top10.json"))["pinned"] == [215]
    assert "215\t215 Blanco GmbH + Co KG\t" in (system / "folders.tsv").read_text(encoding="utf-8")
    assert digest in json.loads((system / "intake_state.json").read_text(encoding="utf-8"))["files"]
    assert json.loads((system / "intake_report.json").read_text(encoding="utf-8"))["new"][0]["company"] == "Blanco GmbH + Co KG"


def test_lane_comes_from_the_existing_lane_rules(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "x.md", "Firma: Acme\nRolle: Head of Data & AI\n\nAnalytics platform leadership CDO CDAO.\n")
    run(root, system)
    assert rows_of(system)[-1]["lane"] == "Data/AI Arch"


def confirm(inbox, name):
    side = inbox / name
    side.write_text(side.read_text(encoding="utf-8").replace("Bestätigt: nein", "Bestätigt: ja"), encoding="utf-8")


def test_pdf_named_firma_rolle_gets_a_proposal_first_and_is_archived_after_confirmation_even_without_text(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "Blanco GmbH - Head of E-Commerce.pdf").write_bytes(b"%PDF-1.4 scanned image only")
    rep = run(root, system)
    assert rep["new"] == [] and rows_of(system) == [] and rep["unclear"][0]["sidecar"] == "Blanco GmbH - Head of E-Commerce.md"
    side = (inbox / "Blanco GmbH - Head of E-Commerce.md").read_text(encoding="utf-8")
    assert "Firma: Blanco GmbH" in side and "Rolle: Head of E-Commerce" in side                   # the name is only a proposal
    confirm(inbox, "Blanco GmbH - Head of E-Commerce.md")
    rep = run(root, system)
    assert rep["new"][0]["text_missing"] is True
    moved = root / "215 Blanco GmbH" / "Head of E-Commerce" / "10 Bewerbung" / "Blanco GmbH - Head of E-Commerce.pdf"
    assert moved.exists() and not (inbox / "Blanco GmbH - Head of E-Commerce.pdf").exists()
    assert "215" not in json.loads((system / "jd_cache.json").read_text(encoding="utf-8"))          # the stale orphan entry is gone


def test_pdf_text_is_cached_when_an_extractor_reads_it(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "Blanco - Head.pdf").write_bytes(b"%PDF fake")
    ex = lambda p: "Aufgaben: Plattform.\nProfil: Erfahrung mit Governance."     # noqa: E731
    run(root, system, extractor=ex)
    confirm(inbox, "Blanco - Head.md")
    rep = run(root, system, extractor=ex)
    assert rep["new"][0]["text_missing"] is False
    assert json.loads((system / "jd_cache.json").read_text(encoding="utf-8"))["215"].startswith("Aufgaben")


def test_pdf_with_sidecar_headers_moves_both_files(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "ausschreibung.pdf").write_bytes(b"%PDF fake")
    (inbox / "ausschreibung.md").write_text("Firma: Beispiel AG\nRolle: CIO\nNotiz: intern\n", encoding="utf-8")
    run(root, system)
    d = root / "215 Beispiel AG" / "CIO" / "10 Bewerbung"
    assert (d / "ausschreibung.pdf").exists() and (d / "ausschreibung.md").exists()
    assert not (inbox / "ausschreibung.pdf").exists() and not (inbox / "ausschreibung.md").exists()
    assert len([r for r in rows_of(system) if r["company"] == "Beispiel AG"]) == 1        # the sidecar is not a second posting


# ---- unclear files ------------------------------------------------------------------------------
def test_unclear_files_are_reported_and_never_moved_or_turned_into_rows(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "no_company.md", "Rolle: CIO\n\nText text.\n")
    drop(inbox, "empty_body.md", "Firma: X\nRolle: Y\n")
    (inbox / "Stellenanzeige.pdf").write_bytes(b"%PDF fake")
    (inbox / "cv.docx").write_bytes(b"PK fake")
    (inbox / "pointer.gdoc").write_text(json.dumps({"doc_id": "1abc"}), encoding="utf-8")
    before = rows_of(system)
    rep = run(root, system)
    reasons = {u["file"]: u["reason"] for u in rep["unclear"]}
    assert set(reasons) == {"no_company.md", "empty_body.md", "Stellenanzeige.pdf", "cv.docx", "pointer.gdoc"}
    assert "Firma" in reasons["no_company.md"] and "Text" in reasons["empty_body.md"] and "nicht unterstützt" in reasons["cv.docx"]
    assert "gdoc" in reasons["pointer.gdoc"] and rep["new"] == []
    assert rows_of(system) == before and sorted(os.listdir(inbox)) == sorted(list(reasons) + ["Stellenanzeige.md"])   # the PDF got a sidecar to fill in
    assert not [d for d in os.listdir(root) if d.startswith("215")]


def test_templates_hidden_files_and_subfolders_are_ignored(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "_VORLAGE.md", "Firma: Nope\nRolle: Nope\n\nx\n")
    drop(inbox, ".hidden.md", "Firma: Nope\nRolle: Nope\n\nx\n")
    (inbox / "sub").mkdir()
    drop(inbox / "sub", "deep.md")
    rep = run(root, system)
    assert rep["new"] == [] and rep["unclear"] == [] and (inbox / "sub" / "deep.md").exists()


def test_missing_inbox_is_a_clean_no_op(tmp_path):
    root, system, inbox = env(tmp_path)
    os.rmdir(inbox)
    rep = run(root, system)
    assert rep["new"] == [] and rep["unclear"] == []


# ---- exactly once, duplicates -------------------------------------------------------------------
def test_second_run_changes_nothing_and_the_same_file_again_is_left_alone(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "blanco.md")
    run(root, system)
    snapshot = (system / "pipeline.csv").read_bytes()
    rep = run(root, system)
    assert rep["new"] == [] and (system / "pipeline.csv").read_bytes() == snapshot
    drop(inbox, "blanco_again.md")                                               # identical content dropped again
    rep = run(root, system)
    assert rep["new"] == [] and [a["uid"] for a in rep["already"]] == [215] and (inbox / "blanco_again.md").exists()


def test_posting_for_an_existing_row_is_archived_there_and_creates_no_new_row(tmp_path):
    root, system, inbox = env(tmp_path, '215,Blanco GmbH,Head of Global E-Commerce (m/w/d),Executive,Applied,,,,,,,,,,,,,n,,\n')
    (root / "215 Blanco GmbH").mkdir()
    drop(inbox, "blanco2.md")
    rep = run(root, system)
    assert rep["new"] == [] and [e["uid"] for e in rep["existing"]] == [215]
    assert len(rows_of(system)) == 1
    hits = [str(p) for p in root.rglob("blanco2.md")]
    assert len(hits) == 1 and "215 Blanco GmbH" in hits[0] and "10 Bewerbung" in hits[0] and not (inbox / "blanco2.md").exists()
    assert top10.load(str(system / "top10.json"))["pinned"] == []               # an existing row is not silently pinned


# ---- names and csv ------------------------------------------------------------------------------
def test_folder_names_are_sanitised_and_cannot_escape_the_root(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "evil.md", 'Firma: ../../A/B: Corp?\nRolle: Head "of" <IT>|*\n\nText.\n')
    run(root, system)
    made = [p for p in root.rglob("evil.md")]
    assert len(made) == 1 and str(made[0]).startswith(str(root)) and ".." not in os.path.relpath(made[0], root).split(os.sep)
    for part in os.path.relpath(made[0], root).split(os.sep):
        assert not set('<>:"|?*\\') & set(part), part


def test_row_append_keeps_existing_bytes_header_order_quotes_and_adds_a_missing_newline(tmp_path):
    root, system, inbox = env(tmp_path)
    existing = HEADER + "133,Nordberatung,Manager,Data/AI Arch,Interviewing,,,,,,,,,,,,,n,,"        # no trailing newline
    (system / "pipeline.csv").write_text(existing, encoding="utf-8")
    drop(inbox, "q.md", 'Firma: Müller, Söhne & "Co"\nRolle: Leiter, IT\n\nText.\n')
    run(root, system)
    raw = (system / "pipeline.csv").read_bytes()
    assert raw.startswith(existing.encode("utf-8") + b"\n")
    row = rows_of(system)[-1]
    assert row["company"] == 'Müller, Söhne & "Co"' and row["role"] == "Leiter, IT" and len(row) == 20


def test_long_notes_are_cut_to_300_characters(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "n.md", "Firma: A\nRolle: B\nNotiz: " + "x" * 500 + "\n\nText.\n")
    run(root, system)
    assert len(rows_of(system)[-1]["note"]) <= 300


# ---- move safety --------------------------------------------------------------------------------
def test_a_failed_move_leaves_the_original_and_the_next_run_heals(tmp_path, monkeypatch):
    root, system, inbox = env(tmp_path)
    src = drop(inbox, "blanco.md")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(I, "move_unique", boom)
    rep = run(root, system)
    assert src.exists() and rep["failed"] and "disk full" in rep["failed"][0]["error"] and rep["new"] == []
    assert len(rows_of(system)) == 1 and top10.load(str(system / "top10.json"))["pinned"] == [215]      # records come first
    monkeypatch.undo()
    rep = run(root, system)                                                    # same company and role: finds its own row
    assert [e["uid"] for e in rep["existing"]] == [215] and len(rows_of(system)) == 1 and not src.exists()
    assert list(root.rglob("blanco.md")) and "215 Blanco GmbH + Co KG" in str(list(root.rglob("blanco.md"))[0])


def test_a_failure_writing_the_records_leaves_everything_untouched(tmp_path, monkeypatch):
    root, system, inbox = env(tmp_path)
    src = drop(inbox, "blanco.md")
    before = (system / "pipeline.csv").read_bytes()

    def boom(*a, **k):
        raise OSError("read-only file system")
    monkeypatch.setattr(I, "append_row", boom)
    rep = run(root, system)
    assert src.exists() and rep["failed"] and rep["new"] == [] and (system / "pipeline.csv").read_bytes() == before
    assert not [d for d in os.listdir(root) if d.startswith("215")] and not (system / "top10.json").exists()


def test_name_clash_gets_a_suffix_and_never_overwrites(tmp_path):
    src_dir = tmp_path / "src"
    dst = tmp_path / "dst"
    src_dir.mkdir()
    dst.mkdir()
    (dst / "posting.pdf").write_bytes(b"OLD CONTENT")
    a = src_dir / "posting.pdf"
    a.write_bytes(b"NEW CONTENT")
    out = I.move_unique(str(a), str(dst))
    assert os.path.basename(out) == "posting (2).pdf" and (dst / "posting.pdf").read_bytes() == b"OLD CONTENT"
    assert (dst / "posting (2).pdf").read_bytes() == b"NEW CONTENT" and not a.exists()
    b = src_dir / "posting.pdf"
    b.write_bytes(b"THIRD")
    assert os.path.basename(I.move_unique(str(b), str(dst))) == "posting (3).pdf"


def test_intake_and_top10_use_no_delete_calls_so_the_boundary_guard_stays_untouched():
    import ast
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("intake.py", "top10.py"):
        tree = ast.parse(open(os.path.join(here, name), encoding="utf-8").read())
        called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not called & {"remove", "rmtree", "rmdir", "unlink"}, (name, called & {"remove", "rmtree", "rmdir", "unlink"})


def test_one_bad_file_does_not_stop_the_others(tmp_path, monkeypatch):
    root, system, inbox = env(tmp_path)
    drop(inbox, "a_bad.md", "Firma: Bad\nRolle: Bad\n\nText.\n")
    drop(inbox, "b_good.md", "Firma: Good\nRolle: Role\n\nText.\n")
    real = I.move_unique

    def flaky(src, dst):
        if "a_bad" in src:
            raise OSError("nope")
        return real(src, dst)
    monkeypatch.setattr(I, "move_unique", flaky)
    rep = run(root, system)
    assert [n["company"] for n in rep["new"]] == ["Good"] and [f["file"] for f in rep["failed"]] == ["a_bad.md"]


def test_dry_run_writes_and_moves_nothing(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "blanco.md")
    snapshot = sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*") if p.is_file())
    rep = run(root, system, dry_run=True)
    assert [n["uid"] for n in rep["new"]] == [215] and rep["dry_run"] is True
    assert sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*") if p.is_file()) == snapshot
    assert not [d for d in os.listdir(root) if d.startswith("215")]


# ---- setup and CLI ------------------------------------------------------------------------------
def test_init_creates_the_inbox_and_template_once_and_keeps_an_edited_template(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    I.init(str(root))
    tpl = root / "_Eingang" / "_VORLAGE.md"
    assert tpl.exists() and "Firma:" in tpl.read_text(encoding="utf-8") and "Bestätigt: ja" in tpl.read_text(encoding="utf-8")
    tpl.write_text("my own", encoding="utf-8")
    I.init(str(root))
    assert tpl.read_text(encoding="utf-8") == "my own"


def test_inbox_folder_name_is_not_counted_as_an_employer_folder():
    assert not I.INBOX[0].isdigit()


def test_main_returns_1_when_the_pipeline_cannot_be_read(tmp_path):
    root, system, inbox = env(tmp_path)
    assert I.main(["--data", str(tmp_path / "none.csv"), "--root", str(root), "--system-dir", str(system)]) == 1


def test_non_utf8_text_is_read_leniently(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "latin.txt").write_bytes("Firma: Größe AG\nRolle: Leiter\n\nStraße Ünder".encode("latin-1"))
    rep = run(root, system)
    assert len(rep["new"]) == 1


# ---- final review, fix pass ---------------------------------------------------------------------
def test_role_matching_is_by_whole_words_prefers_exact_and_skips_closed_rows(tmp_path):
    rows = [{"uid": "50", "company": "Beispiel AG", "role": "Director Sales", "stage": "Closed"},
            {"uid": "51", "company": "Beispiel AG", "role": "Head of Data & AI", "stage": "Closed"},
            {"uid": "200", "company": "Beispiel AG", "role": "Head of Data", "stage": "Watchlist"},
            {"uid": "60", "company": "Andere GmbH", "role": "Senior Manager Data AI Technology naechste Runde", "stage": "Interviewing"}]
    assert I.find_existing(rows, "Beispiel AG", "CTO") is None                         # 'cto' is not inside 'director' as a word
    assert I.find_existing(rows, "Beispiel AG", "Director Sales") is None              # a closed row is not a match: a new posting is a new find
    assert I.find_existing(rows, "Beispiel AG", "Head of Data")["uid"] == "200"       # exact, active row wins over a closed longer one
    assert I.find_existing(rows, "Andere", "Manager Data AI Technology")["uid"] == "60"    # whole-word subset of two or more words still matches


def test_existing_row_in_a_duplicate_prefix_folder_pair_is_not_guessed(tmp_path):
    root, system, inbox = env(tmp_path, '167,Bohnenhaus Gruppe,Head of IT,Executive,Applied,,,,,,,,,,,,,n,,\n')
    (root / "167 Aaa wrong company").mkdir()
    (root / "167 Bohnenhaus Gruppe").mkdir()
    src = drop(inbox, "neumann.md", "Firma: Bohnenhaus Gruppe\nRolle: Head of IT\n\nText.\n")
    rep = run(root, system)
    assert src.exists() and rep["existing"] == [] and rep["failed"] and "Dublette" in rep["failed"][0]["error"]
    assert not list((root / "167 Aaa wrong company").rglob("*")) and not list((root / "167 Bohnenhaus Gruppe").rglob("*"))


def test_existing_row_never_archives_into_a_rejected_or_inactive_role_folder(tmp_path):
    root, system, inbox = env(tmp_path, '70,Beispiel AG,Head of Data,Executive,Applied,,,,,,,,,,,,,n,,\n')
    (root / "70 Beispiel AG" / "Head of Data (rejected)").mkdir(parents=True)
    drop(inbox, "p.md", "Firma: Beispiel AG\nRolle: Head of Data\n\nText.\n")
    rep = run(root, system)
    assert [e["uid"] for e in rep["existing"]] == [70]
    hits = [str(x) for x in root.rglob("p.md")]
    assert len(hits) == 1 and "(rejected)" not in hits[0] and hits[0].endswith(os.path.join("Head of Data", "10 Bewerbung", "p.md"))


def test_the_main_file_moves_before_its_sidecar_so_a_failed_move_keeps_the_headers(tmp_path, monkeypatch):
    root, system, inbox = env(tmp_path)
    (inbox / "post.pdf").write_bytes(b"%PDF fake")
    (inbox / "post.md").write_text("Firma: Beispiel AG\nRolle: CIO\n", encoding="utf-8")
    real = I.move_unique

    def fail_pdf(src, dst):
        if src.endswith("post.pdf"):
            raise OSError("busy")
        return real(src, dst)
    monkeypatch.setattr(I, "move_unique", fail_pdf)
    rep = run(root, system)
    assert rep["failed"] and (inbox / "post.pdf").exists() and (inbox / "post.md").exists()      # headers still beside the PDF
    monkeypatch.undo()
    rep = run(root, system)
    assert not (inbox / "post.pdf").exists() and not (inbox / "post.md").exists() and len(rows_of(system)) == 1


def test_a_failed_sidecar_move_after_the_main_file_is_a_warning_not_a_failure(tmp_path, monkeypatch):
    root, system, inbox = env(tmp_path)
    (inbox / "post.pdf").write_bytes(b"%PDF fake")
    (inbox / "post.md").write_text("Firma: Beispiel AG\nRolle: CIO\n", encoding="utf-8")
    real = I.move_unique

    def fail_side(src, dst):
        if src.endswith("post.md"):
            raise OSError("busy")
        return real(src, dst)
    monkeypatch.setattr(I, "move_unique", fail_side)
    rep = run(root, system)
    assert [n["uid"] for n in rep["new"]] == [215] and "Begleitdatei" in rep["new"][0]["warning"] and rep["failed"] == []
    assert not (inbox / "post.pdf").exists() and (inbox / "post.md").exists()


def test_a_half_done_find_is_completed_and_reported_as_healed(tmp_path, monkeypatch):
    root, system, inbox = env(tmp_path)
    src = drop(inbox, "blanco.md")

    def boom(*a, **k):
        raise OSError("sync hiccup")
    monkeypatch.setattr(I, "append_folder_line", boom)                              # fails after the row was appended
    rep = run(root, system)
    assert rep["failed"] and src.exists() and len(rows_of(system)) == 1
    monkeypatch.undo()
    rep = run(root, system)
    assert [h["uid"] for h in rep["healed"]] == [215] and rep["existing"] == [] and rep["new"] == []
    assert "215\t215 Blanco GmbH + Co KG" in (system / "folders.tsv").read_text(encoding="utf-8")
    assert top10.load(str(system / "top10.json"))["pinned"] == [215] and json.loads((system / "jd_cache.json").read_text(encoding="utf-8"))["215"].startswith("Wir suchen")
    role = root / "215 Blanco GmbH + Co KG" / "Head of Global E-Commerce (m-w-d)"
    assert all((role / s).is_dir() for s in ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf")) and not src.exists()


def test_decomposed_unicode_in_a_file_name_still_finds_the_existing_row(tmp_path):
    import unicodedata
    root, system, inbox = env(tmp_path, unicodedata.normalize("NFC", "300,Müller AG,CIO,Executive,Applied,,,,,,,,,,,,,n,,\n"))
    drop(inbox, "mueller.md", "Firma: " + unicodedata.normalize("NFD", "Müller AG") + "\nRolle: CIO\n\nText.\n")
    rep = run(root, system)
    assert [e["uid"] for e in rep["existing"]] == [300] and rep["new"] == [] and len(rows_of(system)) == 1


def test_control_characters_in_headers_are_unclear_and_never_reach_the_csv(tmp_path):
    root, system, inbox = env(tmp_path)
    before = (system / "pipeline.csv").read_bytes()
    drop(inbox, "nul.md", "Firma: Evil\x00 AG\nRolle: CIO\n\nText.\n")
    rep = run(root, system)
    assert [u["file"] for u in rep["unclear"]] == ["nul.md"] and "Steuerzeichen" in rep["unclear"][0]["reason"]
    assert (system / "pipeline.csv").read_bytes() == before


def test_a_corrupt_cache_or_state_file_is_backed_up_not_overwritten(tmp_path):
    root, system, inbox = env(tmp_path)
    (system / "jd_cache.json").write_text("{corrupt: of value", encoding="utf-8")
    drop(inbox, "blanco.md")
    run(root, system)
    backups = [f for f in os.listdir(system) if f.startswith("jd_cache.json.corrupt-")]
    assert len(backups) == 1 and (system / backups[0]).read_text(encoding="utf-8") == "{corrupt: of value"
    assert json.loads((system / "jd_cache.json").read_text(encoding="utf-8"))["215"].startswith("Wir suchen")


def test_a_temporarily_unreadable_cache_fails_the_file_and_keeps_it(tmp_path):
    root, system, inbox = env(tmp_path)
    cache = system / "jd_cache.json"
    cache.write_text("{}", encoding="utf-8")
    os.chmod(cache, 0o000)
    try:
        src = drop(inbox, "blanco.md")
        rep = run(root, system)
    finally:
        os.chmod(cache, 0o644)
    assert src.exists() and rep["failed"]


def test_runbook_describes_the_real_move_not_a_copy_and_rollback():
    text = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "RUNBOOK.md"), encoding="utf-8").read()
    step = text[text.index("## Schritt 3c"):text.index("## Schritt 3d")]
    assert "SHA-256" not in step and "zurückgenommen" not in step and "Kopie" not in step
    assert "umbenannt" in step and "nicht von Hand" in step
    assert "nach geprüfter Kopie" not in text


# ---- Eingang robustness (Stage 1.1) -------------------------------------------------------------
ABC1 = "Sr. Director, Business Intelligence and Analytics - Toronto, ON _ ABC1 Canada Careers"


def test_page_title_names_are_suspect_and_normal_names_are_not():
    for stem in (ABC1, "Head of IT - Blanco", "Blanco - Manager | Jobs", "Acme - Data Lead - Careers", "Acme - Stellenangebote Hamburg", "Foo - Bar_Baz"):
        assert I.looks_like_page_title(stem), stem
    for stem in ("Blanco GmbH - Head of E-Commerce", "Blanco – CIO", "Beispiel AG - Manager Data & AI", "Firma - Rolle"):
        assert not I.looks_like_page_title(stem), stem


def test_suggestions_are_read_from_a_page_title():
    assert I.suggest_from_title(ABC1) == {"company": "ABC1 Canada", "role": "Sr. Director, Business Intelligence and Analytics", "location": "Toronto, ON"}
    assert I.suggest_from_title("Head of IT - Blanco") == {"company": "Blanco", "role": "Head of IT"}
    assert I.suggest_from_title("Stellenanzeige") == {}


def test_a_page_title_pdf_gets_a_sidecar_with_suggestions_and_creates_no_row(tmp_path):
    root, system, inbox = env(tmp_path)
    pdf = inbox / (ABC1 + ".pdf")
    pdf.write_bytes(b"%PDF fake")
    before = rows_of(system)
    rep = run(root, system, extractor=lambda p: "Senior Director BI\nGS1 Canada\nToronto\n")
    assert rep["new"] == [] and rows_of(system) == before and pdf.exists()
    assert [u["file"] for u in rep["unclear"]] == [pdf.name] and rep["unclear"][0]["sidecar"] == ABC1 + ".md"
    side = (inbox / (ABC1 + ".md")).read_text(encoding="utf-8")
    assert "Firma: ABC1 Canada" in side and "Rolle: Sr. Director, Business Intelligence and Analytics" in side and "Ort: Toronto, ON" in side
    assert "Bestätigt: nein" in side and "Senior Director BI" in side                         # unconfirmed, with the start of the text as help


def test_an_unconfirmed_sidecar_stays_unclear_until_it_is_confirmed(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / (ABC1 + ".pdf")).write_bytes(b"%PDF fake")
    run(root, system)
    rep = run(root, system)
    assert rep["new"] == [] and "nicht bestätigt" in rep["unclear"][0]["reason"] and "sidecar" not in rep["unclear"][0]
    side = inbox / (ABC1 + ".md")
    side.write_text(side.read_text(encoding="utf-8").replace("Bestätigt: nein", "Bestätigt: ja").replace("Firma: ABC1 Canada", "Firma: ABC1 Canada Inc"), encoding="utf-8")
    rep = run(root, system)
    assert [n["company"] for n in rep["new"]] == ["ABC1 Canada Inc"] and rows_of(system)[-1]["location"] == "Toronto, ON"
    assert not (inbox / (ABC1 + ".pdf")).exists() and not side.exists()


def test_an_existing_sidecar_is_never_overwritten(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "post.pdf").write_bytes(b"%PDF fake")
    (inbox / "post.md").write_text("Notiz: nur eine Notiz\n", encoding="utf-8")
    rep = run(root, system)
    assert rep["unclear"] and "sidecar" not in rep["unclear"][0] and (inbox / "post.md").read_text(encoding="utf-8") == "Notiz: nur eine Notiz\n"


def test_dry_run_writes_no_sidecar(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / (ABC1 + ".pdf")).write_bytes(b"%PDF fake")
    run(root, system, dry_run=True)
    assert os.listdir(inbox) == [ABC1 + ".pdf"]


def test_recently_modified_files_wait_and_temp_files_are_named_for_what_they_are(tmp_path):
    root, system, inbox = env(tmp_path)
    fresh = drop(inbox, "fresh.md")
    (inbox / "big.pdf.crdownload").write_bytes(b"partial")
    (inbox / "~$lock.docx").write_bytes(b"lock")
    old = drop(inbox, "old.md", "Firma: Alt AG\nRolle: CIO\n\nText.\n")
    os.utime(old, (1, 1))
    rep = I.run(str(root), str(system), TODAY, extractor=lambda p: None, min_age=60)
    waiting = {w["file"]: w["reason"] for w in rep["waiting"]}
    assert set(waiting) == {"fresh.md", "big.pdf.crdownload"} and "Download" in waiting["big.pdf.crdownload"] and fresh.exists()
    assert [n["company"] for n in rep["new"]] == ["Alt AG"] and (inbox / "~$lock.docx").exists()      # lock files ignored, not reported


def test_empty_files_and_symlinks_are_unclear(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "leer.pdf").write_bytes(b"")
    real = tmp_path / "elsewhere.md"
    real.write_text("Firma: X\nRolle: Y\n\nText.\n", encoding="utf-8")
    os.symlink(real, inbox / "link.md")
    rep = run(root, system)
    reasons = {u["file"]: u["reason"] for u in rep["unclear"]}
    assert "leer" in reasons["leer.pdf"] and "Verknüpfung" in reasons["link.md"] and rep["new"] == []


def test_invisible_characters_and_no_break_spaces_are_cleaned(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "z.md", "Firma: Bei​spiel AG﻿\nRolle: Head‍ of IT\n\nText.\n")
    run(root, system)
    row = rows_of(system)[-1]
    assert row["company"] == "Beispiel AG" and row["role"] == "Head of IT"
    assert [d for d in os.listdir(root) if d.startswith("215")] == ["215 Beispiel AG"]


def test_long_file_names_are_shortened_for_the_archive_and_keep_the_extension(tmp_path):
    src_dir, dst = tmp_path / "s", tmp_path / "d"
    src_dir.mkdir()
    dst.mkdir()
    # 245 bytes: legal on Linux (255-byte limit) and macOS, but over NAME_MAX_BYTES, so it must be shortened
    a, b = src_dir / (("Ä" * 120) + "A.pdf"), src_dir / (("Ä" * 120) + "B.pdf")
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    out_a, out_b = I.move_unique(str(a), str(dst)), I.move_unique(str(b), str(dst))
    for out in (out_a, out_b):
        assert len(os.fsencode(os.path.basename(out))) <= 200 and out.endswith(".pdf")
    assert out_a != out_b and len(os.listdir(dst)) == 2


def test_the_sidecar_belongs_to_the_pdf_when_html_and_pdf_share_a_stem(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "x.pdf").write_bytes(b"%PDF fake")
    (inbox / "x.html").write_text("<html><body>Text</body></html>", encoding="utf-8")
    (inbox / "x.md").write_text("Firma: Beispiel AG\nRolle: CIO\n", encoding="utf-8")
    rep = run(root, system)
    assert [n["file"] for n in rep["new"]] == ["x.pdf"] and [u["file"] for u in rep["unclear"]] == ["x.html"]


def test_main_prints_the_refresh_hint_and_render_runs_the_renderer(tmp_path, monkeypatch, capsys):
    root, system, inbox = env(tmp_path)
    drop(inbox, "blanco.md")
    calls = []

    class Done:
        returncode = 0
    monkeypatch.setattr(I.subprocess, "run", lambda cmd, **k: calls.append(cmd) or Done())
    assert I.main(["--root", str(root), "--system-dir", str(system), "--today", TODAY, "--min-age", "0"]) == 0
    assert "--render" in capsys.readouterr().out and calls == [] and rows_of(system)[-1]["company"] == "Blanco GmbH + Co KG"     # a hint, nothing run
    drop(inbox, "acme.md", "Firma: Acme\nRolle: CTO\n\nText.\n")
    assert I.main(["--root", str(root), "--system-dir", str(system), "--today", TODAY, "--min-age", "0", "--render"]) == 0
    assert rows_of(system)[-1]["company"] == "Acme"                                          # the file was really processed
    cmd = calls[-1]
    assert cmd[1].endswith("render.py") and "--data" in cmd and str(system / "pipeline.csv") in cmd and cmd[cmd.index("--out") + 1] == str(root)


def test_runbook_mentions_the_sidecar_confirmation_and_the_render_option():
    text = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "RUNBOOK.md"), encoding="utf-8").read()
    step = text[text.index("## Schritt 3c"):text.index("## Schritt 3d")]
    assert "Bestätigt" in step and "--render" in step and "wartet" in step


# ---- final review of Stage 1.1, fix pass ---------------------------------------------------------
def test_an_unconfirmed_sidecar_never_becomes_a_row_when_its_pdf_is_renamed_or_moved_away(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / (ABC1 + ".pdf")).write_bytes(b"%PDF fake")
    run(root, system)
    os.rename(inbox / (ABC1 + ".pdf"), inbox / "ABC1 Canada - Senior Director BI.pdf")       # the renamed PDF
    rep = run(root, system)
    assert rep["new"] == [] and rows_of(system) == []                                     # the orphan sidecar alone is not a posting
    assert {u["file"] for u in rep["unclear"]} >= {ABC1 + ".md", "ABC1 Canada - Senior Director BI.pdf"}
    os.rename(inbox / "ABC1 Canada - Senior Director BI.pdf", tmp_path / "away.pdf")       # the PDF taken out of the inbox
    rep = run(root, system)
    assert rep["new"] == [] and rows_of(system) == []
    assert sorted(u["file"] for u in rep["unclear"]) == sorted([ABC1 + ".md", "ABC1 Canada - Senior Director BI.md"])      # two unconfirmed sidecars, no row


def test_sidecar_and_pdf_pair_up_across_case_and_unicode_forms(tmp_path):
    import unicodedata
    root, system, inbox = env(tmp_path)
    nfd = unicodedata.normalize("NFD", "Müller Group - Head of Data")
    (inbox / (nfd + ".PDF")).write_bytes(b"%PDF fake")
    (inbox / (unicodedata.normalize("NFC", "Müller Group - Head of Data") + ".md")).write_text(
        "Firma: Müller Group\nRolle: Head of Data\nBestätigt: nein\n", encoding="utf-8")
    rep = run(root, system)
    assert rep["new"] == [] and rows_of(system) == [] and len(rep["unclear"]) == 1        # one pair, unconfirmed: nothing is created


def test_only_an_explicit_yes_confirms_and_everything_else_stays_unconfirmed(tmp_path):
    for value, ok in (("ja", True), ("Ja", True), (" JA ", True), ("yes", True), ("true", True), ("j", True),
                      ("nein", False), ("nein.", False), ("", False), ("noch nicht", False), ("offen", False), ("nein​", False)):
        root, system, inbox = env(tmp_path / ("c%d" % abs(hash((value, ok)))))
        (inbox / "post.pdf").write_bytes(b"%PDF fake")
        (inbox / "post.md").write_text("Firma: Beispiel AG\nRolle: CIO\nBestätigt: %s\n" % value, encoding="utf-8")
        rep = run(root, system)
        assert bool(rep["new"]) is ok, (value, rep["unclear"])


def test_a_deleted_confirmation_line_in_our_own_sidecar_is_not_a_confirmation(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / (ABC1 + ".pdf")).write_bytes(b"%PDF fake")
    run(root, system)
    side = inbox / (ABC1 + ".md")
    side.write_text("\n".join(l for l in side.read_text(encoding="utf-8").splitlines() if not l.startswith("Bestätigt")) + "\n", encoding="utf-8")
    assert run(root, system)["new"] == [] and rows_of(system) == []


def test_the_confirmation_is_found_after_a_multi_line_note_and_a_blank_line(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "post.pdf").write_bytes(b"%PDF fake")
    (inbox / "post.md").write_text("Firma: Beispiel AG\nRolle: CIO\nNotiz: erste Zeile\nzweite Zeile\n\nBestätigt: nein\n", encoding="utf-8")
    assert run(root, system)["new"] == []


def test_a_standalone_markdown_posting_with_an_unconfirmed_marker_is_not_processed(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "orphan.md", "Firma: Evil AG\nRolle: CIO\nBestätigt: nein\n\nText.\n")
    rep = run(root, system)
    assert rep["new"] == [] and rows_of(system) == [] and "bestätigt" in rep["unclear"][0]["reason"].lower()


def test_proposals_put_company_and_role_the_right_way_round(tmp_path):
    assert I.propose("Lead Consulting GmbH - Data Architect") == {"company": "Lead Consulting GmbH", "role": "Data Architect"}
    assert I.propose("Data Scientist - Beispiel AG") == {"company": "Beispiel AG", "role": "Data Scientist"}
    assert I.propose("Blanco - Head of E-Commerce") == {"company": "Blanco", "role": "Head of E-Commerce"}
    assert I.propose(ABC1) == {"company": "ABC1 Canada", "role": "Sr. Director, Business Intelligence and Analytics", "location": "Toronto, ON"}
    assert I.propose("Stellenanzeige") == {}


def test_a_file_name_alone_never_creates_a_row(tmp_path):
    root, system, inbox = env(tmp_path)
    for name in ("Blanco GmbH - Head of E-Commerce.pdf", "Data Scientist - Beispiel AG.pdf", "Lead Consulting GmbH - Data Architect.pdf"):
        (inbox / name).write_bytes(b"%PDF fake")
    drop(inbox, "Foo - Bar.md", "Nur Text ohne Kopfzeilen.\n")
    rep = run(root, system)
    assert rep["new"] == [] and rows_of(system) == [] and len(rep["unclear"]) == 4


def test_html_with_a_pdf_of_the_same_stem_gets_no_sidecar_of_its_own(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "x.html").write_text("<html><body>Text</body></html>", encoding="utf-8")
    (inbox / "x.pdf").write_bytes(b"%PDF fake")
    run(root, system)
    assert sorted(os.listdir(inbox)) == ["x.html", "x.md", "x.pdf"]                       # exactly one sidecar, made for the PDF
    assert "Bestätigt: nein" in (inbox / "x.md").read_text(encoding="utf-8")


def test_a_future_modification_time_does_not_keep_a_file_waiting_forever(tmp_path):
    root, system, inbox = env(tmp_path)
    p = drop(inbox, "future.md", "Firma: Zukunft AG\nRolle: CIO\n\nText.\n")
    os.utime(p, (4102444800, 4102444800))                                                  # year 2100
    rep = I.run(str(root), str(system), TODAY, extractor=lambda q: None, min_age=60)
    assert rep["waiting"] == [] and [n["company"] for n in rep["new"]] == ["Zukunft AG"]


def test_render_option_always_renders_reports_failures_and_refuses_dry_run(tmp_path, monkeypatch, capsys):
    root, system, inbox = env(tmp_path)
    calls = []

    class Done:
        def __init__(self, code):
            self.returncode, self.stderr, self.stdout = code, "boom on stderr", ""
    codes = [0]
    monkeypatch.setattr(I.subprocess, "run", lambda cmd, **k: calls.append(cmd) or Done(codes[0]))
    base = ["--root", str(root), "--system-dir", str(system), "--today", TODAY, "--min-age", "0"]
    assert I.main(base + ["--render"]) == 0 and len(calls) == 1                            # nothing new in the inbox: it still renders
    codes[0] = 3
    assert I.main(base + ["--render"]) == 2 and "boom on stderr" in capsys.readouterr().out  # a render failure is visible and distinct
    assert I.main(base + ["--render", "--dry-run"]) == 1 and len(calls) == 2               # not combinable, nothing run


def test_the_hint_appears_only_when_something_changed_and_the_summary_counts_waiting(tmp_path, monkeypatch, capsys):
    root, system, inbox = env(tmp_path)
    base = ["--root", str(root), "--system-dir", str(system), "--today", TODAY, "--min-age", "0"]
    assert I.main(base) == 0
    assert "aktualisieren" not in capsys.readouterr().out
    drop(inbox, "blanco.md")
    assert I.main(base) == 0
    out = capsys.readouterr().out
    assert "1 new" in out and "aktualisieren" in out and rows_of(system)[-1]["company"] == "Blanco GmbH + Co KG"
    (inbox / "x.pdf.crdownload").write_bytes(b"p")
    assert I.main(base) == 0 and "1 waiting" in capsys.readouterr().out


def test_runbook_takes_fit_and_brief_candidates_from_the_data_not_from_the_report():
    text = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "RUNBOOK.md"), encoding="utf-8").read()
    step = text[text.index("## Schritt 3d"):text.index("## Schritt 4 — Score")]
    assert "Eigener Fund" in step and "ts_fit_score" in step and "intake_report.json" not in step


# ---- --confirm and the file to open (Stage 1.2) ---------------------------------------------------
def proposal(tmp_path, stem=ABC1, text=None):
    root, system, inbox = env(tmp_path)
    (inbox / (stem + ".pdf")).write_bytes(b"%PDF fake")
    run(root, system, extractor=lambda p: text or "")
    return root, system, inbox


def cli(root, system, *extra):
    return I.main(["--root", str(root), "--system-dir", str(system), "--today", TODAY, "--min-age", "0", *extra])


def test_unclear_entries_name_the_file_to_open(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "a.pdf").write_bytes(b"%PDF fake")                                       # no sidecar yet: one is written, that is the file to open
    (inbox / "b.pdf").write_bytes(b"%PDF fake 2")
    (inbox / "b.md").write_text("Firma: B AG\nRolle: CIO\nBestätigt: nein\n", encoding="utf-8")   # unconfirmed sidecar
    drop(inbox, "orphan.md", "Firma: O AG\nRolle: CIO\nBestätigt: nein\n\nText.\n")
    drop(inbox, "nohead.md", "Nur Text.\n")
    (inbox / "cv.docx").write_bytes(b"PK")
    rep = run(root, system)
    edit = {u["file"]: u.get("edit") for u in rep["unclear"]}
    assert edit == {"a.pdf": "a.md", "b.pdf": "b.md", "orphan.md": "orphan.md", "nohead.md": "nohead.md", "cv.docx": None}


def test_confirm_shows_the_proposal_and_writes_nothing_without_yes_when_not_interactive(tmp_path, capsys, monkeypatch):
    root, system, inbox = proposal(tmp_path)
    side = inbox / (ABC1 + ".md")
    before = side.read_bytes()
    monkeypatch.setattr(I, "_interactive", lambda: False)
    assert cli(root, system, "--confirm", "ABC1") == 3
    out = capsys.readouterr().out
    assert "ABC1 Canada" in out and "--yes" in out and side.read_bytes() == before and rows_of(system) == []


def test_confirm_asks_in_a_terminal_and_only_a_yes_confirms(tmp_path, capsys, monkeypatch):
    root, system, inbox = proposal(tmp_path)
    side = inbox / (ABC1 + ".md")
    before = side.read_bytes()
    monkeypatch.setattr(I, "_interactive", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "n")
    assert cli(root, system, "--confirm", "ABC1") == 3 and side.read_bytes() == before and rows_of(system) == []
    monkeypatch.setattr(builtins, "input", lambda prompt="": "j")
    assert cli(root, system, "--confirm", "ABC1") == 0 and [r["company"] for r in rows_of(system)] == ["ABC1 Canada"]


def test_confirm_with_yes_sets_ja_shows_what_was_confirmed_and_creates_the_find(tmp_path, capsys):
    root, system, inbox = proposal(tmp_path)
    assert cli(root, system, "--confirm", "ABC1", "--yes") == 0                       # a unique fragment is enough
    out = capsys.readouterr().out
    assert "ABC1 Canada" in out and "Sr. Director" in out and "Toronto, ON" in out and "bestätigt" in out
    assert [r["company"] for r in rows_of(system)] == ["ABC1 Canada"] and not (inbox / (ABC1 + ".pdf")).exists()
    assert not [f for f in os.listdir(inbox) if f.startswith(".") and f.endswith(".tmp")]


def test_confirm_finds_the_sidecar_by_its_name_the_pdf_name_or_case_and_unicode_variants(tmp_path):
    import unicodedata
    for i, query in enumerate((ABC1 + ".md", ABC1 + ".pdf", ABC1, ABC1.upper(), unicodedata.normalize("NFD", "Müller AG - Head of Data"))):
        stem = "Müller AG - Head of Data" if i == 4 else ABC1
        root, system, inbox = proposal(tmp_path / ("q%d" % i), stem=unicodedata.normalize("NFC", stem))
        assert cli(root, system, "--confirm", query, "--yes") == 0 and len(rows_of(system)) == 1, query


def test_fragments_need_three_characters_and_a_word_start(tmp_path, capsys):
    root, system, inbox = env(tmp_path)
    (inbox / "Alpha Data - Head of Data.pdf").write_bytes(b"%PDF a")
    run(root, system)
    for bad in ("a", "ha", "ata", "lpha"):
        assert cli(root, system, "--confirm", bad, "--yes") == 1, bad                 # too short, or inside a word
    assert rows_of(system) == []
    assert cli(root, system, "--confirm", "dat", "--yes") == 0 and len(rows_of(system)) == 1     # 'Dat' starts the word 'Data'


def test_confirm_refuses_ambiguous_unknown_and_incomplete_proposals(tmp_path, capsys):
    root, system, inbox = env(tmp_path)
    for stem in ("Alpha Data - Head of Data", "Alpha Cloud - Head of Cloud"):
        (inbox / (stem + ".pdf")).write_bytes(b"%PDF " + stem.encode())
    run(root, system)
    assert cli(root, system, "--confirm", "Alpha", "--yes") == 1 and "Alpha Data" in capsys.readouterr().err       # ambiguous: candidates listed
    assert cli(root, system, "--confirm", "Zzzz", "--yes") == 1
    side = inbox / "Alpha Data - Head of Data.md"
    side.write_text(side.read_text(encoding="utf-8").replace("Firma: Alpha Data", "Firma:"), encoding="utf-8")
    assert cli(root, system, "--confirm", "Alpha Data", "--yes") == 1 and "Firma" in capsys.readouterr().err        # incomplete: never confirmed
    assert rows_of(system) == [] and "Bestätigt: nein" in side.read_text(encoding="utf-8")


def test_confirm_adds_a_missing_confirmation_line_and_reports_an_already_confirmed_one(tmp_path, capsys):
    root, system, inbox = proposal(tmp_path)
    side = inbox / (ABC1 + ".md")
    side.write_text("\n".join(l for l in side.read_text(encoding="utf-8").splitlines() if not l.startswith("Bestätigt")) + "\n", encoding="utf-8")
    assert cli(root, system, "--confirm", "ABC1", "--yes") == 0 and len(rows_of(system)) == 1
    root2, system2, inbox2 = proposal(tmp_path / "again")
    (inbox2 / (ABC1 + ".md")).write_text((inbox2 / (ABC1 + ".md")).read_text(encoding="utf-8").replace("nein", "ja"), encoding="utf-8")
    capsys.readouterr()
    assert cli(root2, system2, "--confirm", "ABC1", "--yes") == 0 and "bereits bestätigt" in capsys.readouterr().out


def test_confirm_never_edits_a_file_you_wrote_yourself_and_dry_run_edits_nothing(tmp_path, capsys):
    root, system, inbox = env(tmp_path)
    mine = drop(inbox, "meins.md", "Firma: Meine AG\nRolle: CIO\n\nText mit Bestätigt: nein im Text.\n")
    before = mine.read_text(encoding="utf-8")
    assert cli(root, system, "--confirm", "meins", "--yes") == 1 and mine.read_text(encoding="utf-8") == before
    root2, system2, inbox2 = proposal(tmp_path / "dry")
    side = inbox2 / (ABC1 + ".md")
    text = side.read_text(encoding="utf-8")
    assert cli(root2, system2, "--confirm", "ABC1", "--dry-run") == 0 and side.read_text(encoding="utf-8") == text and rows_of(system2) == []
    assert "Vorschlag: " in capsys.readouterr().out


def test_a_confirmation_line_far_down_in_the_posting_text_is_neither_matched_nor_edited(tmp_path):
    root, system, inbox = env(tmp_path)
    body = "\n".join("Zeile %d" % n for n in range(80)) + "\nConfirmed: remote allowed\nBestätigt: nein (vom Recruiter)\n"
    mine = drop(inbox, "long.md", "Firma: Lang AG\nRolle: CIO\n\n" + body)
    assert cli(root, system, "--confirm", "long", "--yes") == 1 and "remote allowed" in mine.read_text(encoding="utf-8")


def test_confirm_keeps_the_bytes_and_line_endings_and_only_changes_the_header_line(tmp_path):
    root, system, inbox = proposal(tmp_path)
    side = inbox / (ABC1 + ".md")
    raw = side.read_bytes().replace(b"\n", b"\r\n") + b"".join(b"Zeile %d\r\n" % n for n in range(70)) + b"Confirmed: remote allowed\r\n"    # far below line 60
    side.write_bytes(raw)
    assert cli(root, system, "--confirm", "ABC1", "--yes") == 0
    assert len(rows_of(system)) == 1                                                       # confirmed and processed
    moved = [str(p) for p in root.rglob(ABC1 + ".md")]
    assert len(moved) == 1
    data = open(moved[0], "rb").read()
    assert data == raw.replace(b"Best\xc3\xa4tigt: nein", b"Best\xc3\xa4tigt: ja")          # nothing else changed, CRLF intact


def test_confirm_refuses_files_that_are_not_utf8_and_leaves_them_untouched(tmp_path):
    root, system, inbox = env(tmp_path)
    side = inbox / "alt.md"
    raw = "Firma: Müller AG\nRolle: Leiter für Größe\nBestätigt: nein\n\n# Bitte prüfen: Firma\n".encode("latin-1")
    side.write_bytes(raw)
    (inbox / "alt.pdf").write_bytes(b"%PDF fake")
    assert cli(root, system, "--confirm", "alt", "--yes") == 1 and side.read_bytes() == raw


def test_confirm_refuses_symlinks_and_read_only_files(tmp_path):
    root, system, inbox = proposal(tmp_path)
    side = inbox / (ABC1 + ".md")
    before = side.read_bytes()
    os.chmod(side, 0o444)
    try:
        assert cli(root, system, "--confirm", "ABC1", "--yes") == 1 and side.read_bytes() == before
    finally:
        os.chmod(side, 0o644)
    root2, system2, inbox2 = proposal(tmp_path / "sym")
    real = tmp_path / "real.md"
    os.rename(inbox2 / (ABC1 + ".md"), real)
    os.symlink(real, inbox2 / (ABC1 + ".md"))
    assert cli(root2, system2, "--confirm", "ABC1", "--yes") == 1 and os.path.islink(inbox2 / (ABC1 + ".md"))


def test_confirm_writes_nothing_when_the_edit_could_not_be_verified(tmp_path, monkeypatch):
    root, system, inbox = proposal(tmp_path)
    side = inbox / (ABC1 + ".md")
    before = side.read_bytes()
    monkeypatch.setattr(I, "is_confirmed", lambda text: False)                            # the edited text would not count as confirmed
    assert cli(root, system, "--confirm", "ABC1", "--yes") == 1 and side.read_bytes() == before


def test_confirm_option_combinations_are_rejected_or_previewed_sensibly(tmp_path, capsys):
    root, system, inbox = proposal(tmp_path)
    assert cli(root, system, "--confirm", "", "--yes") == 1
    assert cli(root, system, "--confirm", "ABC1", "--init", "--yes") == 1
    assert rows_of(system) == []


def test_a_confirmed_standalone_markdown_is_processed_at_once_despite_the_default_min_age(tmp_path):
    root, system, inbox = env(tmp_path)
    drop(inbox, "meins.md", "Firma: Meine AG\nRolle: CIO\nBestätigt: nein\n\n# Bitte prüfen: Firma\nText der Ausschreibung.\n")
    assert I.main(["--root", str(root), "--system-dir", str(system), "--today", TODAY, "--confirm", "meins", "--yes"]) == 0     # default min-age 20 s
    assert [r["company"] for r in rows_of(system)] == ["Meine AG"]


def test_the_confirmation_line_must_stand_on_one_line(tmp_path):
    assert not I.is_confirmed("Firma: X\nRolle: Y\nBestätigt:\nja\n")                       # a value on the next line does not count
    assert I.is_confirmed("Firma: X\r\nRolle: Y\r\nBestätigt: ja\r\n")


def test_template_and_runbook_teach_the_confirm_command_and_its_review_step():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert "--confirm" in I.TEMPLATE and "j/N" in open(os.path.join(here, "intake.py"), encoding="utf-8").read()
    text = open(os.path.join(here, "RUNBOOK.md"), encoding="utf-8").read()
    step = text[text.index("## Schritt 3c"):text.index("## Schritt 3d")]
    assert "--confirm" in step and "--yes" in step


# ---- proposals from the posting text and safe automatic confirmation (e2e fix) ---------------------------------------
CONTOSO = ("9/25/26, 11:50 PM        AI Governance Officer im Chief Data Office (m/w/d) in Musterstadt | Operations at Contoso\n"
           "AI Governance Officer im Chief Data Office (m/w/d)\nBerufserfahren   Musterstadt   Operations   Contoso Deutschland   Contoso Versicherungs-AG\n"
           "Jetzt bewerben\nBeschreibung\nSie gestalten die AI-Governance der Contoso.\n")
UNI = ("KI-Anwendungsmanager*in\nKennziffer 22026TRZ\nEinrichtung Rechenzentrum\nWertigkeit EG 13 TV-L\nDie Beispiel Universität Nordstadt sucht ab sofort ...\nBeispiel Universität Nordstadt, Am Turm 1, 20095 Hamburg\n")
HOF = ("9/25/26, 11:53 PM        Teamleitung (m/w/d) | Datenarchitektur IT\nWir, die Musterhof GmbH, ist die zentrale Immobiliengesellschaft. Musterhof GmbH betreut Immobilien.\n"
       "Wir suchen für unseren Bereich zum nächstmöglichen Zeitpunkt eine/n\nTeamleitung (m/w/d) Datenarchitektur IT\n")


def test_file_name_characters_are_restored_and_titles_are_split_into_role_and_company():
    pt = lambda stem: {k: v for k, v in I.parse_title(stem).items() if k != "shape"}
    assert I.restore_chars("Teamleitung (m_w_d)") == "Teamleitung (m/w/d)" and I.restore_chars("KI-Anwendungsmanager_in") == "KI-Anwendungsmanager*in"
    assert pt("AI Governance Officer at Contoso") == {"role": "AI Governance Officer", "company": "Contoso"}
    assert pt("KI-Anwendungsmanager_in _ Beispiel Universität Nordstadt") == {"role": "KI-Anwendungsmanager*in", "company": "Beispiel Universität Nordstadt"}
    assert pt("Teamleitung (m_w_d) _ Datenarchitektur IT - Musterhof GmbH") == {"role": "Teamleitung (m/w/d) Datenarchitektur IT", "company": "Musterhof GmbH"}
    assert pt("Head of Data - Blanco GmbH") == {"role": "Head of Data", "company": "Blanco GmbH"}
    assert pt("Stellenanzeige") == {} and pt("Head of Data") == {}


def test_proposals_are_filled_from_the_text_and_marked_sure_only_when_company_and_role_are_in_the_text():
    a = I.derive_proposal("AI Governance Officer at Contoso", CONTOSO)
    assert (a["company"], a["role"], a["auto"]) == ("Contoso", "AI Governance Officer im Chief Data Office (m/w/d)", True)
    b = I.derive_proposal("KI-Anwendungsmanager_in _ Beispiel Universität Nordstadt", UNI)
    assert (b["company"], b["role"], b["auto"]) == ("Beispiel Universität Nordstadt", "KI-Anwendungsmanager*in", True)
    c = I.derive_proposal("Teamleitung (m_w_d) _ Datenarchitektur IT - Musterhof GmbH", HOF)
    assert (c["company"], c["role"], c["auto"]) == ("Musterhof GmbH", "Teamleitung (m/w/d) Datenarchitektur IT", True)
    assert I.derive_proposal("Head of Data - Blanco GmbH", "Head of Data\nWir suchen Verstärkung.")["auto"] is False            # company not in the text
    assert I.derive_proposal("Head of Data - Blanco GmbH", "Blanco GmbH sucht Verstärkung für das Team.")["auto"] is False      # role not in the text
    assert I.derive_proposal("Head of Data - Manager", "Head of Data Manager")["auto"] is False                                # 'company' looks like a job title
    assert I.derive_proposal("Senior Manager _ Karriere bei Blanco", "Senior Manager Blanco")["auto"] is False                # job-site words never make a company
    assert I.derive_proposal("Stellenanzeige", "text")["auto"] is False and I.derive_proposal("Stellenanzeige", "text")["company"] == ""


def test_a_swapped_title_is_never_confirmed_automatically():
    swapped = I.derive_proposal("Blanco GmbH - Head of Data", "Blanco GmbH sucht Head of Data. Blanco GmbH bietet mehr.")
    assert swapped["company"] == "Blanco GmbH" and swapped["role"] == "Head of Data" and swapped["auto"] is True         # correct order is fine
    odd = I.derive_proposal("Head of Data GmbH - Blanco", "Blanco Head of Data GmbH")
    assert odd["auto"] is False                                                                                       # a role with a legal suffix next to a plain company: unsure


def test_a_sure_pdf_becomes_a_row_at_once_with_an_automatic_note_and_a_confirmed_sidecar(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "AI Governance Officer at Contoso.pdf").write_bytes(b"%PDF contoso")
    (inbox / "Unklar.pdf").write_bytes(b"%PDF other")
    texts = {"AI Governance Officer at Contoso.pdf": CONTOSO, "Unklar.pdf": "Irgendein Text ohne Firma und Rolle."}
    rep = run(root, system, extractor=lambda p: texts.get(os.path.basename(p)))
    assert [(e["file"], e.get("auto")) for e in rep["new"]] == [("AI Governance Officer at Contoso.pdf", True)]
    row = rows_of(system)[-1]
    assert row["company"] == "Contoso" and row["role"] == "AI Governance Officer im Chief Data Office (m/w/d)" and "automatisch" in row["note"].lower()
    archived = [str(p) for p in root.rglob("*Contoso*.md")]
    assert len(archived) == 1 and "Bestätigt: ja" in open(archived[0], encoding="utf-8").read() and "Automatisch geprüft" in open(archived[0], encoding="utf-8").read()
    assert [e["file"] for e in rep["unclear"]] == ["Unklar.pdf"] and (inbox / "Unklar.md").exists() and "Bestätigt: nein" in (inbox / "Unklar.md").read_text(encoding="utf-8")
    again = run(root, system, extractor=lambda p: texts.get(os.path.basename(p)))
    assert not again["new"] and len(rows_of(system)) == 1


def test_an_unsure_pdf_still_waits_for_you_but_the_proposal_is_filled_from_the_text(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "Teamleitung (m_w_d) _ Datenarchitektur IT - Musterhof GmbH.pdf").write_bytes(b"%PDF hof")
    rep = run(root, system, extractor=lambda p: "Teamleitung (m/w/d) Datenarchitektur IT\nKein Firmenname im Text.")
    assert rep["new"] == [] and len(rep["unclear"]) == 1
    side = (inbox / "Teamleitung (m_w_d) _ Datenarchitektur IT - Musterhof GmbH.md").read_text(encoding="utf-8")
    assert "Firma: Musterhof GmbH" in side and "Rolle: Teamleitung (m/w/d) Datenarchitektur IT" in side and "Bestätigt: nein" in side and "Automatisch" not in side


# ---- review of the automatic filing: it must prove more, and never guess ---------------------------------------------------
GENERIC = "Wir suchen Verstärkung im Team. Bewerbung bei {c} gesendet. {c} ist ein tolles Unternehmen. Aufgaben: {r} im Bereich Daten und Analytics. www.{c}.example/jobs\n{r}\n"


def auto(stem, company_in_text=None, role_in_text=None):
    c = company_in_text or "Testfirma"
    r = role_in_text or "Head of Data"
    return I.derive_proposal(stem, GENERIC.format(c=c, r=r))["auto"]


def test_locations_agencies_people_and_generic_words_are_never_a_company():
    for stem, c in (("Head of Data - Berlin", "Berlin"), ("Manager _ Hamburg", "Hamburg"), ("Head of Data - Remote", "Remote"), ("Data Engineer at Remote", "Remote"),
                    ("Head of Data - Personalhaus", "Personalhaus"), ("Data Engineer at Randstad", "Randstad"), ("Head of Data - Max Mustermann", "Max Mustermann"),
                    ("Head of Data - Group IT", "Group IT"), ("Head of Data _ IT", "IT"), ("Senior Manager - Data", "Data"), ("Head of Data - Bank", "Bank"),
                    ("Head of Data - Technische Universität", "Technische Universität"), ("Data Engineer - Stepstone.de", "stepstone.de")):
        assert auto(stem, c) is False, stem


def test_titles_with_more_than_two_parts_or_a_place_are_not_filed_automatically():
    for stem in ("Head of Data | Contoso | Berlin", "Head of Data - Hamburg - Contoso", "Data Governance Lead - Hamburg Port Authority - Contoso", "Berlin - Head of Data",
                 "Hamburg - Senior Data Engineer", "Head of Data at Contoso - Berlin"):
        assert auto(stem, "Contoso") is False, stem


def test_a_company_that_is_named_once_or_only_in_a_url_or_boilerplate_is_not_proven():
    assert I.derive_proposal("Head of Data at Globex", "Head of Data\nBewerbung bei Globex gesendet.\nAufgaben: Daten.")["auto"] is False
    assert I.derive_proposal("Lead Architect at Acme", "acme.example/jobs leadership architecture Lead Architect")["auto"] is False
    assert I.derive_proposal("Head of Data at Globex", "Head of Data bei Globex\nGlobex sucht Verstärkung.\n")["auto"] is True


def test_a_headline_from_another_job_never_replaces_the_role():
    text = "Head of Data (m/w/d)\nGlobex AG sucht Verstärkung. Globex AG bietet viel.\nÄhnliche Jobs\nHead of Data Science & Analytics (m/w/d) - Initech\n"
    got = I.derive_proposal("Head of Data at Globex AG", text)
    assert got["role"] == "Head of Data (m/w/d)" or got["role"] == "Head of Data"
    assert "Initech" not in got["role"] and "Science" not in got["role"]


def test_the_automatic_flag_survives_a_failed_move_and_a_second_run_and_shows_for_existing_rows(tmp_path):
    root, system, inbox = env(tmp_path)
    (inbox / "AI Governance Officer at Contoso.pdf").write_bytes(b"%PDF contoso")
    import unittest.mock as um
    with um.patch.object(I, "move_unique", side_effect=OSError("disk full")):
        run(root, system, extractor=lambda p: CONTOSO)
    side = inbox / "AI Governance Officer at Contoso.md"
    assert "Bestätigt: ja" in side.read_text(encoding="utf-8") and "Automatisch geprüft" in side.read_text(encoding="utf-8")
    rep = run(root, system, extractor=lambda p: CONTOSO)
    entries = rep["healed"] + rep["existing"] + rep["new"]
    assert entries and all(e.get("auto") is True for e in entries)
    import today_view as TV
    lines = TV.build_context([], None, "2026-09-26", intake=rep)["intake_lines"]
    assert [l["label"] for l in lines] == ["Automatisch angelegt"]
