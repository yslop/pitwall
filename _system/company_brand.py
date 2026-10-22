#!/usr/bin/env python3
"""
Company brand record (application path, Phase 3 stage A): colours, fonts and logo of a target company, for the CI-styled CV/CL PDFs.

Sources for the logo, in this order: a logo.svg / logo.png you put into the role folder (always wins, never overwritten), the company's own
site, Wikipedia / Wikimedia Commons (licence label kept). Only public pages, https only, small size limits, a handful of requests, no login,
nothing about you is sent. If a company's CI cannot be read, the record says so and the renderer uses your personal PE look.

`Marke_<Firma>.json` and `Marke_logo.<ext>` go into the role's `20 Vorbereitung`; you may edit the record (set "confirmed": true, change colours).

    python3 company_brand.py --uid 215 [--website https://example.com] [--force] [--dry-run]
    python3 company_brand.py --pinned
"""
import argparse
import colorsys
import csv
import datetime
import html
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request

import coverage as C

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "job-crm-brand/1.0 (personal job-search tool; contact via repository owner)"
PAGE_MAX, CSS_MAX, LOGO_MAX, TIMEOUT, MAX_CSS_FILES = 1_000_000, 500_000, 2_000_000, 10, 2
PE = {"primary": "#14213D", "accent": "#2E74B5", "ink": "#333333", "panel": "#F2F3F5", "heading_font": "Calibri", "body_font": "Calibri"}
BOARD_LABELS = {"linkedin", "xing", "indeed", "stepstone", "glassdoor", "kununu", "monster", "pinpointhq", "greenhouse", "lever", "workable", "softgarden", "personio",
                "smartrecruiters", "recruitee", "myworkdayjobs", "successfactors", "taleo", "bewerber", "bit", "jobvite", "icims", "ashbyhq", "teamtailor", "breezy"}
BOARD_FIRST_LABELS = {"jobs", "karriere", "stellenangebote", "stellenmarkt", "jobboerse", "jobportal"}


def is_board_host(host):
    """True for job boards and ATS hosts, by whole host labels ('clever.company' and 'monsterenergy.com' are not boards)."""
    labels = (host or "").lower().split(".")
    return any(l in BOARD_LABELS for l in labels) or (len(labels) > 2 and labels[0] in BOARD_FIRST_LABELS)
GENERIC_FONTS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "inherit", "initial", "ui-sans-serif", "ui-serif", "arial", "helvetica",
                 "times new roman", "-apple-system", "blinkmacsystemfont", "segoe ui", "roboto", "helvetica neue", "verdana", "tahoma"}
SERIF_HINTS = ("serif", "georgia", "garamond", "playfair", "merriweather", "lora", "times", "baskerville", "caslon", "libre baskerville")
HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
FONT_DECL = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
META_THEME = re.compile(r"<meta[^>]+name=[\"']theme-color[\"'][^>]*content=[\"']([^\"']+)[\"']|<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*name=[\"']theme-color[\"']", re.I)
LINK_CSS = re.compile(r"<link[^>]+rel=[\"']stylesheet[\"'][^>]*>", re.I)
HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ATTR = lambda name: re.compile(name + r"=[\"']([^\"']*)[\"']", re.I)
ICON_LINK = re.compile(r"<link[^>]+rel=[\"'](?:apple-touch-icon|icon|shortcut icon)[\"'][^>]*>", re.I)


# ── colours ──────────────────────────────────────────────────────────────────
def _norm_hex(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(h):
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_on_white(h):
    return 1.05 / (luminance(h) + 0.05)


def legible(h):
    return contrast_on_white(h) >= 4.5


def darken_until_legible(h):
    """The colour with lightness reduced until it reads on white (WCAG AA, 4.5:1); hue and saturation kept."""
    r, g, b = _rgb(h)
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    while ll > 0.05 and not legible("#%02X%02X%02X" % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hh, ll, ss))):
        ll -= 0.02
    return "#%02X%02X%02X" % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hh, ll, ss))


def _is_brandish(h):
    r, g, b = _rgb(h)
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return ss >= 0.25 and 0.12 <= ll <= 0.85


def _hue(h):
    r, g, b = _rgb(h)
    return colorsys.rgb_to_hls(r, g, b)[0]


