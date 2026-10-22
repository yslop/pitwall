import csv, json, os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import md_render as M
import xml.dom.minidom

CV = """# MAX MUSTERMANN

**Head of Data** · Hamburg
max@example.org · +49 160 1234567

## At a glance

| 15+ | 56 | 3 |
|---|---|---|
| years executive IT | global sites | continents |

## Professional experience

### Beispiel AG — Head of Data
Hamburg · 2020 – 2026

- **KPI framework:** delivered one governed platform for 44 legal entities.
- Led *up to 9* people, see [profile](https://example.org/p) and [mail](mailto:max@example.org).

> "Outstanding work." — CFO

## Education

Dipl.-Ing. Computer Science, TUHH.

## Skills

Python, SQL, Power BI.
"""


def docx_xml(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def test_html_escapes_everything_and_keeps_only_http_and_mailto_links():
    h = M.to_html("# <script>alert(1)</script>\n\n[x](javascript:alert(1)) and [ok](https://example.org/a?b=1&c=2) <img src=x onerror=y>\n")
    assert "<script" not in h and "javascript:" not in h and "&lt;script&gt;" in h and "&lt;img" in h
    assert '<a href="https://example.org/a?b=1&amp;c=2">ok</a>' in h and ">x<" not in h.replace("&lt;", "")


def test_html_headings_lists_quotes_tables_and_emphasis():
    h = M.to_html(CV)
    for part in ("<h1>MAX MUSTERMANN</h1>", "<h2>At a glance</h2>", "<h3>Beispiel AG — Head of Data</h3>", "<strong>KPI framework:</strong>", "<em>up to 9</em>",
                 "<ul>", "<blockquote>", "<table>", "<th>15+</th>", "<td>years executive IT</td>"):
        assert part in h, part


def test_a_strip_of_numbers_over_labels_is_flattened_into_one_plain_line():
    flat = M.flatten_tables(CV)
    assert "15+ years executive IT · 56 global sites · 3 continents" in flat and "|" not in flat
    other = M.flatten_tables("| Firma | Ort |\n|---|---|\n| A AG | Hamburg |\n| B AG | Berlin |\n")
    assert other.splitlines()[:3] == ["Firma · Ort", "A AG · Hamburg", "B AG · Berlin"]


def test_docx_is_valid_ats_safe_and_has_real_headings_and_bullets(tmp_path):
    p = M.write_docx(CV, str(tmp_path / "a.docx"))
    parts = docx_xml(p)
    for name, xml_text in parts.items():
        xml.dom.minidom.parseString(xml_text)
    doc = parts["word/document.xml"]
    assert "<w:tbl" not in doc and "<w:drawing" not in doc and 'w:pStyle w:val="Title"' in doc and 'w:pStyle w:val="Heading1"' in doc and 'w:pStyle w:val="Heading2"' in doc and 'w:pStyle w:val="Heading3"' not in doc
    assert doc.count("<w:numPr>") == 2 and "<w:b/>" in doc and "<w:i/>" in doc
    assert "15+ years executive IT" in doc and "profile (https://example.org/p)" in doc and "max@example.org" in doc
    assert not any(n.startswith("word/media") or "header" in n or "footer" in n for n in parts)
    assert not [f for f in os.listdir(tmp_path) if f.startswith(".")]                                    # temp file was moved into place


def test_docx_escapes_text_and_survives_empty_input(tmp_path):
    p = M.write_docx("# A & B <c>\n\nText mit \"Anführungszeichen\" & Umlauten äöü.\n", str(tmp_path / "b.docx"))
    doc = docx_xml(p)["word/document.xml"]
    assert "A &amp; B &lt;c&gt;" in doc and "äöü" in doc
    M.write_docx("", str(tmp_path / "c.docx"))
    xml.dom.minidom.parseString(docx_xml(str(tmp_path / "c.docx"))["word/document.xml"])


import ats_check as A


def test_the_plain_docx_passes_the_ats_check_and_layout_elements_fail_it(tmp_path):
    good = M.write_docx(CV, str(tmp_path / "good.docx"))
    assert A.status(A.check_docx(good, "CV")) == "pass"
    def rebuild(name, doc_xml=None, extra=None):
        out = str(tmp_path / name)
        with zipfile.ZipFile(good) as zin, zipfile.ZipFile(out, "w") as zout:
            for n in zin.namelist():
                zout.writestr(n, doc_xml if (n == "word/document.xml" and doc_xml) else zin.read(n))
            for n, data in (extra or {}).items():
                zout.writestr(n, data)
        return out
    doc = docx_xml(good)["word/document.xml"]
    assert A.status(A.check_docx(rebuild("t.docx", doc.replace("<w:body>", "<w:body><w:tbl></w:tbl>")), "CV")) == "fail"
    assert A.status(A.check_docx(rebuild("d.docx", doc.replace("<w:body>", "<w:body><w:p><w:r><w:drawing/></w:r></w:p>")), "CV")) == "fail"
    assert A.status(A.check_docx(rebuild("h.docx", extra={"word/header1.xml": "<x/>"}), "CV")) == "warn"
    assert A.status(A.check_docx(rebuild("i.docx", extra={"word/media/logo.png": b"x"}), "CV")) == "fail"


def test_ats_check_reports_missing_contact_headings_text_and_unreadable_files(tmp_path):
    thin = M.write_docx("# Name\n\n" + "Wort " * 60 + "\n", str(tmp_path / "thin.docx"))
    rules = {f["rule"] for f in A.check_docx(thin, "CV")}
    assert {"contact", "headings"} <= rules and "layout" not in rules
    assert "headings" not in {f["rule"] for f in A.check_docx(thin, "CL")}                                # a letter has no CV headings
    tiny = M.write_docx("# Name\n\nKurz.\n", str(tmp_path / "tiny.docx"))
    assert A.status(A.check_docx(tiny, "CV")) == "fail"
    (tmp_path / "bad.docx").write_bytes(b"not a zip")
    assert A.check_docx(str(tmp_path / "bad.docx"))[0]["rule"] == "readable" and A.check_docx(str(tmp_path / "nope.docx"))[0]["level"] == "fail"


def test_ats_check_of_a_pdf_counts_pages_and_needs_extractable_text(tmp_path, monkeypatch):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 /Type /Page /Parent 1 /Type /Page /Type /Pages")
    assert A.pdf_pages(str(pdf)) == 2 and A.pdf_pages(str(tmp_path / "missing.pdf")) == 0
    monkeypatch.setattr(A, "pdf_text", lambda p: "max@example.org +49 160 1234567 " + "Wort " * 60)
    assert [f["rule"] for f in A.check_pdf(str(pdf), "CL")] == ["length"]                                  # 2 pages, a letter allows 1
    monkeypatch.setattr(A, "pdf_text", lambda p: "Bild")
    assert A.status(A.check_pdf(str(pdf), "CV")) == "fail"
    monkeypatch.setattr(A, "pdf_text", lambda p: None)
    assert {f["rule"] for f in A.check_pdf(str(pdf), "CV")} == {"text"}
    (tmp_path / "e.pdf").write_bytes(b"")
    assert A.check_pdf(str(tmp_path / "e.pdf"))[0]["rule"] == "readable"


import company_brand as B

PAGE = """<html><head><meta name="theme-color" content="#0A3D91">
<link rel="stylesheet" href="/a.css"><style>:root{--brand-primary:#0A3D91;--accent:#E4572E;--grey:#cccccc}
body{font-family:"Open Sans",Arial,sans-serif;color:#222}h1{font-family:'Open Sans'}a{color:#0A3D91}.x{background:#eeeeee}</style></head>
<body><header><img class="site-logo" alt="ACME logo" src="/img/logo.svg"><img src="/hero.jpg"></header></body></html>"""
API_SEARCH = json.dumps({"query": {"search": [{"title": "Acme Corporation"}]}}).encode()
API_IMAGES = json.dumps({"query": {"pages": {"1": {"images": [{"title": "File:Acme building.jpg"}, {"title": "File:Acme logo.png"}, {"title": "File:Acme logo.svg"}]}}}}).encode()
API_INFO = json.dumps({"query": {"pages": {"2": {"imageinfo": [{"url": "https://upload.wikimedia.org/x/Acme_logo.svg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Acme_logo.svg",
                                                               "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}}).encode()
SVG = b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'><rect width='10' height='10' fill='#0A3D91'/></svg>"


def fake_web(extra=None):
    routes = {"https://acme.example/": {"status": 200, "body": PAGE.encode(), "type": "text/html", "url": "https://acme.example/"},
              "https://acme.example/a.css": {"status": 200, "body": b"h2{font-family:'Open Sans'}", "type": "text/css"},
              "https://acme.example/img/logo.svg": {"status": 200, "body": SVG, "type": "image/svg+xml"},
              "https://upload.wikimedia.org/x/Acme_logo.svg": {"status": 200, "body": SVG, "type": "image/svg+xml"}}
    routes.update(extra or {})
    seen = []
    def fetch(url, limit):
        seen.append(url)
        if "action=query" in url and "list=search" in url:
            return {"status": 200, "body": API_SEARCH}
        if "action=query" in url and "prop=images" in url:
            return {"status": 200, "body": API_IMAGES}
        if "action=query" in url and "prop=imageinfo" in url:
            return {"status": 200, "body": API_INFO}
        if url.startswith("https://fonts.googleapis.com/"):
            return {"status": 200, "body": b""}
        return routes.get(url)
    fetch.seen = seen
    return fetch


def test_palette_prefers_brand_colours_ignores_neutrals_and_fixes_contrast():
    pal = B.pick_palette(PAGE, [])
    assert pal["primary"] == "#0A3D91" and pal["accent"] == "#E4572E"
    assert B.pick_palette("<style>a{color:#cccccc;background:#eeeeee;border:1px solid #333}</style>", []) is None
    light = B.pick_palette("<meta name='theme-color' content='#FFD700'>", [])
    assert B.legible(light["primary"]) and light["primary"] != "#FFD700"
    assert B.contrast_on_white("#000000") > 20 and not B.legible("#FFFF00")


def test_fonts_are_parsed_and_chosen_google_installed_or_fallback(tmp_path):
    fams = B.parse_fonts([PAGE, "p{font-family:Lato,sans-serif} h2{font-family:var(--x)} li{font-family:system-ui}"])
    assert fams[0] == ("Open Sans", 2) and ("Lato", 1) in fams and all(f not in ("Arial", "sans-serif") for f, _ in fams)
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "OpenSans-Regular.ttf").write_bytes(b"x")
    assert B.choose_fonts(fams, lambda u, n: None, [str(tmp_path / "fonts")]) == {"heading": "Open Sans", "body": "Open Sans", "source": "installed"}
    calls = []
    def fake(url, n):
        calls.append(url)
        return {"status": 200, "body": b""} if "Open+Sans" in url else None
    assert B.choose_fonts(fams, fake, [])["source"] == "google" and "fonts.googleapis.com/css2?family=Open+Sans" in calls[0]
    serif = B.choose_fonts([("Playfair Display", 3)], lambda u, n: None, [])
    assert serif == {"heading": "Georgia", "body": "Georgia", "source": "fallback"}
    assert B.choose_fonts([], lambda u, n: None, [])["heading"] == "Calibri"


def test_images_are_recognised_by_content_and_unsafe_svgs_are_rejected():
    assert B.sniff_image(b"\x89PNG\r\n\x1a\n....") == "png" and B.sniff_image(b"\xff\xd8\xff\xe0") == "jpg" and B.sniff_image(b"<svg xmlns='x'></svg>") == "svg"
    assert B.sniff_image(b"<html>not an image</html>") is None and B.sniff_image(b"GIF89a") is None
    assert B.svg_is_safe(b"<svg xmlns='http://www.w3.org/2000/svg'><path d='M0 0'/><use href='#a'/></svg>")
    for bad in (b"<svg><script>alert(1)</script></svg>", b"<svg onload='x()'></svg>", b"<svg><foreignObject/></svg>", b"<svg><image href='https://evil.example/x.png'/></svg>",
                b"<svg><a xlink:href='javascript:x'/></svg>", b"<!DOCTYPE svg [<!ENTITY a 'b'>]><svg/>", b"<svg><rect style='fill:url(https://e.example/x)'/></svg>"):
        assert not B.svg_is_safe(bad), bad


def test_logo_candidates_rank_svg_logos_first_and_skip_other_images():
    got = B.logo_candidates(PAGE + '<img src="data:image/png;base64,AAA" alt="logo">', "https://acme.example/")
    assert got == ["https://acme.example/img/logo.svg"]
    with_icon = B.logo_candidates('<link rel="icon" href="/fav.png"><img alt="Company Logo" src="https://cdn.example/l.png">', "https://acme.example/")
    assert with_icon == ["https://cdn.example/l.png", "https://acme.example/fav.png"]
    assert B.logo_candidates('<img src="http://insecure.example/logo.png" alt="logo">', "https://a.example/") == []


def test_wikipedia_logo_takes_the_svg_logo_file_with_its_licence_and_fails_soft():
    got = B.wikipedia_logo("Acme", fake_web())
    assert got == {"url": "https://upload.wikimedia.org/x/Acme_logo.svg", "page": "https://commons.wikimedia.org/wiki/File:Acme_logo.svg", "license": "CC BY-SA 4.0", "title": "File:Acme logo.svg"}
    assert B.wikipedia_logo("Acme", lambda u, n: None) is None
    assert B.wikipedia_logo("Acme", lambda u, n: {"status": 200, "body": b"{}"}) is None


def test_website_comes_from_an_override_or_a_company_link_never_from_a_job_board():
    assert B.website_from_row({"note": "Eigener Fund · https://gs1ca.pinpointhq.com/postings/x"}) == ""
    assert B.website_from_row({"note": "https://www.linkedin.com/jobs/view/1"}) == ""
    assert B.website_from_row({"note": "Quelle https://careers.acme.example/job/1 ok"}) == "https://careers.acme.example/"
    assert B.website_from_row({"note": "https://gs1ca.pinpointhq.com/x"}, "https://www.gs1ca.org/path") == "https://www.gs1ca.org/"


def test_fetch_url_refuses_plain_http_and_offline_returns_none():
    assert B.fetch_url("http://acme.example/", 100) is None and B.fetch_url("ftp://x", 100) is None


import draft_lint as L


def world(tmp_path, with_drafts=True):
    base = tmp_path / "career"
    system = base / "_system"
    role = base / "215 Acme AG" / "Head of Data"
    (role / "10 Bewerbung").mkdir(parents=True)
    (role / "20 Vorbereitung").mkdir(parents=True)
    system.mkdir()
    with open(system / "pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "company", "role", "folder_id", "note"])
        w.writeheader()
        w.writerow({"uid": "215", "company": "Acme AG", "role": "Head of Data", "folder_id": "", "note": "Eigener Fund · https://acme.pinpointhq.com/x"})
    if with_drafts:
        (role / "10 Bewerbung" / "CV_Acme_AG_Head_of_Data_v1.md").write_text(CV, encoding="utf-8")
        (role / "10 Bewerbung" / "CL_Acme_AG_Head_of_Data_v1.md").write_text("# MAX MUSTERMANN\n\nDear Team,\n\n" + "Text " * 40 + "\n\nmax@example.org · +49 160 1234567\n", encoding="utf-8")
    return str(system), str(base), role, (lambda b, u, r, fid="": (role, []))


def test_build_brand_reads_colours_fonts_and_logo_from_the_site_with_fallbacks_noted(tmp_path):
    rec, logo, ext = B.build_brand("Acme", "https://acme.example/", fake_web(), "2026-09-26", [])
    assert rec["colors"]["primary"] == "#0A3D91" and rec["colors"]["accent"] == "#E4572E" and rec["colors"]["source"] == "website"
    assert rec["fonts"] == {"heading": "Open Sans", "body": "Open Sans", "source": "google"}
    assert rec["logo"] == {"source": "website", "url": "https://acme.example/img/logo.svg"} and ext == "svg" and logo == SVG and rec["notes"] == []
    hostile = fake_web({"https://acme.example/img/logo.svg": {"status": 200, "body": b"<svg><script>1</script></svg>", "type": "image/svg+xml"}})
    rec2, logo2, _ = B.build_brand("Acme", "https://acme.example/", hostile, "2026-09-26", [])
    assert rec2["logo"]["source"] == "wikipedia" and rec2["logo"]["license"] == "CC BY-SA 4.0" and logo2 == SVG                # site logo refused, Wikipedia used
    rec3, logo3, _ = B.build_brand("Acme", "", fake_web(), "2026-09-26", [])
    assert rec3["logo"]["source"] == "wikipedia" and any("Webseite fehlt" in n for n in rec3["notes"]) and rec3["colors"]["primary"] == B.PE["primary"]
    rec4, logo4, _ = B.build_brand("Acme", "https://acme.example/", lambda u, n: None, "2026-09-26", [])
    assert logo4 is None and rec4["colors"]["primary"] == B.PE["primary"] and any("nicht lesbar" in n for n in rec4["notes"]) and any("kein Logo" in n for n in rec4["notes"])


def test_run_brand_writes_the_record_and_logo_then_is_current_and_never_overwrites_a_confirmed_record(tmp_path):
    system, base, role, locate = world(tmp_path)
    res = B.run_brand("215", system, base, "2026-09-26", website="https://acme.example/", fetch=fake_web(), locate=locate, dirs=[])
    assert res["status"] == "written" and os.path.basename(res["file"]) == "Marke_Acme_AG.json"
    rec = json.load(open(res["file"], encoding="utf-8"))
    assert rec["colors"]["primary"] == "#0A3D91" and rec["logo"]["file"] == "Marke_logo.svg" and (role / "20 Vorbereitung" / "Marke_logo.svg").read_bytes() == SVG
    assert B.run_brand("215", system, base, "2026-09-27", fetch=fake_web(), locate=locate)["status"] == "current"
    rec["confirmed"] = True
    rec["colors"]["primary"] = "#112233"
    open(res["file"], "w", encoding="utf-8").write(json.dumps(rec))
    forced = B.run_brand("215", system, base, "2026-09-28", force=True, fetch=fake_web(), locate=locate, dirs=[])
    assert forced["status"] == "skipped" and "confirmed" in forced["reason"] and json.load(open(res["file"], encoding="utf-8"))["colors"]["primary"] == "#112233"


def test_your_own_logo_file_always_wins_and_is_never_overwritten(tmp_path):
    system, base, role, locate = world(tmp_path)
    mine = role / "logo.png"
    mine.write_bytes(b"\x89PNG\r\n\x1a\nMINE")
    B.run_brand("215", system, base, "2026-09-26", website="https://acme.example/", fetch=fake_web(), locate=locate, dirs=[])
    rec = B.load_brand(role)
    assert B.effective_logo(role, rec) == str(mine) and mine.read_bytes().endswith(b"MINE")
    mine.rename(role / "20 Vorbereitung" / "Logo.png")
    assert B.effective_logo(role, rec).lower() == str(role / "20 Vorbereitung" / "Logo.png").lower()          # the file system may ignore case
    (role / "20 Vorbereitung" / "Logo.png").rename(role / "x.png")
    assert B.effective_logo(role, rec).endswith("Marke_logo.svg")


def test_run_brand_reports_instead_of_raising(tmp_path):
    system, base, role, locate = world(tmp_path)
    assert B.run_brand("999", system, base, "2026-09-26", fetch=fake_web(), locate=locate)["status"] == "skipped"
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert B.run_brand("215", system, base, "2026-09-26", fetch=fake_web(), locate=broken)["status"] == "error"
    dry = B.run_brand("215", system, base, "2026-09-26", website="https://acme.example/", dry_run=True, fetch=fake_web(), locate=locate, dirs=[])
    assert dry["status"] == "written" and not os.listdir(role / "20 Vorbereitung")
    (role / "20 Vorbereitung" / "Marke_Acme_AG.json").write_text("{nope", encoding="utf-8")
    assert B.load_brand(role) is None


import render_docs as R


class Runner:
    """Stands in for Chrome: writes a small PDF where --print-to-pdf points."""
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = next(c for c in cmd if c.startswith("--print-to-pdf="))[len("--print-to-pdf="):]
        if self.ok:
            open(out, "wb").write(b"%PDF-1.4\n/Type /Page\n" + b"x" * 400)


def test_chrome_pdf_prints_through_a_temp_dir_and_reports_failure(tmp_path):
    r = Runner()
    target = str(tmp_path / "o.pdf")
    assert R.chrome_pdf("<html><body>hi</body></html>", target, chrome="/fake/chrome", runner=r) and os.path.getsize(target) > 200
    cmd = r.calls[0]
    assert cmd[0] == "/fake/chrome" and "--headless=new" in cmd and "--no-pdf-header-footer" in cmd and cmd[-1].startswith("file://")
    assert not R.chrome_pdf("<html/>", str(tmp_path / "n.pdf"), chrome="/fake/chrome", runner=Runner(ok=False)) and not os.path.exists(tmp_path / "n.pdf")
    assert not R.chrome_pdf("<html/>", str(tmp_path / "m.pdf"), chrome="/nonexistent/chrome", runner=Runner(ok=False))
    assert not [f for f in os.listdir(tmp_path) if f.startswith(".")]


def test_find_chrome_honours_the_environment_override(tmp_path):
    exe = tmp_path / "mychrome"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    assert R.find_chrome({"CHROME_BIN": str(exe)}) == str(exe)


def test_ci_html_applies_the_brand_and_falls_back_to_the_pe_look(tmp_path):
    logo = tmp_path / "logo.svg"
    logo.write_bytes(SVG)
    brand = {"colors": {"primary": "#0A3D91", "accent": "#E4572E"}, "fonts": {"heading": "Open Sans", "body": "Open Sans", "source": "google"}}
    h = R.ci_html(CV, "CV", brand, str(logo))
    assert "#0A3D91" in h and "#E4572E" in h and "'Open Sans'" in h and "fonts.googleapis.com/css2?family=Open+Sans" in h and 'src="data:image/svg+xml;base64,' in h
    pe = R.ci_html(CV, "CV", None, "")
    assert B.PE["primary"] in pe and "Calibri" in pe and "<img" not in pe and "fonts.googleapis" not in pe


def test_ci_html_ignores_hostile_brand_values_and_unsafe_logos(tmp_path):
    bad = {"colors": {"primary": "red;} body{display:none", "accent": "javascript:x"}, "fonts": {"heading": "x'}</style><script>1</script>", "body": "Calibri", "source": "google"}}
    h = R.ci_html(CV, "CV", bad, "")
    assert "display:none" not in h and "<script>" not in h and B.PE["primary"] in h and "fonts.googleapis" not in h
    evil = tmp_path / "logo.svg"
    evil.write_bytes(b"<svg><script>alert(1)</script></svg>")
    assert "<img" not in R.ci_html(CV, "CV", None, str(evil))
    light = R.ci_html(CV, "CV", {"colors": {"primary": "#FFFF00"}}, "")
    assert "#FFFF00" not in light.split("<body>")[0].split("h1,h2,h3{")[1].split("}")[0]                              # unreadable colours are darkened


def test_ats_html_is_plain_black_and_flattened():
    h = R.ats_html(CV)
    assert "<table" not in h and "color:#000" in h and "15+ years executive IT" in h and "border" not in h


def test_run_render_writes_ats_docx_ats_pdf_and_ci_pdf_per_draft_and_records_the_state(tmp_path):
    system, base, role, locate = world(tmp_path)
    B.run_brand("215", system, base, "2026-09-26", website="https://acme.example/", fetch=fake_web(), locate=locate, dirs=[])
    r = Runner()
    res = R.run_render("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=r)
    assert res["status"] == "written" and res["version"] == "v1" and len(res["files"]) == 6 and len(r.calls) == 4
    bew = role / "10 Bewerbung"
    for stem in ("CV_Acme_AG_Head_of_Data_v1", "CL_Acme_AG_Head_of_Data_v1"):
        for suffix in ("_ATS.docx", "_ATS.pdf", "_CI.pdf"):
            assert (bew / (stem + suffix)).exists(), stem + suffix
    assert (bew / "CV_Acme_AG_Head_of_Data_v1.md").read_text(encoding="utf-8") == CV                          # the draft is untouched
    st = json.load(open(os.path.join(system, "render_state.json"), encoding="utf-8"))["215"]["v1"]
    assert st["brand"] == "Acme AG" and len(st["files"]) == 6 and st["ats"] in ("pass", "warn")
    assert not [f for f in os.listdir(bew) if f.startswith(".") or f.endswith(".html")]


def test_run_render_is_current_until_draft_brand_or_logo_change_and_force_rerenders(tmp_path):
    system, base, role, locate = world(tmp_path)
    r = Runner()
    args = dict(locate=locate, chrome="/fake/chrome", runner=r)
    assert R.run_render("215", system, base, "2026-09-26", **args)["status"] == "written"
    assert R.run_render("215", system, base, "2026-09-27", **args)["status"] == "current" and len(r.calls) == 4
    (role / "10 Bewerbung" / "CV_Acme_AG_Head_of_Data_v1.md").write_text(CV + "\nNoch ein Absatz.\n", encoding="utf-8")
    assert R.run_render("215", system, base, "2026-09-28", **args)["status"] == "written"
    (role / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nX")
    assert R.run_render("215", system, base, "2026-09-29", **args)["status"] == "written"
    assert R.run_render("215", system, base, "2026-09-30", force=True, **args)["status"] == "written"
    (role / "10 Bewerbung" / "CL_Acme_AG_Head_of_Data_v1_CI.pdf").rename(role / "10 Bewerbung" / "moved.pdf")
    assert R.run_render("215", system, base, "2026-10-01", **args)["status"] == "written"                       # a missing file is re-created


def test_a_new_draft_version_gets_new_files_and_old_ones_stay(tmp_path):
    system, base, role, locate = world(tmp_path)
    args = dict(locate=locate, chrome="/fake/chrome", runner=Runner())
    R.run_render("215", system, base, "2026-09-26", **args)
    (role / "10 Bewerbung" / "CV_Acme_AG_Head_of_Data_v2.md").write_text(CV.replace("Head of Data", "Head of AI"), encoding="utf-8")
    res = R.run_render("215", system, base, "2026-09-27", **args)
    assert res["version"] == "v2" and res["files"] == ["CV_Acme_AG_Head_of_Data_v2_ATS.docx", "CV_Acme_AG_Head_of_Data_v2_ATS.pdf", "CV_Acme_AG_Head_of_Data_v2_CI.pdf"]
    assert (role / "10 Bewerbung" / "CV_Acme_AG_Head_of_Data_v1_CI.pdf").exists()
    assert R.run_render("215", system, base, "2026-09-27", version="v1", **args)["status"] == "current"


def test_without_chrome_the_docx_is_written_and_html_is_kept_for_printing(tmp_path, monkeypatch):
    system, base, role, locate = world(tmp_path)
    monkeypatch.setattr(R, "find_chrome", lambda env=None: None)
    res = R.run_render("215", system, base, "2026-09-26", locate=locate, chrome=None)
    bew = role / "10 Bewerbung"
    assert res["status"] == "written" and (bew / "CV_Acme_AG_Head_of_Data_v1_ATS.docx").exists() and (bew / "CV_Acme_AG_Head_of_Data_v1_CI.html").exists()
    assert not (bew / "CV_Acme_AG_Head_of_Data_v1_CI.pdf").exists() and any("Chrome" in n for n in res["notes"])


def test_run_render_reports_missing_pieces_and_never_raises(tmp_path):
    system, base, role, locate = world(tmp_path, with_drafts=False)
    assert R.run_render("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=Runner())["status"] == "skipped"
    system, base, role, locate = world(tmp_path / "b")
    assert R.run_render("215", system, base, "2026-09-26", version="v9", locate=locate, chrome="/f", runner=Runner())["status"] == "skipped"
    assert R.run_render("999", system, base, "2026-09-26", locate=locate, chrome="/f", runner=Runner())["status"] == "skipped"
    def broken(b, u, r, fid=""): raise OSError("Drive offline")
    assert R.run_render("215", system, base, "2026-09-26", locate=broken, chrome="/f", runner=Runner())["status"] == "error"
    open(os.path.join(system, "render_state.json"), "w", encoding="utf-8").write(json.dumps({"215": {"v1": "x"}, "9": []}))
    assert R.run_render("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=Runner())["status"] == "written"
    (role / "10 Bewerbung" / "CV_Acme_AG_Head_of_Data_v1.md").write_bytes("Umlaut ü".encode("cp1252"))
    res = R.run_render("215", system, base, "2026-09-27", locate=locate, chrome="/fake/chrome", runner=Runner())
    assert res["status"] == "written" and any("nicht lesbar" in n for n in res["notes"])


def test_dry_run_writes_nothing_and_the_cli_prints_the_files(tmp_path, capsys):
    system, base, role, locate = world(tmp_path)
    res = R.run_render("215", system, base, "2026-09-26", dry_run=True, locate=locate, chrome="/fake/chrome", runner=Runner())
    assert res["status"] == "written" and len(res["files"]) == 6 and not os.path.exists(os.path.join(system, "render_state.json"))
    assert not any(n.endswith((".docx", ".pdf")) for n in os.listdir(role / "10 Bewerbung"))
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate), um.patch.object(R, "chrome_pdf", lambda h, p, c=None, r=None, timeout=60: (open(p, "wb").write(b"%PDF-1.4 /Type /Page " + b"x" * 300) and True)):
        assert R.main(["--uid", "215", "--system", system, "--base-dir", base, "--today", "2026-09-26"]) in (0, 1)
    assert "render_docs uid 215: written · v1" in capsys.readouterr().out


# ---- review fix pass -------------------------------------------------------------------------------------------
def test_a_pipe_line_without_a_separator_row_is_a_paragraph_and_never_hangs(tmp_path):
    import signal
    def alarm(*a): raise TimeoutError("parse did not finish")
    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(10)
    try:
        for md in ("| a |\nfoo", "|", "| Skills | Python |\n| Tools | SQL |", ">\n|\n>", "|a|\n|b|\n\ntext"):
            assert M.parse(md) and "|" in M.to_html(md)
        M.write_docx("| Skills | Python |\n| Tools | SQL |\n", str(tmp_path / "t.docx"))
    finally:
        signal.alarm(0)


def test_characters_that_are_invalid_in_xml_are_dropped_and_the_ats_check_parses_the_xml(tmp_path):
    p = M.write_docx("# Name\n\nZeile\x0bmit\x0cSteuerzeichen\x00 und Text.\n", str(tmp_path / "c.docx"))
    xml.dom.minidom.parseString(docx_xml(p)["word/document.xml"])
    assert "Zeilemit" in docx_xml(p)["word/document.xml"].replace("SteuerzeichenSteuerzeichen", "") or "Steuerzeichen" in docx_xml(p)["word/document.xml"]
    broken = str(tmp_path / "broken.docx")
    with zipfile.ZipFile(p) as zin, zipfile.ZipFile(broken, "w") as zout:
        for n in zin.namelist():
            zout.writestr(n, zin.read(n).replace(b"Name", b"Na\x0bme") if n == "word/document.xml" else zin.read(n))
    f = A.check_docx(broken, "CV")
    assert A.status(f) == "fail" and any(x["rule"] == "readable" for x in f)


def test_svg_allowlist_rejects_namespaced_scripts_animation_imports_and_foreign_elements():
    ok = b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><style>.a{fill:#0A3D91}</style><g><path class='a' d='M0 0h10v10z'/></g></svg>"
    assert B.svg_is_safe(ok)
    for bad in (b"<svg xmlns='http://www.w3.org/2000/svg' xmlns:s='http://www.w3.org/2000/svg'><s:script>alert(1)</s:script></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg'><animate attributeName='href' values='javascript:alert(1)'/></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg'><set attributeName='onclick' to='x'/></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg'><style>@import 'https://evil.example/x.css';</style></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg' xmlns:h='http://www.w3.org/1999/xhtml'><h:iframe src='https://evil.example'/></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg'><image href='data:image/svg+xml;base64,PHN2Zy8+'/></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg'><use xlink:href=' https://evil.example/x.svg#a' xmlns:xlink='http://www.w3.org/1999/xlink'/></svg>",
                b"<svg xmlns='http://www.w3.org/2000/svg'><a href='javascript:alert(1)'><rect/></a></svg>",
                b"<html><body>not svg</body></html>", b"<svg><g></svg>", b""):
        assert not B.svg_is_safe(bad), bad
    assert B.svg_is_safe(b"<svg xmlns='http://www.w3.org/2000/svg'><image href='data:image/png;base64,iVBORw0KGgo='/></svg>")


def test_a_failed_print_is_not_frozen_as_current(tmp_path):
    system, base, role, locate = world(tmp_path)
    bad = Runner(ok=False)
    first = R.run_render("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=bad)
    assert first["status"] == "written" and any(n.endswith(".html") for n in first["files"])
    again = R.run_render("215", system, base, "2026-09-27", locate=locate, chrome="/fake/chrome", runner=Runner())
    assert again["status"] == "written" and (role / "10 Bewerbung" / "CV_Acme_AG_Head_of_Data_v1_CI.pdf").exists()


def test_a_hand_edited_brand_record_with_missing_keys_never_crashes_the_cli_or_the_renderer(tmp_path, capsys):
    system, base, role, locate = world(tmp_path)
    (role / "20 Vorbereitung" / "Marke_Acme.json").write_text(json.dumps({"company": "Acme", "colors": {"primary": "#123456"}}), encoding="utf-8")
    import unittest.mock as um
    with um.patch("folder_utils.locate_role_folder", locate):
        assert B.main(["--uid", "215", "--system", system, "--base-dir", base]) == 0
    assert "company_brand uid 215: current" in capsys.readouterr().out
    res = R.run_render("215", system, base, "2026-09-26", locate=locate, chrome="/fake/chrome", runner=Runner())
    assert res["status"] == "written" and "#123456" in R.ci_html(CV, "CV", B.load_brand(role), "")


def test_company_sites_are_matched_by_host_label_not_by_substring():
    for company in ("https://clever.company/", "https://www.goodjobs.com/", "https://monsterenergy.com/", "https://careers.google.com/x"):
        assert B.website_from_row({"note": company}) != "", company
    for board in ("https://jobs.acme.com/x", "https://acme.pinpointhq.com/x", "https://boards.greenhouse.io/acme", "https://jobs.lever.co/acme", "https://www.linkedin.com/jobs/1",
                  "https://acme.myworkdayjobs.com/x", "https://www.stepstone.de/x", "https://karriere.acme.de/x"):
        assert B.website_from_row({"note": board}) == "", board


def test_font_names_are_cleaned_and_only_safe_names_reach_the_css(tmp_path):
    fams = B.parse_fonts(["a{font-family: Inter!important} b{font-family:'Comic Sans' /* c */ , serif} /* p{font-family:Hidden} */ c{font-family:&quot;X&quot;}"])
    names = [f for f, _ in fams]
    assert "Inter" in names and "Comic Sans" in names and "Hidden" not in names and not any(("!" in n or "&" in n or "*" in n) for n in names)
    h = R.ci_html(CV, "CV", {"colors": {}, "fonts": {"heading": "Levi's & Co", "body": "Calibri", "source": "google"}}, "")
    assert "Levi" not in h and "fonts.googleapis" not in h                                            # not a plain font name: PE look instead


def test_unreadable_ink_and_panel_colours_fall_back_to_the_pe_values():
    h = R.ci_html(CV, "CV", {"colors": {"primary": "#0A3D91", "ink": "#FFFFFF", "accent": "#E4572E"}}, "")
    body = h.split("body{")[1].split("}")[0]
    assert "color:#FFFFFF" not in body and "color:%s" % B.PE["ink"] in body


def test_https_redirects_to_plain_http_are_refused_before_the_request_is_made():
    import urllib.request
    handler = B.HttpsOnlyRedirect()
    req = urllib.request.Request("https://acme.example/")
    assert handler.redirect_request(req, None, 302, "Found", {}, "http://acme.example/x") is None
    assert handler.redirect_request(req, None, 302, "Found", {}, "https://acme.example/x") is not None


def test_year_ranges_are_not_phone_numbers_and_compressed_pdfs_are_not_read_as_empty(tmp_path, monkeypatch):
    md = "# Name\n\nmax@example.org\n\n2010 - 2011 Beispiel AG\n\n" + "Wort " * 60
    p = M.write_docx(md, str(tmp_path / "y.docx"))
    assert any(f["rule"] == "contact" and "Telefon" in f["text"] for f in A.check_docx(p, "CV"))
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.5 compressed object streams only " + b"x" * 300)
    monkeypatch.setattr(A, "pdf_pages_tool", lambda path: 2)
    assert A.pdf_pages(str(pdf)) == 2


def test_the_render_hash_follows_the_logo_content_not_only_its_size(tmp_path):
    system, base, role, locate = world(tmp_path)
    args = dict(locate=locate, chrome="/fake/chrome", runner=Runner())
    (role / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nAAAA")
    assert R.run_render("215", system, base, "2026-09-26", **args)["status"] == "written"
    (role / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nBBBB")                                         # same size, different content
    assert R.run_render("215", system, base, "2026-09-27", **args)["status"] == "written"


def test_the_standard_illustrator_doctype_is_fine_but_an_internal_subset_or_entity_is_not():
    illustrator = (b'<?xml version="1.0" encoding="iso-8859-1"?>\r\n<!-- Generator: Adobe Illustrator -->\r\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
                   b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\r\n<svg version="1.1" xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>')
    assert B.svg_is_safe(illustrator)
    assert not B.svg_is_safe(b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
    assert not B.svg_is_safe(b'<!DOCTYPE svg [ ]><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
    assert not B.svg_is_safe(b'<!DOCTYPE svg SYSTEM "x"><!ENTITY a "b"><svg xmlns="http://www.w3.org/2000/svg"/>')


def test_briefings_show_a_confidence_column_fed_by_the_render_data():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    t = open(os.path.join(here, "templates", "brief.html"), encoding="utf-8").read()
    r = open(os.path.join(here, "render.py"), encoding="utf-8").read()
    assert "r.confidence" in t and ">Chance<" in t
    assert 'r["confidence"]' in r
