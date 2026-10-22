#!/usr/bin/env python3
"""Inbox intake for opportunities you found yourself.

    python3 _system/intake.py --init                 # once: create _Eingang/ and its template
    python3 _system/intake.py [--dry-run]            # daily (runbook step 3c)

Drop the posting into `_Eingang/` (a .md/.txt with header lines, a printed PDF named `Firma - Rolle.pdf`, or a PDF plus a
same-named .md with the headers). For each file, exactly once: a Watchlist row (or, for a known company and role, the existing row),
the posting text in jd_cache.json, a Top-10 pin (new rows only), the folders `NNN Firma/Rolle/{10 Bewerbung, 20 Vorbereitung,
30 Verlauf}`, and the posting moved into `10 Bewerbung` (an atomic rename inside the Drive tree, never an overwrite, no delete
calls). Records come first, the move last: if the move fails the file stays in the inbox and the next run finds the row and
completes the move. Unclear files are reported and never moved. Nothing else in Drive is ever moved, renamed or deleted.
"""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import top10  # noqa: E402
from folder_utils import find_company_folder, find_role_folder  # noqa: E402
import kit_run

try:
    from discovery import detect_lane
except Exception:                                                            # keep intake usable if discovery cannot import
    def detect_lane(title, description=""):
        return "Other"

INBOX = "_Eingang"
ALLOWED = (".md", ".txt", ".pdf", ".html")
SUBFOLDERS = ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf")
JD_MAX = 20000
NOTE_MAX = 300
HEADER_KEYS = {"bestätigt": "confirmed", "bestaetigt": "confirmed", "confirmed": "confirmed", "firma": "company", "company": "company", "rolle": "role", "role": "role", "link": "link",
               "ort": "location", "location": "location", "notiz": "note", "note": "note"}
CLOSED_ROLE = re.compile(r"\((rejected|inactive)\)\s*$", re.I)      # status suffix your role folders carry when a role is over (as in intel_index)
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HEADER_RE = re.compile(r"^\s*(Firma|Company|Rolle|Role|Link|Ort|Location|Notiz|Note|Bestätigt|Bestaetigt|Confirmed)\s*:\s*(.*?)\s*$", re.I)
ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
WAIT_EXT = (".crdownload", ".download", ".part", ".partial", ".tmp", ".opdownload")
NAME_MAX_BYTES = 200                                                          # macOS/Drive allow 255; leave room for ' (2)' and the like
JOB_WORDS = re.compile(r"\b(director|manager|head|lead|leiter|leiterin|leitung|engineer|architect|architekt|architektin|consultant|berater|beraterin|"
                       r"analyst|officer|principal|chief|cio|cto|cdo|cfo|ceo|vp|specialist|owner|sr|jr|senior|junior|scientist|master|expert|referent|werkstudent|"
                       r"geschäftsführer)\b|(leiter|leiterin|leitung|manager|managerin|berater|beraterin|entwickler|entwicklerin|ingenieur|ingenieurin|"
                       r"architekt|architektin|spezialist|spezialistin)\b|\([dmwfx]/[dmwfx](/[dmwfx])?\)|\(all genders\)", re.I)
SITE_WORDS = re.compile(r"\b(careers?|jobs?|karriere|stellenangebote?|stellenmarkt|jobportal|indeed|stepstone|xing|linkedin|glassdoor|softgarden|workday|"
                        r"greenhouse|lever|smartrecruiters|personio|recruitee|taleo|successfactors)\b", re.I)
SEP = r"\s+[-–—]\s+"
YES = {"ja", "j", "yes", "y", "true", "1"}
CONFIRM_RE = re.compile(r"^[ \t]*(?:Bestätigt|Bestaetigt|Confirmed)[ \t]*:[ \t]*(.*?)[ \t]*$", re.I | re.M)      # one line only: the value cannot sit on the next
OWN_MARKER = "# Bitte prüfen: Firma"
AUTO_MARK = "# Automatisch geprüft"
MAX_KEY_LEN = 60
LEGAL = re.compile(r"\b(gmbh|ag|se|kg|kgaa|mbh|co|ltd|inc|llc|ev|gruppe|group)\b", re.I)
TEMPLATE = """# So legst du eine Ausschreibung ab

Lege die Datei hier in `_Eingang/` ab. Der nächste Lauf legt Zeile, Ordner und Kopie an, pinnt sie in die Top 10 und verschiebt
die Datei nach `10 Bewerbung` der Rolle. Was unklar ist, bleibt hier liegen und steht auf „Heute“ unter „Im Eingang“.

**Firma und Rolle werden nie aus dem Dateinamen übernommen** (Browser benennen gedruckte Seiten nach dem Seitentitel). Sie stammen nur aus
Kopfzeilen, die du selbst schreibst, oder aus einer Begleitdatei, die du mit „Bestätigt: ja“ freigibst.

1. **Gedruckte Ausschreibung als PDF** (oder HTML): einfach ablegen. Beim nächsten Lauf erscheint daneben `<Name>.md` mit einem Vorschlag
   und `Bestätigt: nein`. Firma, Rolle, Ort prüfen (Vorsicht: vertauscht?), `Bestätigt: ja` setzen, speichern. Danach wird alles angelegt.
   Kurzform ohne Editor: `python3 _system/intake.py --confirm "Teil des Namens"` zeigt den Vorschlag, fragt nach und läuft dann sofort weiter.
2. **Textdatei** (`.md` oder `.txt`) mit deinen Kopfzeilen, danach der eingefügte Text der Ausschreibung:

       Firma: Beispiel AG
       Rolle: Head of Data & AI (m/w/d)
       Link: https://...
       Ort: Hamburg
       Notiz: von Herrn X empfohlen

       (hier der Text der Ausschreibung)

3. **PDF plus eigene Begleitdatei** gleichen Namens (`ausschreibung.pdf` + `ausschreibung.md`) mit den Kopfzeilen oben.

Nur ein ausdrückliches `Bestätigt: ja` gilt als Freigabe; leer, „nein“ oder eine gelöschte Zeile bedeuten: noch nicht.
Dateien, die mit `_` oder `.` beginnen (wie diese), werden ignoriert; Dateien, die gerade erst geschrieben werden, „warten“ bis zum nächsten Lauf.
"""


