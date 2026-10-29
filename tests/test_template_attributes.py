"""No bare apostrophe in a template's attribute text (Oct 29): Netlify's pretty-URL pass rewrites the live HTML with
single-quoted attributes and escapes an apostrophe as \\', which HTML doesn't read, so the hover card for "Every
outlet's headline…" said only "Every outlet\\". Write ’ (or let |e make &#39;, which comes through whole)."""
import glob
import os
import re

TEMPLATES = os.path.join(os.path.dirname(__file__), '..', 'app', 'site', 'templates')
ATTRIBUTE = re.compile(r'\s([a-zA-Z][\w:-]*)="([^"]*)"')
JINJA = re.compile(r'\{\{.*?\}\}|\{%.*?%\}')


def bare_apostrophes(src: str) -> list[str]:
    body = re.sub(r'<script\b.*?</script>', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), src, flags=re.S)
    return [f'{m.group(1)}="{m.group(2)[:60]}"' for m in ATTRIBUTE.finditer(body) if "'" in JINJA.sub('', m.group(2))]


def test_the_scan_finds_a_bare_apostrophe_and_spares_jinja_and_scripts():
    assert bare_apostrophes('<a title="Every outlet\'s headline">') == ['title="Every outlet\'s headline"']
    assert bare_apostrophes('<a title="Every outlet’s {{ x[\'y\'] }}">') == []
    assert bare_apostrophes('<script>el.innerHTML = "<b title=\\"it\'s\\">"</script>') == []


def test_no_template_attribute_has_a_bare_apostrophe():
    found = [f'{os.path.basename(f)}: {a}' for f in sorted(glob.glob(os.path.join(TEMPLATES, '*.html')))
             for a in bare_apostrophes(open(f, encoding='utf-8').read())]
    assert found == []
