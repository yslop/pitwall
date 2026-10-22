#!/usr/bin/env python3
"""
Markdown for CVs and letters, rendered three ways from one source (application path, Phase 3 stage A):

  to_html(md)       escaped HTML body for the CI-styled and the plain PDF (headless Chrome prints it)
  flatten_tables(md) Markdown tables as plain lines, for the ATS-safe versions (an ATS reads tables badly)
  write_docx(md, path) an ATS-safe .docx written with the standard library: real headings and bullets, one column, no tables or images

Supported Markdown: # ## ### headings, paragraphs, - / * / 1. lists, > quotes, | tables |, --- rules, **bold**, *italic*, [text](url), `code`.
No raw HTML ever passes through: all text is escaped.
"""
import html
import re
import zipfile

HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
BULLET = re.compile(r"^\s*[-*•]\s+(.*\S)\s*$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*\S)\s*$")
RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
INLINE = re.compile(r"(\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*|\[[^\]\n]+\]\([^)\s]+\)|`[^`\n]+`)")
LINK = re.compile(r"^\[([^\]]+)\]\(([^)\s]+)\)$")
NUMERIC_CELL = re.compile(r"^[\d.,+%€$ ]+$")
SAFE_URL = re.compile(r"^(?:https?://|mailto:)", re.I)
XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ufeff]")      # not allowed in XML 1.0 (a Shift+Enter copied from Word is \x0b)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(md):
    """Blocks: ('h', level, text) ('p', text) ('ul', [items]) ('ol', [items]) ('quote', text) ('table', [rows]) ('hr',)."""
    lines = XML_BAD.sub("", md or "").replace("\r\n", "\n").split("\n")
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = HEADING.match(line)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2)))
            i += 1
        elif RULE.match(line):
            blocks.append(("hr",))
            i += 1
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP.match(lines[i + 1]):
            rows = [_cells(line)]
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            blocks.append(("table", rows))
        elif BULLET.match(line):
            items = []
            while i < len(lines) and BULLET.match(lines[i]):
                items.append(BULLET.match(lines[i]).group(1))
                i += 1
            blocks.append(("ul", items))
        elif NUMBERED.match(line):
            items = []
            while i < len(lines) and NUMBERED.match(lines[i]):
                items.append(NUMBERED.match(lines[i]).group(1))
                i += 1
            blocks.append(("ol", items))
        elif line.lstrip().startswith(">"):
            quote = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote.append(lines[i].lstrip()[1:].strip())
                i += 1
            blocks.append(("quote", " ".join(q for q in quote if q)))
        else:
            para = [line.strip()]                       # always consume the current line: a stray '|' line without a separator row is a paragraph
            i += 1
            while i < len(lines) and lines[i].strip() and not (HEADING.match(lines[i]) or BULLET.match(lines[i]) or NUMBERED.match(lines[i])
                                                              or lines[i].lstrip().startswith((">", "|")) or RULE.match(lines[i])):
                para.append(lines[i].strip())
                i += 1
            blocks.append(("p", "\n".join(para)))
    return blocks


def _inline_html(text):
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append("<strong>%s</strong>" % html.escape(part[2:-2]))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append("<em>%s</em>" % html.escape(part[1:-1]))
        elif part.startswith("`") and part.endswith("`"):
            out.append("<code>%s</code>" % html.escape(part[1:-1]))
        elif LINK.match(part):
            label, url = LINK.match(part).groups()
            out.append('<a href="%s">%s</a>' % (html.escape(url, quote=True), html.escape(label)) if SAFE_URL.match(url) else html.escape(label))
        else:
            out.append(html.escape(part).replace("\n", "<br>"))
    return "".join(out)


def to_html(md):
    """HTML body (no <html> wrapper). Everything from the source is escaped; only links with http(s) or mailto targets stay links."""
    out = []
    for b in parse(md):
        kind = b[0]
        if kind == "h":
            out.append("<h%d>%s</h%d>" % (b[1], _inline_html(b[2]), b[1]))
        elif kind == "p":
            out.append("<p>%s</p>" % _inline_html(b[1]))
        elif kind in ("ul", "ol"):
            out.append("<%s>%s</%s>" % (kind, "".join("<li>%s</li>" % _inline_html(x) for x in b[1]), kind))
        elif kind == "quote":
            out.append("<blockquote>%s</blockquote>" % _inline_html(b[1]))
        elif kind == "hr":
            out.append("<hr>")
        elif kind == "table":
            rows = b[1]
            head = "<tr>%s</tr>" % "".join("<th>%s</th>" % _inline_html(c) for c in rows[0])
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline_html(c) for c in r) for r in rows[1:])
            out.append("<table>%s%s</table>" % (head, body))
    return "\n".join(out)


def _plain(text):
    """Inline Markdown as plain text; a link keeps its address visible (an ATS may drop link targets)."""
    def sub(m):
        part = m.group(0)
        if part.startswith("**"):
            return part[2:-2]
        if part.startswith("`"):
            return part[1:-1]
        if part.startswith("["):
            label, url = LINK.match(part).groups()
            return label if url.replace("mailto:", "") in label else "%s (%s)" % (label, url.replace("mailto:", ""))
        return part[1:-1]
    return INLINE.sub(sub, text)