def pick_palette(html_text, css_texts):
    """{'primary', 'accent'} from theme-color, brand-like custom properties and the most frequent saturated colours; None when nothing usable."""
    score = {}
    m = META_THEME.search(html_text or "")
    if m:
        for h in HEX.findall(m.group(1) or m.group(2) or ""):
            score[_norm_hex(h)] = score.get(_norm_hex(h), 0) + 6
    for text in [html_text or ""] + list(css_texts):
        for line in re.findall(r"--[\w-]*(?:primary|brand|accent|main)[\w-]*\s*:\s*[^;}{]+", text, re.I):
            for h in HEX.findall(line):
                score[_norm_hex(h)] = score.get(_norm_hex(h), 0) + 4
        for h in HEX.findall(text):
            score[_norm_hex(h)] = score.get(_norm_hex(h), 0) + 1
    ranked = [h for h, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0])) if _is_brandish(h)]
    if not ranked:
        return None
    primary = darken_until_legible(ranked[0]) if not legible(ranked[0]) else ranked[0]
    accent = next((h for h in ranked[1:] if abs(_hue(h) - _hue(ranked[0])) > 0.06 and h != ranked[0]), None)
    return {"primary": primary, "accent": accent or primary}          # the accent colours rules and borders only, so it needs no text contrast


# ── fonts ────────────────────────────────────────────────────────────────────
def parse_fonts(css_texts):
    """[(family, count)] of named font families (generic and system families dropped), most used first."""
    count = {}
    for text in css_texts:
        for decl in FONT_DECL.findall(re.sub(r"/\*.*?\*/", "", text, flags=re.S)):
            decl = html.unescape(re.sub(r"!\s*important", "", decl))
            first = decl.split(",")[0].strip().strip("'\"").strip()
            if not re.fullmatch(r"[\w .-]{1,40}", first):
                continue
            if first and first.lower() not in GENERIC_FONTS and not first.startswith(("var(", "$")) and len(first) < 40:
                count[first] = count.get(first, 0) + 1
    return sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))


def font_dirs():
    home = os.path.expanduser("~")
    return ["/Library/Fonts", "/System/Library/Fonts", os.path.join(home, "Library", "Fonts")]


def font_installed(family, dirs=None):
    key = re.sub(r"\W", "", family.lower())
    for d in dirs if dirs is not None else font_dirs():
        try:
            for n in os.listdir(d):
                if key and key in re.sub(r"\W", "", n.lower()):
                    return True
        except OSError:
            continue
    return False


def choose_fonts(families, fetch, dirs=None):
    """{'heading', 'body', 'source': 'google'|'installed'|'fallback'}. Google Fonts is asked with one request per candidate (at most 2)."""
    for fam, _ in families[:2]:
        if font_installed(fam, dirs):
            return {"heading": fam, "body": fam, "source": "installed"}
        url = "https://fonts.googleapis.com/css2?family=%s" % urllib.parse.quote(fam.replace(" ", "+"), safe="+")
        got = fetch(url, 200_000)
        if got and got.get("status") == 200:
            return {"heading": fam, "body": fam, "source": "google"}
    serif = any(h in " ".join(f for f, _ in families[:2]).lower() for h in SERIF_HINTS)
    return {"heading": "Georgia" if serif else PE["heading_font"], "body": "Georgia" if serif else PE["body_font"], "source": "fallback"}


