"""md_safe: Markdown from the briefing files -> HTML that cannot carry markup or script of its own."""
import os
import sys

SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM_DIR)

import md_safe


def test_headings_paragraphs_and_inline_formatting():
    out = md_safe.render("# Titel\n\nText mit **fett**, *kursiv* und `code`.\n\n## Unter\n")
    assert "<h1>Titel</h1>" in out and "<h2>Unter</h2>" in out
    assert "<strong>fett</strong>" in out and "<em>kursiv</em>" in out and "<code>code</code>" in out


def test_lists_ordered_and_unordered():
    out = md_safe.render("- eins\n- zwei\n\n1. a\n2. b\n")
    assert "<ul><li>eins</li><li>zwei</li></ul>" in out and "<ol><li>a</li><li>b</li></ol>" in out


def test_tables_have_a_header_row_and_body_rows():
    out = md_safe.render("| Name | Wert |\n|---|---|\n| A | 1 |\n| B | 2 |\n")
    assert "<table>" in out and "<th>Name</th>" in out and "<td>A</td>" in out and "<td>2</td>" in out


def test_quotes_rules_and_fenced_code():
    out = md_safe.render("> Zitat\n\n---\n\n```\nx < y\n```\n")
    assert "<blockquote>" in out and "<hr>" in out and "<pre><code>x &lt; y</code></pre>" in out


def test_raw_html_and_script_are_escaped_everywhere():
    evil = "<script>alert(1)</script>"
    for text in (evil, "# " + evil, "- " + evil, "| " + evil + " |\n|---|\n| " + evil + " |", "**" + evil + "**", "> " + evil):
        out = md_safe.render(text)
        assert "<script" not in out.lower() and "&lt;script&gt;" in out, text


def test_only_http_https_links_become_links():
    out = md_safe.render("[ok](https://example.org/a?x=1&y=2) [bad](javascript:alert(1)) [data](data:text/html,x) [mail](mailto:a@b.c)")
    assert 'href="https://example.org/a?x=1&amp;y=2"' in out and 'rel="noopener"' in out
    assert "javascript:" not in out.replace("[bad](javascript:alert(1))", "") or 'href="javascript' not in out
    assert 'href="javascript' not in out and 'href="data' not in out and 'href="mailto' not in out


def test_a_quote_in_a_link_cannot_break_out_of_the_attribute():
    out = md_safe.render('[x](https://e.org/"onmouseover="alert(1))')
    assert 'onmouseover="' not in out


def test_empty_and_odd_input_never_crash():
    assert md_safe.render("") == ""
    assert md_safe.render(None) == ""
    md_safe.render("|\n|||\n```\nunclosed\n**unclosed\n")


def test_oversized_text_is_cut_with_a_note():
    out, truncated = md_safe.render_capped("a\n\n" * 50000, 1000)
    assert truncated is True and len(out) < 3000 and "gekürzt" in out
    out2, t2 = md_safe.render_capped("kurz", 1000)
    assert t2 is False and "<p>kurz</p>" in out2