class Unclear(Exception):
    def __init__(self, reason, offer_sidecar=False, edit=None):
        super().__init__(reason)
        self.offer_sidecar = offer_sidecar
        self.edit = edit                                                          # the file the user should open to fix this


# ---- parsing ------------------------------------------------------------------------------------
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_headers(text):
    """(fields, body): leading `Key: value` lines are headers; the rest is the posting text."""
    lines = text.splitlines()
    fields, i = {}, 0
    while i < len(lines) and i < 15:
        if not lines[i].strip() and not fields:
            i += 1
            continue
        m = HEADER_RE.match(lines[i])
        if not m:
            break
        if m.group(2):
            fields.setdefault(HEADER_KEYS[m.group(1).lower()], m.group(2))
        i += 1
    return fields, "\n".join(lines[i:]).strip()


def name_pattern(stem):
    """'Firma - Rolle' (hyphen, en dash or em dash with spaces) -> (company, role), else None."""
    parts = re.split(r"\s+[-–—]\s+", stem.strip(), maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 and parts[0].strip() and parts[1].strip() else None


def clean(text):
    """Zero-width characters out, no-break spaces to spaces, runs of blanks collapsed."""
    return re.sub(r"[ \t]+", " ", ZERO_WIDTH.sub("", str(text)).replace("\u00a0", " ")).strip()


def nfc(text):
    """macOS file names are often decomposed (u + combining diaeresis); rows are composed: compare and store composed."""
    return unicodedata.normalize("NFC", str(text))


def looks_like_page_title(stem):
    """Browser 'Save as PDF' names a file '<page title> - <site>': title first, site words, or _ and | in it. Never parsed as Firma - Rolle."""
    s = nfc(clean(stem))
    parts = re.split(SEP, s)
    if len(parts) > 2 or "|" in s or "_" in s:
        return True
    return len(parts) == 2 and bool(JOB_WORDS.search(parts[0]) or SITE_WORDS.search(parts[1]))


def suggest_from_title(stem):
    """Best-effort {company, role, location} from a page-title file name; {} unless a job-title part is found. A proposal, never a decision."""
    parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", nfc(clean(stem))) if p.strip()]
    role = next((p for p in parts if JOB_WORDS.search(p)), "")
    if not role:
        return {}
    company = location = ""
    for chunk in (p for p in parts if p != role):
        pieces = [c.strip() for c in re.split(r"\s+_\s+|_|\s*\|\s*", chunk) if c.strip()]
        site = [c for c in pieces if SITE_WORDS.search(c)]
        others = [c for c in pieces if c not in site]
        if site:
            company = company or SITE_WORDS.sub("", site[0]).strip(" ,-–—")
            location = location or (others[0] if others else "")
        elif others:
            company = company or others[0]
            location = location or (others[1] if len(others) > 1 else "")
    return {k: v for k, v in (("company", company), ("role", role), ("location", location)) if v}


def is_confirmed(text):
    """Fail-closed: a `Bestätigt:` line must say an explicit yes; an empty value, 'nein', 'nein.' and the like are not a yes.
    A sidecar written by intake that lost its `Bestätigt` line is not confirmed either; a file you wrote yourself without the key is."""
    found = CONFIRM_RE.findall("\n".join(text.splitlines()[:60]))
    if found:
        return clean(found[-1]).lower() in YES
    return OWN_MARKER not in text


def propose(stem):
    """{company, role[, location]} proposed for the sidecar. A proposal only: it is never used without the user's explicit yes."""
    stem = nfc(clean(stem))
    pattern = name_pattern(stem)
    if pattern:
        a, b = pattern
        if LEGAL.search(a) and not LEGAL.search(b):
            return {"company": a, "role": b}
        if LEGAL.search(b) and not LEGAL.search(a):
            return {"company": b, "role": a}
    if looks_like_page_title(stem):
        return suggest_from_title(stem)
    return {"company": pattern[0], "role": pattern[1]} if pattern else {}


RESTORE = ((re.compile(r"\b([mwfdx])_([mwfdx])_([mwfdx])\b", re.I), r"\1/\2/\3"), (re.compile(r"(?<=[A-Za-zäöüÄÖÜß])_(in|innen)\b"), r"*\1"))
AT_RE = re.compile(r"^(.+?)\s+(?:at|bei|@)\s+(.+)$", re.I)


def restore_chars(text):
    """Browsers replace '/' and '*' in file names by '_': '(m_w_d)' was '(m/w/d)', 'Manager_in' was 'Manager*in'."""
    for pat, sub in RESTORE:
        text = pat.sub(sub, text)
    return text


LOCATIONS = {"berlin", "hamburg", "münchen", "muenchen", "munich", "köln", "koeln", "frankfurt", "stuttgart", "düsseldorf", "duesseldorf", "leipzig", "dresden", "hannover",
             "nürnberg", "nuernberg", "bremen", "essen", "dortmund", "karlsruhe", "mannheim", "wiesbaden", "bonn", "kiel", "lübeck", "luebeck", "toronto", "vienna", "wien",
             "zürich", "zuerich", "zurich", "remote", "hybrid", "homeoffice", "home office", "deutschland", "germany", "österreich", "schweiz", "europe", "emea", "dach"}
AGENCIES = {"Personalhaus", "randstad", "hays", "robert half", "adecco", "gulp", "freelancermap", "manpower", "kelly", "experis", "page personnel", "brunel", "akkodis", "amoria bond",
            "spencer stuart", "korn ferry", "heidrick", "russell reynolds", "egon zehnder", "personio", "softgarden", "kienbaum"}
GENERIC_COMPANY = {"data", "bank", "group", "gruppe", "it", "ai", "digital", "consulting", "technology", "technologie", "management", "solutions", "services", "team", "unternehmen", "company"}
ORG_WORDS = re.compile(r"\b(universität|universitaet|hochschule|klinikum|universitätsklinikum|stadt|landkreis|kreis|bundes\w*|verband|institut|stiftung|versicherung\w*|bank|sparkasse|kasse|amt|ministerium|gemeinde)\b", re.I)
MARKER = re.compile(r"^\s*(ähnliche|similar|weitere stellen|andere stellen|you may also|empfohlene|related jobs)", re.I | re.M)
URLISH = re.compile(r"https?://\S+|www\.\S+|\S+\.(?:de|com|org|net|io|eu|example)\b\S*", re.I)


def company_ok(company):
    """A company name that is not a place, an agency, a generic word or a person's name."""
    norm = norm_company(company)
    if len(norm) < 4 or norm in LOCATIONS or norm in AGENCIES or norm in GENERIC_COMPANY or norm.strip(". ") != norm:
        return False
    toks = norm.split()
    if all(t in LOCATIONS or t in GENERIC_COMPANY for t in toks) or re.search(r"\.[a-z]{2,3}\b", company.lower()):
        return False
    if len(toks) == 2 and all(t[:1].isalpha() for t in toks) and not LEGAL.search(company) and not ORG_WORDS.search(company) and all(c.isupper() for c in (w[:1] for w in company.split()[:2])):
        return False                                                            # 'Max Mustermann': a person, not an employer
    return True


def parse_title(stem):
    """{role, company, shape} from a page-title file name. shape: 'at' (Role at Company), 'legal' (company with a legal form), 'plain' (two parts, last is the company).
    {} when unsure. A proposal only; automatic filing additionally needs the text (is_sure) and a shape that proves enough."""
    s = restore_chars(nfc(clean(stem)))
    m = AT_RE.match(s)
    if m and JOB_WORDS.search(m.group(1)) and not JOB_WORDS.search(m.group(2)) and not SITE_WORDS.search(m.group(2)):
        company = m.group(2).strip()
        return {"role": m.group(1).strip(), "company": company, "shape": "at" if not re.search(r"\s[-|–—_]\s|,", company) else "mixed"}
    parts = [p.strip() for p in re.split(r"\s+[|_–—-]\s+", s) if p.strip()]
    if len(parts) < 2 or any(SITE_WORDS.search(p) for p in parts):
        return {}                                                                 # a site name in the title: the older, more careful rules decide
    ci = next((i for i in range(len(parts) - 1, -1, -1) if LEGAL.search(parts[i])), None)
    shape = "legal"
    if ci is None and not JOB_WORDS.search(parts[-1]):
        ci, shape = len(parts) - 1, "plain" if len(parts) == 2 else "mixed"        # without a legal form only the last part can be the company
    if ci is None:
        return {}
    role = " ".join(parts[:ci]) if ci > 0 else " ".join(parts[1:])
    if not role or not JOB_WORDS.search(role):
        return {}
    if shape == "legal" and len(parts) > 3:
        shape = "mixed"
    return {"role": role, "company": parts[ci], "shape": shape}


HEADLINE_SKIP = re.compile(r"^\s*\d{1,2}[/.]\d{1,2}[/.]\d{2,4},?\s|https?://", re.I)


def _tokens(text, n=4):
    return [t for t in re.findall(r"[\wäöüÄÖÜß*-]+", text.lower()) if len(t) >= n and t not in ("m/w/d",)]


def _own_text(text):
    """The posting itself: cut at 'similar jobs' style lists, URLs and 'Bewerbung bei X' phrases out."""
    m = MARKER.search(text or "")
    cut = (text or "")[: m.start()] if m else (text or "")
    return re.sub(r"(bewerbung|bewerben|apply)\s+(bei|at|for)\s+\S+(\s+\S+)?", " ", URLISH.sub(" ", cut), flags=re.I)


def refine_role(role, text):
    """The posting's own headline for the role when it contains all words of the name's role (e.g. with the department), else the name's role.
    A headline with another company, a separator or from a list of other jobs is never taken."""
    toks = _tokens(re.sub(r"\([^)]*\)", " ", role))
    if not toks:
        return role
    for line in [l.strip() for l in _own_text(text).splitlines() if l.strip()][:60]:
        if HEADLINE_SKIP.match(line) or len(line) > min(140, len(role) + 60) or re.search(r"\s[-|–—]\s", line) or (LEGAL.search(line) and not LEGAL.search(role)):
            continue
        low = line.lower()
        if all(t in low for t in toks) and JOB_WORDS.search(line) and low.startswith(role.split()[0].lower()):
            return clean(line)
    return role


def _whole(word, flat):
    return bool(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", flat))


def is_sure(company, role, text, shape="legal"):
    """Company and role are both proven by the posting: right title shape, a company that is no place/agency/person/generic word, named at least twice in the
    posting itself (not in URLs, 'Bewerbung bei X' or a list of other jobs), the role's words all present. Anything less waits for you."""
    if not (company and role) or len(company) > 80 or len(role) > 140 or not company_ok(company):
        return False
    if JOB_WORDS.search(company) or SITE_WORDS.search(company) or not JOB_WORDS.search(role) or SITE_WORDS.search(role):
        return False
    if norm_company(company) == norm_company(role) or (LEGAL.search(role) and not LEGAL.search(company)):
        return False
    if shape == "plain" and not (ORG_WORDS.search(company) and len(company.split()) >= 2):
        return False
    if shape not in ("at", "legal", "plain"):
        return False
    flat = re.sub(r"\s+", " ", _own_text(text).lower())
    words = [w for w in norm_company(company).split() if len(w) >= 2]
    phrase = " ".join(words)
    if not words or len(re.findall(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", flat)) < 2:
        return False
    return all(_whole(t, flat) for t in _tokens(re.sub(r"\([^)]*\)", " ", role)))


def derive_proposal(stem, text):
    """{company, role, location, auto}: from the file name and the posting text. 'auto' means both are proven (see is_sure); only a title shape parse_title
    is sure about can be automatic, never the older fallback rules."""
    parsed = parse_title(stem)
    prop = parsed or {k: v for k, v in propose(stem).items() if k in ("company", "role", "location")}
    company, role = restore_chars(prop.get("company", "")), restore_chars(prop.get("role", ""))
    role = refine_role(role, text or "") if role else role
    return {"company": company, "role": role, "location": prop.get("location", ""),
            "auto": bool(parsed and company and role and is_sure(company, role, text or "", parsed.get("shape", "")))}


def norm_company(name):
    s = re.sub(r"\(.*?\)", " ", nfc(name).lower())
    s = LEGAL.sub(" ", s)
    return re.sub(r"[\W_]+", " ", s).strip()


def norm_role(name):
    return re.sub(r"[\W_]+", " ", re.sub(r"\(.*?\)", " ", nfc(name).lower())).strip()


def extract_text(path):
    low = path.lower()
    try:
        if low.endswith((".md", ".txt")):
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        if low.endswith(".html"):
            with open(path, encoding="utf-8", errors="replace") as f:
                raw = f.read()
            return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)))
        if low.endswith(".pdf") and shutil.which("pdftotext"):
            r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=60)
            return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _key(name):
    return nfc(name).lower()