# ── logo ─────────────────────────────────────────────────────────────────────
def sniff_image(data):
    """'png' | 'jpg' | 'svg' by content, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    head = data[:2000].lstrip().lower()
    if head.startswith((b"<svg", b"<?xml")) and b"<svg" in data[:4000].lower():
        return "svg"
    return None


SVG_NS = "{http://www.w3.org/2000/svg}"
SVG_OK = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient", "stop", "clippath", "mask",
          "title", "desc", "symbol", "text", "tspan", "pattern", "style", "use", "image", "metadata"}
SVG_BAD_STYLE = re.compile(r"@import|expression\s*\(|javascript:|behavior\s*:|url\(\s*[\"']?\s*(?!#)", re.I)


def svg_is_safe(data):
    """Allowlist check: a well-formed SVG whose every element is a plain drawing element in the SVG namespace, without event handlers, scripts, animation,
    foreign content, DOCTYPE/entities, external references (only #fragment or raster data: images) or style rules that load anything."""
    import xml.etree.ElementTree as ET
    low = data.lower()
    if b"<!entity" in low or (b"<![cdata[" in low and b"<script" in low):
        return False
    doctype = re.search(rb"<!doctype[^>]*", low)
    if doctype and b"[" in doctype.group(0):                    # a plain 'PUBLIC ... svg11.dtd' line (Illustrator) is fine, an internal subset is not
        return False
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError):
        return False
    if root.tag != SVG_NS + "svg":
        return False
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(SVG_NS) or el.tag[len(SVG_NS):].lower() not in SVG_OK:
            return False
        name = el.tag[len(SVG_NS):].lower()
        for attr, val in el.attrib.items():
            local = attr.rsplit("}", 1)[-1].lower()
            if local.startswith("on") or "javascript:" in val.lower() or "\n" in val and local in ("href", "src"):
                return False
            if local == "href" or local == "src":
                v = val.strip()
                if not (v.startswith("#") or re.match(r"^data:image/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]*$", v, re.I)):
                    return False
            if local == "style" and SVG_BAD_STYLE.search(val):
                return False
        if name == "style" and SVG_BAD_STYLE.search("".join(el.itertext())):
            return False
    return True


def logo_candidates(html_text, base_url):
    """URLs likely to be the company logo, best first: header/logo-named images, then the site icon."""
    scored = []
    for tag in IMG_TAG.findall(html_text or ""):
        src = (ATTR("src").search(tag) or [None, ""])[1] if ATTR("src").search(tag) else ""
        if not src or src.startswith("data:"):
            continue
        alt = ATTR("alt").search(tag).group(1) if ATTR("alt").search(tag) else ""
        cls = ATTR("class").search(tag).group(1) if ATTR("class").search(tag) else ""
        hint = " ".join([src, alt, cls]).lower()
        if "logo" in hint:
            score = 3 + (2 if src.lower().endswith(".svg") else 0) + (1 if "header" in hint or "brand" in hint else 0)
            scored.append((score, urllib.parse.urljoin(base_url, src)))
    for tag in ICON_LINK.findall(html_text or ""):
        m = HREF.search(tag)
        if m:
            scored.append((0, urllib.parse.urljoin(base_url, m.group(1))))
    seen, out = set(), []
    for _, url in sorted(scored, key=lambda x: -x[0]):
        if url.startswith("https://") and url not in seen:
            seen.add(url)
            out.append(url)
    return out[:4]


def wikipedia_logo(company, fetch):
    """{'url', 'page', 'license', 'title'} for the company's logo on Wikipedia / Wikimedia Commons, or None. Two API requests plus one for the file."""
    api = "https://en.wikipedia.org/w/api.php?"
    got = fetch(api + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": company, "srlimit": 1, "format": "json"}), 200_000)
    try:
        title = json_loads(got["body"])["query"]["search"][0]["title"]
        got = fetch(api + urllib.parse.urlencode({"action": "query", "titles": title, "prop": "images", "imlimit": 50, "format": "json"}), 200_000)
        pages = json_loads(got["body"])["query"]["pages"]
        files = [i["title"] for p in pages.values() for i in p.get("images", []) if "logo" in i["title"].lower() and not i["title"].lower().endswith((".ogg", ".webm"))]
        files.sort(key=lambda t: (not t.lower().endswith(".svg"), len(t)))
        if not files:
            return None
        got = fetch(api + urllib.parse.urlencode({"action": "query", "titles": files[0], "prop": "imageinfo", "iiprop": "url|extmetadata", "format": "json"}), 200_000)
        info = next(iter(json_loads(got["body"])["query"]["pages"].values()))["imageinfo"][0]
        lic = (info.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "")
        return {"url": info["url"], "page": info.get("descriptionurl", ""), "license": lic, "title": files[0]}
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None


def json_loads(data):
    return json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)


# ── fetching ─────────────────────────────────────────────────────────────────
class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses a redirect to anything but https before the next request is made."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url, limit):
    """{'status', 'body', 'type', 'url'} or None. https only (also across redirects), timeout, size limit."""
    if not url.startswith("https://"):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.build_opener(HttpsOnlyRedirect).open(req, timeout=TIMEOUT) as resp:
            if not resp.geturl().startswith("https://"):
                return None
            body = resp.read(limit + 1)
            if len(body) > limit:
                return None
            return {"status": resp.status, "body": body, "type": resp.headers.get("Content-Type", ""), "url": resp.geturl()}
    except Exception:
        return None