def flatten_tables(md):
    """The Markdown with every table replaced by plain lines. A strip of numbers over a row of labels ('15+ | 56' over 'years | sites')
    becomes '15+ years · 56 sites'; any other table becomes one line per row."""
    out = []
    for b in parse(md):
        if b[0] == "table":
            rows = b[1]
            if len(rows) >= 2 and rows[0] and all(NUMERIC_CELL.match(c) for c in rows[0]) and len(rows[1]) == len(rows[0]):
                out.append(" · ".join("%s %s" % (a, b_) for a, b_ in zip(rows[0], rows[1])).strip())
                for r in rows[2:]:
                    out.append(" · ".join(c for c in r if c))
            else:
                for r in rows:
                    out.append(" · ".join(c for c in r if c))
            out.append("")
        elif b[0] == "h":
            out += ["#" * b[1] + " " + b[2], ""]
        elif b[0] == "p":
            out += [b[1], ""]
        elif b[0] == "ul":
            out += ["- " + x for x in b[1]] + [""]
        elif b[0] == "ol":
            out += ["%d. %s" % (n, x) for n, x in enumerate(b[1], 1)] + [""]
        elif b[0] == "quote":
            out += ["> " + b[1], ""]
        else:
            out += ["---", ""]
    return "\n".join(out).rstrip() + "\n"


# ── .docx (ATS-safe) ────────────────────────────────────────────────────────
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FONT = "Calibri"


def _x(text):
    return html.escape(text, quote=False)


def _runs(text, base=""):
    out = []
    for part in INLINE.split(_plain_keep(text)):
        if not part:
            continue
        props = base
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            part, props = part[2:-2], base + "<w:b/>"
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            part, props = part[1:-1], base + "<w:i/>"
        elif part.startswith("`") and part.endswith("`"):
            part = part[1:-1]
        out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % ("<w:rPr>%s</w:rPr>" % props if props else "", _x(part)))
    return "".join(out)


def _plain_keep(text):
    """Links become 'label (address)' text, bold and italic stay as markers for _runs."""
    def sub(m):
        label, url = LINK.match(m.group(0)).groups()
        url = url.replace("mailto:", "")
        return label if url in label else "%s (%s)" % (label, url)
    return re.sub(r"\[[^\]\n]+\]\([^)\s]+\)", sub, text)


def _para(text, style=None, num=False, extra=""):
    ppr = ""
    if style or num or extra:
        ppr = "<w:pPr>%s%s%s</w:pPr>" % ('<w:pStyle w:val="%s"/>' % style if style else "", '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' if num else "", extra)
    return "<w:p>%s%s</w:p>" % (ppr, _runs(text))


def docx_document_xml(md):
    body = []
    first = True
    for b in parse(flatten_tables(md)):
        if b[0] == "h":
            body.append(_para(b[2], "Title" if (b[1] == 1 and first) else "Heading%d" % {1: 1, 2: 1, 3: 2}[b[1]]))
        elif b[0] == "p":
            for line in b[1].split("\n"):
                body.append(_para(line))
        elif b[0] in ("ul", "ol"):
            body += [_para(x, "ListBullet", num=True) for x in b[1]]
        elif b[0] == "quote":
            body.append(_para(b[1], None, extra='<w:ind w:left="360"/>'))
        first = False
    sect = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>'
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="%s"><w:body>%s%s</w:body></w:document>' % (W, "".join(body), sect)


def _style(sid, name, size, bold=False, before=0, after=80, based="Normal"):
    return ('<w:style w:type="paragraph" w:styleId="%s"><w:name w:val="%s"/>%s<w:qFormat/><w:pPr><w:spacing w:before="%d" w:after="%d"/></w:pPr>'
            '<w:rPr>%s<w:sz w:val="%d"/></w:rPr></w:style>' % (sid, name, '<w:basedOn w:val="%s"/>' % based if based else "", before, after, "<w:b/>" if bold else "", size))


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="%s"><w:docDefaults><w:rPrDefault><w:rPr>'
          '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s"/><w:color w:val="000000"/><w:sz w:val="22"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault></w:docDefaults>'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="80"/></w:pPr></w:style>%s%s%s%s%s</w:styles>'
          % (W, FONT, FONT, FONT, _style("Title", "Title", 32, True, 0, 120), _style("Heading1", "heading 1", 26, True, 240, 80),
             _style("Heading2", "heading 2", 23, True, 160, 60), _style("Heading3", "heading 3", 22, True, 120, 40),
             _style("ListBullet", "List Bullet", 22, False, 0, 40)))

NUMBERING = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="%s"><w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
             '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr></w:lvl>'
             '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>' % W)

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>')
ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/></Relationships>')


def write_docx(md, path):
    """Write the ATS-safe .docx for a Markdown draft. The file is written to a hidden temp name and moved into place."""
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".", suffix=".docx.tmp")
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/document.xml", docx_document_xml(md))
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return path