def _sibling(path, ext):
    """A file next to `path` with the same stem (case- and Unicode-form-insensitive) and the given extension, or None."""
    stem = _key(os.path.splitext(os.path.basename(path))[0])
    try:
        for n in os.listdir(os.path.dirname(path)):
            s, e = os.path.splitext(n)
            if _key(s) == stem and e.lower() == ext:
                return os.path.join(os.path.dirname(path), n)
    except OSError:
        pass
    return None


def read_posting(path, extractor):
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext == ".gdoc":
        raise Unclear("Google-Docs-Verknüpfung (.gdoc): Text nicht lesbar; als PDF oder .md ablegen")
    if ext not in ALLOWED:
        raise Unclear("Dateityp nicht unterstützt (%s); als PDF oder .md ablegen" % (ext or "ohne Endung"))
    sidecar = None
    text = (extract_text(path) if ext in (".md", ".txt") else extractor(path)) or ""      # only PDF/HTML need the injectable extractor
    if ext in (".md", ".txt"):
        if not is_confirmed(text):
            raise Unclear("noch nicht bestätigt: Firma/Rolle prüfen und „Bestätigt: ja“ setzen", edit=name)
        fields, body = parse_headers(text)
    else:
        fields, body = {}, text
        side = _sibling(path, ".md")
        if side and not (ext == ".html" and _sibling(path, ".pdf")):                      # with a PDF beside it, the sidecar is the PDF's
            side_text = extract_text(side) or ""
            if not is_confirmed(side_text):
                raise Unclear("Begleitdatei noch nicht bestätigt: Firma/Rolle prüfen und „Bestätigt: ja“ setzen", edit=os.path.basename(side))
            fields, _ = parse_headers(side_text)
            sidecar = side
    fields = {k: nfc(clean(v)) for k, v in fields.items()}
    if any(CTRL_RE.search(v) for v in fields.values()):
        raise Unclear("Steuerzeichen in Kopfzeile oder Dateiname: bitte bereinigen")
    if not (fields.get("company") and fields.get("role")):                                # a file name alone is never enough
        offer = ext in (".pdf", ".html") and _sibling(path, ".md") is None and not (ext == ".html" and _sibling(path, ".pdf"))
        hint = " Der Dateiname sieht wie ein Browser-Seitentitel aus." if looks_like_page_title(stem) else ""
        raise Unclear("Firma/Rolle fehlt: Kopfzeilen „Firma:“/„Rolle:“ oder eine bestätigte Begleitdatei (<Name>.md) verwenden." + hint,
                      offer_sidecar=offer, edit=os.path.basename(sidecar) if sidecar else (name if ext in (".md", ".txt") else None))
    if ext in (".md", ".txt") and not body.strip():
        raise Unclear("Ausschreibungstext fehlt: nach den Kopfzeilen den Text einfügen")
    return {"company": fields["company"], "role": fields["role"], "link": fields.get("link", ""), "location": fields.get("location", ""),
            "note": fields.get("note", ""), "text": body[:JD_MAX], "text_missing": not body.strip(), "sidecar": sidecar,
            "auto": bool(sidecar and AUTO_MARK in (extract_text(sidecar) or ""))}