def website_from_row(row, override=""):
    """The company's own site: an explicit override, else the host of the row's note link unless it is a job board or ATS; '' when unknown."""
    for cand in [override] + re.findall(r"https?://[^\s·)>\]]+", row.get("note", "") or ""):
        if not cand:
            continue
        u = urllib.parse.urlparse(cand if "://" in cand else "https://" + cand)
        if u.hostname and (cand == override or not is_board_host(u.hostname)):
            return "https://%s/" % u.hostname
    return ""


# ── the record ───────────────────────────────────────────────────────────────
def build_brand(company, website, fetch, today, dirs=None):
    """(record, logo_bytes or None, logo_ext). Never raises for network or parse problems: the record lists what fell back."""
    rec = {"company": company, "website": website, "date": today, "confirmed": False, "colors": dict(PE), "fonts": {"heading": PE["heading_font"], "body": PE["body_font"], "source": "fallback"},
           "logo": None, "notes": []}
    logo_bytes, logo_ext, css_texts, html_text = None, None, [], ""
    if website:
        page = fetch(website, PAGE_MAX)
        if page and page.get("status") == 200:
            html_text = page["body"].decode("utf-8", "replace")
            for tag in LINK_CSS.findall(html_text)[:MAX_CSS_FILES]:
                h = HREF.search(tag)
                css = fetch(urllib.parse.urljoin(website, h.group(1)), CSS_MAX) if h else None
                if css and css.get("status") == 200:
                    css_texts.append(css["body"].decode("utf-8", "replace"))
            css_texts += re.findall(r"<style[^>]*>(.*?)</style>", html_text, re.S | re.I)
            pal = pick_palette(html_text, css_texts)
            if pal:
                rec["colors"].update(primary=pal["primary"], accent=pal["accent"])
                rec["colors"]["source"] = "website"
            else:
                rec["notes"].append("keine Markenfarbe gefunden: PE-Farben")
            fams = parse_fonts(css_texts + [html_text])
            rec["fonts"] = choose_fonts(fams, fetch, dirs) if fams else rec["fonts"]
            if not fams:
                rec["notes"].append("keine Schrift gefunden: PE-Schrift")
            for url in logo_candidates(html_text, page.get("url") or website):
                got = fetch(url, LOGO_MAX)
                ext = sniff_image(got["body"]) if got and got.get("status") == 200 else None
                if ext and (ext != "svg" or svg_is_safe(got["body"])):
                    logo_bytes, logo_ext = got["body"], ext
                    rec["logo"] = {"source": "website", "url": url}
                    break
        else:
            rec["notes"].append("Webseite nicht lesbar: PE-Look")
    else:
        rec["notes"].append("Webseite fehlt (im Datensatz „website“ eintragen oder --website angeben): PE-Look")
    if logo_bytes is None:
        wp = wikipedia_logo(company, fetch)
        if wp:
            got = fetch(wp["url"], LOGO_MAX)
            ext = sniff_image(got["body"]) if got and got.get("status") == 200 else None
            if ext and (ext != "svg" or svg_is_safe(got["body"])):
                logo_bytes, logo_ext = got["body"], ext
                rec["logo"] = {"source": "wikipedia", "url": wp["url"], "page": wp["page"], "license": wp["license"], "title": wp["title"]}
    if logo_bytes is None:
        rec["notes"].append("kein Logo gefunden: PDF ohne Logo (eigene Datei logo.svg/png im Rollenordner hat Vorrang)")
    return rec, logo_bytes, logo_ext


def user_logo(role_folder):
    """Path of a logo.svg / logo.png / logo.jpg you put into the role folder (also in 20 Vorbereitung), else ''."""
    for d in (str(role_folder), os.path.join(str(role_folder), "20 Vorbereitung")):
        for name in ("logo.svg", "logo.png", "logo.jpg", "Logo.svg", "Logo.png", "Logo.jpg"):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return ""


