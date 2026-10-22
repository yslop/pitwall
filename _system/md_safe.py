"""Markdown from the briefing and cheat-sheet files -> HTML that cannot carry markup or script of its own.

The files are written by agents from third-party material (job posts, web pages, mail), so nothing in them is
trusted: every character is HTML-escaped first, then a small, fixed set of Markdown forms is turned into tags.
Links become links only for http and https. No raw HTML, no images, no other schemes. Python 3.9 compatible.
"""
import html
import re

_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_ITAL = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
_CODE = re.compile(r"(`[^`\n]+`)")
_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_UL = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _esc(text):
    return html.escape(text, quote=True)


def _inline(raw):
    """Escape first, then add tags. The URL of a link is taken from the escaped text, so a quote cannot leave the attribute."""
    out = []
    for part in _CODE.split(_esc(raw)):
        if len(part) > 1 and part[0] == "`" and part[-1] == "`":
            out.append("<code>%s</code>" % part[1:-1])
            continue
        part = _LINK.sub(lambda m: '<a href="%s" target="_blank" rel="noopener">%s</a>' % (m.group(2), m.group(1)), part)
        part = _BOLD.sub(r"<strong>\1</strong>", part)
        part = _ITAL.sub(r"<em>\1</em>", part)
        out.append(part)
    return "".join(out)


def _cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render(text):
    if text is None:
        return ""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>%s</p>" % _inline(" ".join(para)))
            del para[:]

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % _esc("\n".join(code)))
            continue
        if not stripped:
            flush()
            i += 1
            continue
        m = _HEAD.match(stripped)
        if m:
            flush()
            level = min(len(m.group(1)), 4)
            out.append("<h%d>%s</h%d>" % (level, _inline(m.group(2)), level))
            i += 1
            continue
        if _RULE.match(stripped) and not _UL.match(stripped):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _SEP.match(lines[i + 1]):
            flush()
            head = _cells(line)
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            th = "".join("<th>%s</th>" % _inline(c) for c in head)
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline(c) for c in r) for r in rows)
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (th, body))
            continue
        if stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % _inline(" ".join(quote)))
            continue
        ul, ol = _UL.match(line), _OL.match(line)
        if ul or ol:
            flush()
            pattern, tag = (_UL, "ul") if ul else (_OL, "ol")
            items = []
            while i < len(lines) and pattern.match(lines[i]):
                items.append(pattern.match(lines[i]).group(1))
                i += 1
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % _inline(t) for t in items), tag))
            continue
        para.append(stripped)
        i += 1
    flush()
    return "".join(out)


def render_capped(text, limit):
    """(html, truncated). A text above `limit` characters is cut at a line break and says so."""
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return render(text), False
    cut = text[:limit]
    if "\n" in cut:
        cut = cut[:cut.rfind("\n")]
    return render(cut) + '<p class="md-cut">… gekürzt: für den vollen Text die Datei öffnen.</p>', True