def write_sidecar(path, extractor, proposal=None):
    """Ready-to-fill <stem>.md beside an unclear PDF/HTML: proposal, 'Bestätigt: nein', start of the text as help. Never overwrites.
    A proposal proven by the text (proposal['auto']) is written already confirmed, with a note that says so."""
    stem = os.path.splitext(os.path.basename(path))[0]
    side = os.path.join(os.path.dirname(path), stem + ".md")
    text = extractor(path) or ""
    sug = proposal if proposal is not None else derive_proposal(stem, text)
    head = [l.strip() for l in text.splitlines() if l.strip()][:6]
    if sug.get("auto"):
        body = ("Firma: %s\nRolle: %s\nOrt: %s\nLink:\nNotiz: automatisch angelegt (Firma und Rolle stehen im Text)\nBestätigt: ja\n\n"
                "# Automatisch geprüft: Firma und Rolle stehen im Text der Ausschreibung. Bitte auf Heute kontrollieren; falsch? Zeile in pipeline.csv und Ordner korrigieren.\n"
                "# Textanfang der Datei (nur zur Orientierung):\n%s\n") % (sug["company"], sug["role"], sug.get("location", ""), "\n".join("# " + l for l in head))
    else:
        body = ("Firma: %s\nRolle: %s\nOrt: %s\nLink:\nNotiz:\nBestätigt: nein\n\n"
                "# Bitte prüfen: Firma, Rolle und Ort korrigieren (vertauscht?), dann oben „Bestätigt: ja“ setzen und speichern.\n"
                "# Der nächste Lauf legt den Fund an und verschiebt PDF und diese Datei nach 10 Bewerbung.\n"
                "# Textanfang der Datei (nur zur Orientierung):\n%s\n") % (sug.get("company", ""), sug.get("role", ""), sug.get("location", ""),
                                                                           "\n".join("# " + l for l in head))
    with open(side, "x", encoding="utf-8") as f:                                         # 'x': an existing file is never touched
        f.write(body)
    return os.path.basename(side)