def load_brand(role_folder):
    """The saved brand record of a role folder, or None."""
    vorb = os.path.join(str(role_folder), "20 Vorbereitung")
    try:
        names = sorted(n for n in os.listdir(vorb) if n.startswith("Marke_") and n.endswith(".json"))
    except OSError:
        return None
    for n in names:
        rec = C._read_json(os.path.join(vorb, n), {})
        if isinstance(rec, dict) and isinstance(rec.get("colors"), dict):
            rec["_path"] = os.path.join(vorb, n)
            return rec
    return None


def effective_logo(role_folder, rec):
    """The logo file to print: your own file first, else the fetched one recorded in the brand record; '' if none exists."""
    mine = user_logo(role_folder)
    if mine:
        return mine
    if rec and isinstance(rec.get("logo"), dict) and rec["logo"].get("file"):
        p = os.path.join(str(role_folder), "20 Vorbereitung", rec["logo"]["file"])
        if os.path.isfile(p):
            return p
    return ""


def run_brand(uid, system, base_dir, today, website="", force=False, dry_run=False, fetch=None, locate=None, dirs=None):
    """{'status': 'written'|'current'|'skipped'|'error', 'record', 'reason'}. A record you have edited (confirmed) is never overwritten."""
    uid = C.norm_uid(uid)
    fetch = fetch or fetch_url
    if locate is None:
        from folder_utils import locate_role_folder as locate
    try:
        row = None
        with open(os.path.join(system, "pipeline.csv"), newline="", encoding="utf-8") as f:
            row = next((r for r in csv.DictReader(f) if C.norm_uid(r.get("uid")) == uid), None)
        if row is None:
            return {"status": "skipped", "reason": "uid %s nicht in pipeline.csv" % uid}
        folder, flags = locate(base_dir, uid, row.get("role") or "", row.get("folder_id") or "")
        if folder is None:
            return {"status": "error", "reason": "Rollenordner nicht gefunden: %s" % "; ".join(flags)}
        existing = load_brand(folder)
        if existing and not force:
            return {"status": "current", "record": existing}
        if existing and existing.get("confirmed") is True:
            return {"status": "skipped", "reason": "Datensatz ist bestätigt (confirmed): nicht überschrieben", "record": existing}
        company = row.get("company") or ""
        site = website or (existing or {}).get("website") or website_from_row(row)
        rec, logo, ext = build_brand(company, site, fetch, today, dirs)
        if dry_run:
            return {"status": "written", "record": rec, "file": ""}
        vorb = os.path.join(str(folder), "20 Vorbereitung")
        os.makedirs(vorb, exist_ok=True)
        if logo:
            name = "Marke_logo." + ext
            C._write_bytes_atomic(os.path.join(vorb, name), logo)
            rec["logo"]["file"] = name
        path = os.path.join(vorb, "Marke_%s.json" % re.sub(r"[^\w\-]", "_", company or uid))
        C._write_atomic(path, json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True))
        return {"status": "written", "record": rec, "file": path}
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read a target company's brand (colours, fonts, logo) into a brand record.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid")
    g.add_argument("--pinned", action="store_true")
    ap.add_argument("--website", default="")
    ap.add_argument("--today", default=None)
    ap.add_argument("--system", default=HERE)
    ap.add_argument("--base-dir", default=os.path.dirname(HERE))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    today = a.today or datetime.date.today().isoformat()
    uids = [a.uid]
    if a.pinned:
        from top10 import load
        uids = [str(u) for u in load(os.path.join(a.system, "top10.json")).get("pinned", [])]
    rc = 0
    for uid in uids:
        res = run_brand(uid, a.system, a.base_dir, today, a.website, a.force, a.dry_run)
        rec = res.get("record") or {}
        print("company_brand uid %s: %s%s" % (uid, res["status"], " · " + res["reason"] if res.get("reason") else ""))
        if rec:
            colors, fonts = rec.get("colors") or {}, rec.get("fonts") or {}
            print("  Farben %s / %s (%s) · Schrift %s (%s) · Logo %s" % (colors.get("primary", PE["primary"]), colors.get("accent", colors.get("primary", PE["accent"])),
                                                                          colors.get("source", "PE"), fonts.get("heading", PE["heading_font"]), fonts.get("source", "fallback"),
                                                                          (rec.get("logo") or {}).get("source", "keins")))
            for n in rec.get("notes", []):
                print("  Hinweis: " + n)
        if res["status"] == "error":
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
