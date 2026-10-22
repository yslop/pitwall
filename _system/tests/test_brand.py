"""XLRTE brand v0.4: tokens, contrast, fonts, logo assets and logo use on the rendered pages."""
import os
import re
import subprocess
import sys

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER_PY = os.path.join(SYSTEM_DIR, "render.py")
COLS = ("uid,company,role,lane,stage,outcome,applied,last_event,days_idle,score,boost,salary_fit,location,"
        "contacts,folder_id,next_action,due,note\n")


def render_pages(tmp_path):
    """Run render.py on one synthetic row; returns the output folder."""
    data = tmp_path / "pipeline.csv"
    data.write_text(COLS + "133,Nordberatung,Manager,Executive,Interviewing,,2026-07-01,2026-09-24,1,80,0,high,HH,,f1,x,2026-10-01,n\n",
                    encoding="utf-8")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, RENDER_PY, "--data", str(data), "--prep", str(tmp_path / "none.json"),
                          "--folders", str(tmp_path / "none.tsv"), "--transitions", str(tmp_path / "none.csv"),
                          "--today", "2026-09-25", "--out", str(out), "--no-pdf"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return out


# ---- brand tokens -------------------------------------------------------------------------------
def _lum(h):
    h = h.lstrip("#")
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def css_block(css, start_marker):
    i = css.index(start_marker)
    return css[i: css.index("}", i)]


def var(block, name):
    return re.search(r"%s:\s*(#[0-9A-Fa-f]{6})" % re.escape(name), block).group(1)


def theme():
    return open(os.path.join(SYSTEM_DIR, "theme.css"), encoding="utf-8").read()


def test_brand_tokens_match_style_guide():
    b = css_block(theme().split("XLRTE Brand v0.4")[1], ":root {")
    assert var(b, "--xl-ink").upper() == "#1A1A1A" and var(b, "--xl-accent").upper() == "#E4572E"
    assert var(b, "--xl-accent-text").upper() == "#C4421D" and var(b, "--xl-muted").upper() == "#6B6B6B"
    assert var(b, "--xl-line").upper() == "#E3E3E3" and var(b, "--xl-paper").upper() == "#FFFFFF"


def test_text_tokens_meet_wcag_aa_in_light_and_dark():
    css = theme().split("XLRTE Brand v0.4")[1]
    light = css_block(css, ":root {")
    dark = css_block(css, ':root[data-theme="dark"] {')
    for fg, bg in (("--ink", "--panel"), ("--muted", "--panel"), ("--muted", "--panel-2"), ("--xl-accent-text", "--panel"),
                   ("--xl-accent-text", "--panel-2"), ("--xl-ok", "--panel")):
        assert contrast(var(light, fg), var(light, bg)) >= 4.5, ("light", fg, bg)
    for fg, bg in (("--ink", "--panel"), ("--muted", "--panel"), ("--muted", "--panel-2"), ("--xl-accent-text", "--panel"),
                   ("--xl-accent-text", "--panel-2"), ("--xl-ok", "--panel")):
        assert contrast(var(dark, fg), var(dark, bg)) >= 4.5, ("dark", fg, bg)


def test_accent_only_one_hue_and_fonts_are_the_two_brand_faces():
    css = theme().split("XLRTE Brand v0.4")[1]
    assert '"Jost"' in css and '"Nunito Sans"' in css
    assert css.count("#E4572E") <= 6 and "font-weight: 500" not in css and "font-weight: 600" not in css


# ---- logo assets --------------------------------------------------------------------------------
def test_logo_assets_present_and_recolourable():
    logo = open(os.path.join(SYSTEM_DIR, "assets", "xlrte-logo.svg"), encoding="utf-8").read()
    assert logo.count('fill="#E4572E"') == 1                    # vermilion chevron only; letters take the CSS colour
    assert 'class="logo"' in logo and "<title>XLRTE</title>" in logo
    for name in ("x-monogram.svg", "pe-mark.svg"):
        assert os.path.getsize(os.path.join(SYSTEM_DIR, "assets", name)) > 100


def test_logo_height_at_or_above_guide_minimum():
    m = re.search(r"\.brandmark svg \{ height: (\d+)px", theme())
    assert m and int(m.group(1)) >= 16


def test_logo_once_per_page_small_and_never_live_text(tmp_path):
    out = render_pages(tmp_path)
    for name in sorted(n for n in os.listdir(out) if n.endswith(".html")):
        html = (out / name).read_text(encoding="utf-8")
        assert html.count('class="brandmark"') == 1, name
        assert "<svg" in html.split('class="brandmark"')[1][:200], name
        for h1 in re.findall(r"<h1>(.*?)</h1>", html, re.S):
            assert "XLRTE" not in h1, "wordmark must come from the logo file, not live text"
        assert 'rel="icon"' in html and "family=Jost" in html and "Nunito+Sans" in html, name


def test_font_stacks_fall_back_to_system_fonts_when_offline():
    css = theme().split("XLRTE Brand v0.4")[1]
    head = re.search(r"--font-head:\s*([^;]+);", css).group(1)
    body = re.search(r"--font-body:\s*([^;]+);", css).group(1)
    assert "sans-serif" in head and "system-ui" in body


def test_dark_mode_active_chip_and_nav_tab_meet_contrast():
    css = theme().split("XLRTE Brand v0.4")[1]
    chips = re.findall(r"\.chip\.st\.on\s*\{\s*background:\s*(#[0-9A-Fa-f]{6});[^}]*color:\s*(#[0-9A-Fa-f]{6})", css)
    assert len(chips) == 2                                       # the media-query variant and the data-theme variant
    for bg, fg in chips:
        assert contrast(bg, fg) >= 4.5, (bg, fg)
    nav = re.search(r"nav\.views a\.on\s*\{\s*color:\s*(#[0-9A-Fa-f]{6})", css)
    assert nav and contrast(nav.group(1), "#FFFFFF") >= 4.5