# ---- files and records --------------------------------------------------------------------------
def sanitize(name, limit=60):
    s = re.sub(r'[\\/:*?"<>|]', "-", clean(name))
    s = re.sub(r"\.{2,}", ".", re.sub(r"\s+", " ", s)).strip(" .")
    if len(s) > limit:
        s = (s[:limit].rsplit(" ", 1)[0] if " " in s[:limit] else s[:limit]).strip(" .")
    return s or "Unbenannt"


def _dirs(path):
    try:
        return sorted(e for e in os.listdir(path) if not e.startswith(".") and os.path.isdir(os.path.join(path, e)))
    except OSError:
        return []


def read_rows(pipeline):
    with open(pipeline, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_existing(rows, company, role):
    """An active row of the same company (legal form ignored) with the same role, else one whose role words contain the other's
    (whole words, at least two). Closed rows never match: a new posting for a role that was closed is a new find."""
    nc, nr = norm_company(company), norm_role(role)
    if not nc:
        return None
    cands = [r for r in rows if r.get("stage") != "Closed" and norm_company(r.get("company", "")) == nc]
    for r in cands:
        if norm_role(r.get("role", "")) == nr:
            return r
    want = set(nr.split())
    for r in cands:
        have = set(norm_role(r.get("role", "")).split())
        small, big = (want, have) if len(want) <= len(have) else (have, want)
        if len(small) >= 2 and small <= big:
            return r
    return None


def next_uid(rows, root):
    nums = [int(str(r.get("uid", "")).strip()) for r in rows if str(r.get("uid", "")).strip().isdigit()]
    for d in _dirs(root):
        m = re.match(r"(\d{1,4})\s", d)
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def safe_name(name):
    """A file name longer than NAME_MAX_BYTES is cut (at a character boundary) and gets a short hash, the extension is kept."""
    if len(os.fsencode(name)) <= NAME_MAX_BYTES:
        return name
    stem, ext = os.path.splitext(name)
    tag = hashlib.sha1(name.encode("utf-8", "surrogateescape")).hexdigest()[:8]
    room = NAME_MAX_BYTES - len(os.fsencode(ext)) - len(tag) - 1 - 6              # 6 bytes spare for ' (99)'
    cut = os.fsencode(stem)[:room].decode("utf-8", "ignore").rstrip()
    return "%s-%s%s" % (cut, tag, ext)


def move_unique(src, dstdir):
    """Move src into dstdir with one atomic rename; a name clash gets ' (2)', ' (3)' ... and nothing is ever overwritten."""
    os.makedirs(dstdir, exist_ok=True)
    base = safe_name(os.path.basename(src))
    stem, ext = os.path.splitext(base)
    dst, n = os.path.join(dstdir, base), 1
    while os.path.exists(dst):
        n += 1
        dst = os.path.join(dstdir, "%s (%d)%s" % (stem, n, ext))
    os.rename(src, dst)
    return dst


def append_row(pipeline, row):
    with open(pipeline, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    with open(pipeline, "rb") as f:
        f.seek(-1, os.SEEK_END)
        last = f.read(1)
    with open(pipeline, "a", newline="", encoding="utf-8") as f:
        if last != b"\n":
            f.write("\n")
        csv.DictWriter(f, fieldnames=header, extrasaction="ignore", lineterminator="\n").writerow(row)


def append_folder_line(path, uid, folder):
    if not os.path.exists(path):
        return
    with open(path, "rb") as f:
        data = f.read()
    with open(path, "a", encoding="utf-8") as f:
        f.write(("" if not data or data.endswith(b"\n") else "\n") + "%d\t%s\t\n" % (uid, folder))


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def read_json_strict(path, default):
    """Missing file: default. Unparseable or wrong-typed file: renamed aside (never overwritten), default. Temporarily unreadable: raises."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return default
    except ValueError:
        data = None
    if isinstance(data, type(default)):
        return data
    stamp, n = datetime.now().strftime("%Y%m%d%H%M%S"), 0
    backup = "%s.corrupt-%s" % (path, stamp)
    while os.path.exists(backup):
        n += 1
        backup = "%s.corrupt-%s-%d" % (path, stamp, n)
    os.rename(path, backup)
    return default


def employer_dir(root, uid, company):
    found = [d for d in _dirs(root) if re.match(r"^0*%d\s" % uid, d)]
    return found[0] if found else "%d %s" % (uid, sanitize(company))


def role_dir_name(root, employer, role):
    nr = norm_role(role)
    for d in _dirs(os.path.join(root, employer)):
        if not re.match(r"^(10|20|30)(\s|$)", d) and nr and norm_role(d) and (norm_role(d) == nr or nr in norm_role(d) or norm_role(d) in nr):
            return d
    return sanitize(role)


# ---- one file -----------------------------------------------------------------------------------
def process_file(path, ctx):
    """Returns (kind, entry) with kind in already/unclear/existing/new. Raises on failures (caller reports them)."""
    root, system, today = ctx["root"], ctx["system"], ctx["today"]
    digest = sha256(path)
    name = os.path.basename(path)
    known = ctx["state"]["files"].get(digest)
    if known:
        return "already", {"file": name, "uid": known["uid"]}
    try:
        p = read_posting(path, ctx["extractor"])
    except Unclear as e:
        entry = {"file": name, "reason": str(e)}
        if e.edit:
            entry["edit"] = e.edit
        prop = None
        if e.offer_sidecar and not ctx["dry_run"]:
            try:
                prop = derive_proposal(os.path.splitext(name)[0], ctx["extractor"](path) or "")
                entry["sidecar"] = entry["edit"] = write_sidecar(path, ctx["extractor"], prop)
                entry["reason"] += " Vorschlag in %s geschrieben: prüfen und „Bestätigt: ja“ setzen." % entry["sidecar"]
            except OSError:
                prop = None
        if prop and prop["auto"] and not ctx.get("auto_retry"):
            ctx["auto_retry"] = True                                                  # the sidecar is confirmed now: file the find in this run; a failure is a real failure
            try:
                return process_file(path, ctx)
            finally:
                ctx["auto_retry"] = False
        return "unclear", entry
    pipeline = os.path.join(system, "pipeline.csv")
    existing = find_existing(read_rows(pipeline), p["company"], p["role"])
    uid = int(existing["uid"]) if existing else next_uid(read_rows(pipeline), root)
    flags = []
    if existing:                                                               # resolve the real folders; never guess a duplicate
        company_folder, cflags = find_company_folder(root, uid, existing.get("folder_id", ""))
        if company_folder is None and cflags:
            raise RuntimeError("Ordner-Dublette für uid %d, bitte von Hand klären: %s" % (uid, "; ".join(cflags)))
        employer = company_folder.name if company_folder else "%d %s" % (uid, sanitize(existing["company"]))
        role, flags = sanitize(p["role"]), list(cflags)
        if company_folder:
            rf, rflags = find_role_folder(company_folder, p["role"])
            flags += rflags
            if rf is not None and not CLOSED_ROLE.search(rf.name):             # a rejected/inactive role folder is never a target
                role = rf.name
    else:
        employer, role = "%d %s" % (uid, sanitize(p["company"])), sanitize(p["role"])
    target = os.path.join(root, employer, role, "10 Bewerbung")
    entry = {"uid": uid, "company": p["company"], "role": p["role"], "file": name, "archived": os.path.join(employer, role, "10 Bewerbung", name),
             "text_missing": p["text_missing"]}
    if flags:
        entry["flags"] = flags
    if p.get("auto"):
        entry["auto"] = True
    own = bool(existing) and str(existing.get("note", "")).startswith("Eigener Fund")
    if ctx["dry_run"]:
        return ("existing" if existing else "new"), entry

    cache_path = os.path.join(system, "jd_cache.json")
    healed = []
    if not existing:                                                            # records first: nothing here needs an undo
        cache = read_json_strict(cache_path, {})                                # read before the first write: an unreadable cache fails cleanly
        note = "Eigener Fund (Eingang %s)" % today + (" — " + p["note"] if p["note"] else "") + (" · " + p["link"] if p["link"] else "")
        append_row(pipeline, {"uid": uid, "company": p["company"], "role": p["role"], "lane": detect_lane(p["role"], p["text"][:2000]),
                              "stage": "Watchlist", "last_event": today, "days_idle": "0", "score": "0", "boost": "0",
                              "location": p["location"], "note": note[:NOTE_MAX]})
        append_folder_line(os.path.join(system, "folders.tsv"), uid, employer)
        if p["text"]:
            cache[str(uid)] = p["text"]
        else:
            cache.pop(str(uid), None)                                            # never leave another posting's text under this uid
        write_json(cache_path, cache)
        top10.pin(os.path.join(system, "top10.json"), uid)
    elif own:                                                                   # a find whose earlier run stopped half-way: complete it
        tsv = os.path.join(system, "folders.tsv")
        if os.path.exists(tsv) and not re.search(r"^0*%d\t" % uid, open(tsv, encoding="utf-8").read(), re.M):
            append_folder_line(tsv, uid, employer)
            healed.append("folders.tsv")
        cache = read_json_strict(cache_path, {})
        if p["text"] and cache.get(str(uid)) != p["text"]:
            cache[str(uid)] = p["text"]
            write_json(cache_path, cache)
            healed.append("Text")
        elif not p["text"] and str(uid) in cache:
            cache.pop(str(uid))
            write_json(cache_path, cache)
            healed.append("Text")
        pins = top10.load(os.path.join(system, "top10.json"))
        if uid not in pins["pinned"] and uid not in pins["excluded"]:
            top10.pin(os.path.join(system, "top10.json"), uid)
            healed.append("Pin")
    for sub in SUBFOLDERS if (not existing or own) else SUBFOLDERS[:1]:
        d = os.path.join(root, employer, role, sub)
        if own and existing and not os.path.isdir(d):
            healed.append(sub)
        os.makedirs(d, exist_ok=True)
    main = move_unique(path, target)                                              # last step; a failure leaves the file in the inbox
    entry["archived"] = os.path.relpath(main, root)
    if p["sidecar"]:                                                            # after the main file, so the headers survive a failed move
        try:
            move_unique(p["sidecar"], target)
        except OSError as e:
            entry["warning"] = "Begleitdatei blieb im Eingang: %s" % e
    ctx["state"]["files"][digest] = {"uid": uid, "company": p["company"], "role": p["role"], "date": today, "archived": entry["archived"]}
    write_json(os.path.join(system, "intake_state.json"), ctx["state"])
    if healed:
        entry["healed"] = healed
        return "healed", entry
    return ("existing" if existing else "new"), entry


# ---- run ----------------------------------------------------------------------------------------
def init(root):
    inbox = os.path.join(root, INBOX)
    os.makedirs(inbox, exist_ok=True)
    tpl = os.path.join(inbox, "_VORLAGE.md")
    if not os.path.exists(tpl):
        with open(tpl, "w", encoding="utf-8") as f:
            f.write(TEMPLATE)


def scan(inbox):
    try:
        names = sorted(os.listdir(inbox))
    except OSError:
        return []
    files = [n for n in names if not n.startswith((".", "_", "~$")) and os.path.isfile(os.path.join(inbox, n))]
    pairs = {(_key(os.path.splitext(n)[0]), os.path.splitext(n)[1].lower()) for n in files}
    out = []
    for n in files:
        stem, ext = os.path.splitext(n)
        if ext.lower() == ".md" and ((_key(stem), ".pdf") in pairs or (_key(stem), ".html") in pairs):
            continue                                                            # a sidecar belongs to its PDF/HTML
        out.append(n)
    return out


def run(root, system_dir, today, dry_run=False, extractor=None, min_age=0):
    ctx = {"root": root, "system": system_dir, "today": today, "dry_run": dry_run, "extractor": extractor or extract_text,
           "state": read_json_strict(os.path.join(system_dir, "intake_state.json"), {})}
    ctx["state"] = {"files": ctx["state"].get("files", {}) if isinstance(ctx["state"].get("files", {}), dict) else {}}
    report = {"generated": datetime.now().isoformat(timespec="seconds"), "dry_run": dry_run, "new": [], "existing": [], "already": [],
              "healed": [], "waiting": [], "unclear": [], "failed": []}
    inbox = os.path.join(root, INBOX)
    for name in scan(inbox):
        path = os.path.join(inbox, name)
        try:
            ext = os.path.splitext(name)[1].lower()
            if ext in WAIT_EXT:
                report["waiting"].append({"file": name, "reason": "Download noch nicht abgeschlossen (%s)" % ext})
                continue
            if os.path.islink(path):
                report["unclear"].append({"file": name, "reason": "Verknüpfung (Symlink) wird ignoriert: bitte die echte Datei ablegen"})
                continue
            if min_age and 0 <= time.time() - os.path.getmtime(path) < min_age:                 # a future mtime is bad metadata, not a reason to wait
                report["waiting"].append({"file": name, "reason": "wird noch geschrieben oder synchronisiert (jünger als %d s)" % min_age})
                continue
            if os.path.getsize(path) == 0:
                report["unclear"].append({"file": name, "reason": "Datei ist leer (evtl. noch nicht synchronisiert)"})
                continue
            kind, entry = process_file(path, ctx)
        except Exception as e:                                                  # one bad file never stops the others
            report["failed"].append({"file": name, "error": str(e)})
            continue
        report[kind].append(entry)
    if not dry_run:
        write_json(os.path.join(system_dir, "intake_report.json"), report)
    return report


def _interactive():
    return sys.stdin.isatty()


def _is_proposal(text):
    """Ours to confirm: written by intake, or carrying a `Bestätigt` line in its first 60 lines (the range is_confirmed reads)."""
    return OWN_MARKER in text or any(CONFIRM_RE.match(l) for l in text.splitlines()[:60])


def find_sidecars(inbox, query):
    """Proposal files whose name matches: the whole name (exact), else a fragment of at least 3 characters at the start of a word,
    which must match exactly one file. Case, Unicode form and blanks do not matter. Files you wrote yourself never match."""
    q = query.strip()
    if q.lower().endswith((".md", ".pdf", ".html", ".txt")):
        q = os.path.splitext(q)[0]
    q = _key(clean(q))
    partial = []
    try:
        names = sorted(os.listdir(inbox))
    except OSError:
        return []
    for n in names:
        path = os.path.join(inbox, n)
        if n.startswith((".", "_", "~$")) or not n.lower().endswith(".md") or not os.path.isfile(path):
            continue
        if not _is_proposal(extract_text(path) or ""):
            continue
        k = _key(clean(os.path.splitext(n)[0]))
        if k == q:
            return [path]
        if len(q) >= 3 and re.search(r"(?<!\w)" + re.escape(q), k):
            partial.append(path)
    return partial


def confirm_sidecar(path, dry_run=False):
    """Set `Bestätigt: ja` in a proposal file, byte-exact (line endings kept), in place and atomically. Only the confirmation line in the
    first 60 lines is touched, Firma and Rolle must be filled in, and the edited text is verified before anything is written."""
    name = os.path.basename(path)
    if os.path.islink(path):
        raise ValueError("%s ist eine Verknüpfung (Symlink): bitte die echte Datei bearbeiten" % name)
    if not dry_run and not os.access(path, os.W_OK):
        raise ValueError("%s ist schreibgeschützt" % name)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("%s ist nicht UTF-8: bitte als UTF-8 speichern; nichts geändert" % name)
    if text.startswith("\ufeff"):
        raise ValueError("%s beginnt mit einer BOM-Markierung: bitte ohne BOM als UTF-8 speichern" % name)
    fields, _ = parse_headers(text)
    fields = {k: nfc(clean(v)) for k, v in fields.items()}
    if not (fields.get("company") and fields.get("role")):
        raise ValueError("Firma/Rolle fehlen in %s: bitte ausfüllen (Kopfzeilen oben am Stück), dann bestätigen" % name)
    what = "%s → Firma %s · Rolle %s%s" % (name, fields["company"], fields["role"], " · Ort %s" % fields["location"] if fields.get("location") else "")
    if any(CONFIRM_RE.match(l) for l in text.splitlines()[:60]) and is_confirmed(text):
        return "bereits bestätigt: " + what
    if dry_run:
        return "Vorschlag: " + what
    lines = text.splitlines(keepends=True)
    idx = [i for i, l in enumerate(lines[:60]) if CONFIRM_RE.match(l.rstrip("\r\n"))]
    if idx:
        old = lines[idx[-1]]
        lines[idx[-1]] = "Bestätigt: ja" + old[len(old.rstrip("\r\n")):]
    else:
        lines.insert(0, "Bestätigt: ja" + ("\r\n" if "\r\n" in text else "\n"))
    new_text = "".join(lines)
    new_fields = {k: nfc(clean(v)) for k, v in parse_headers(new_text)[0].items()}
    if not is_confirmed(new_text) or any(new_fields.get(k) != fields.get(k) for k in ("company", "role", "location")):
        raise ValueError("Die Änderung an %s ließ sich nicht sicher prüfen: nichts geschrieben" % name)
    tmp = os.path.join(os.path.dirname(path), "." + name + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(new_text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError as e:
        raise ValueError("Schreiben von %s fehlgeschlagen: %s" % (name, e))
    return "bestätigt: " + what


def render_command(system, root, today):
    return [sys.executable, kit_run.script_path(system, "render"), "--data", os.path.join(system, "pipeline.csv"), "--prep", os.path.join(system, "prep.json"),
            "--folders", os.path.join(system, "folders.tsv"), "--today", today, "--out", root]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--system-dir", default=HERE)
    ap.add_argument("--data", default=None, help="pipeline.csv (default: <system-dir>/pipeline.csv)")
    ap.add_argument("--root", default=os.path.join(HERE, ".."), help="the career folder holding the employer folders and _Eingang")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--min-age", type=int, default=20, help="seconds a file must be untouched before it is read (default 20)")
    ap.add_argument("--render", action="store_true", help="refresh the HTML pages afterwards")
    ap.add_argument("--confirm", metavar="NAME", help="set 'Bestätigt: ja' in the proposal file matching NAME (name or unique fragment), then run intake")
    ap.add_argument("--yes", action="store_true", help="with --confirm: do not ask (needed when there is no terminal)")
    a = ap.parse_args(argv)
    root, system = os.path.abspath(a.root), os.path.abspath(a.system_dir)
    if a.confirm is not None and (not a.confirm.strip() or a.init):
        print("intake: --confirm braucht einen Namen und lässt sich nicht mit --init kombinieren", file=sys.stderr)
        return 1
    if a.render and a.dry_run:
        print("intake: --render und --dry-run lassen sich nicht kombinieren", file=sys.stderr)
        return 1
    if a.init:
        init(root)
        print("intake: %s ready" % os.path.join(root, INBOX))
        return 0
    data = a.data or os.path.join(system, "pipeline.csv")
    if not os.path.exists(data):
        print("intake: cannot read %s" % data, file=sys.stderr)
        return 1
    if os.path.abspath(data) != os.path.join(system, "pipeline.csv"):
        print("intake: --data must be <system-dir>/pipeline.csv", file=sys.stderr)
        return 1
    min_age = a.min_age
    if a.confirm:
        matches = find_sidecars(os.path.join(root, INBOX), a.confirm)
        if not matches:
            print("intake: keine Begleitdatei zu „%s“ in _Eingang gefunden (Namen mit mindestens 3 Zeichen am Wortanfang; nur von intake angelegte "
                  "Vorschläge oder Dateien mit „Bestätigt:“-Kopfzeile lassen sich bestätigen)" % a.confirm, file=sys.stderr)
            return 1
        if len(matches) > 1:
            print("intake: „%s“ ist mehrdeutig: %s" % (a.confirm, ", ".join(os.path.basename(m) for m in matches)), file=sys.stderr)
            return 1
        try:
            preview = confirm_sidecar(matches[0], dry_run=True)
            print("intake: " + preview)
            if a.dry_run:
                return 0
            if not preview.startswith("bereits bestätigt"):
                go = a.yes or (_interactive() and input("bestätigen? [j/N] ").strip().lower() in ("j", "ja", "y", "yes"))
                if not go:
                    print("intake: nicht bestätigt. Zum Bestätigen: python3 _system/intake.py --confirm \"%s\" --yes" % a.confirm)
                    return 3
                print("intake: " + confirm_sidecar(matches[0]))
        except ValueError as e:
            print("intake: %s" % e, file=sys.stderr)
            return 1
        min_age = 0                                                              # you just acted on the file: do not make it wait
    rep = run(root, system, a.today, dry_run=a.dry_run, min_age=min_age)
    print("intake%s: %d new, %d healed, %d existing, %d already processed, %d waiting, %d unclear, %d failed" % (
        " (dry run)" if a.dry_run else "", len(rep["new"]), len(rep["healed"]), len(rep["existing"]), len(rep["already"]),
        len(rep["waiting"]), len(rep["unclear"]), len(rep["failed"])))
    for n in rep["new"]:
        print("  + uid %d  %s · %s%s" % (n["uid"], n["company"], n["role"], "  (Text fehlt)" if n["text_missing"] else ""))
    for h in rep["healed"]:
        print("  ~ uid %d  %s · %s  (ergänzt: %s)" % (h["uid"], h["company"], h["role"], ", ".join(h["healed"])))
    for u in rep["unclear"]:
        print("  ? %s: %s" % (u["file"], u["reason"]))
    for f in rep["failed"]:
        print("  ! %s: %s" % (f["file"], f["error"]))
    for w in rep["waiting"]:
        print("  … %s: %s (wartet, nächster Lauf holt sie)" % (w["file"], w["reason"]))
    if a.render:                                                                # unconditional: it is what the user asked for
        r = subprocess.run(render_command(system, root, a.today), capture_output=True, text=True)
        if r.returncode != 0:
            print("  ! render.py fehlgeschlagen (Code %s): %s" % (r.returncode, (r.stderr or "").strip()[-400:]))
            return 2
        print("  Seiten aktualisiert")
    elif not a.dry_run and any(rep[k] for k in ("new", "healed", "existing", "unclear", "failed", "waiting", "already")):
        print("Heute-Seite aktualisieren: python3 _system/intake.py --render   (führt render.py aus; im geplanten Lauf folgt es ohnehin)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
