"""Static asset and template sanity checks, without a browser: the stylesheet's structure and the rules the pages
depend on, the page script's syntax, and every template parsing and resolving its extends/includes."""
import os
import re
import shutil
import subprocess

import pytest
from jinja2 import nodes

from app.site.common import j2env
from app.utils.constants import Constants

SITE = os.path.join(Constants.Paths.ROOT, 'app', 'site')
STATIC = os.path.join(SITE, 'static')
TEMPLATES = os.path.join(SITE, 'templates')
TEMPLATE_NAMES = sorted(f for f in os.listdir(TEMPLATES) if os.path.isfile(os.path.join(TEMPLATES, f)))


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as f:
        return f.read()


def strip_css_comments_and_strings(css: str) -> str:
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', css)


@pytest.fixture(scope='module')
def css():
    return read(STATIC, 'style.css')


@pytest.fixture(scope='module')
def js():
    return read(STATIC, 'index.js')


# <editor-fold desc="style.css">
def test_css_braces_balance(css):
    depth = 0
    for i, ch in enumerate(strip_css_comments_and_strings(css)):
        depth += ch == '{'
        depth -= ch == '}'
        assert depth >= 0, f'unmatched }} near offset {i}'
    assert depth == 0, f'{depth} unclosed {{'


def test_css_comments_are_closed(css):
    assert css.count('/*') == css.count('*/')


@pytest.mark.parametrize('selector', ['#memphis', '.cloud-paper', '.page-toc', '.toc-toggle', '.outlet-icon',
                                      '.outlet-mono', '.story', '.storylink', '.navbar', '.nav-toggle'])
def test_css_has_rules_the_pages_depend_on(css, selector):
    body = strip_css_comments_and_strings(css)
    assert re.search(re.escape(selector) + r'(?![\w-])[^{};]*\{', body), f'no rule for {selector}'


def block_after(text: str, start: int) -> str:
    """The body of the {...} block opening at or after `start`."""
    open_at = text.index('{', start)
    depth = 0
    for i in range(open_at, len(text)):
        depth += text[i] == '{'
        depth -= text[i] == '}'
        if depth == 0:
            return text[open_at + 1:i]
    raise AssertionError('unclosed block')


def test_css_respects_reduced_motion(css):
    body = strip_css_comments_and_strings(css)
    blocks = [block_after(body, m.end()) for m in re.finditer(r'@media\s*\(prefers-reduced-motion:\s*reduce\)', body)]
    assert blocks
    together = '\n'.join(blocks)
    assert 'animation' in together or 'transition' in together
    assert '#memphis' in together, 'the ambient shapes should hold still for readers who ask for less motion'


def test_css_media_queries_have_bodies(css):
    body = strip_css_comments_and_strings(css)
    assert not re.search(r'@media[^{;]*;', body), 'an @media with no block'
# </editor-fold>


# <editor-fold desc="index.js">
def test_js_syntax_with_node(js, tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node not installed')
    path = tmp_path / 'index.js'
    path.write_text(js, encoding='utf-8')
    result = subprocess.run([node, '--check', str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', ['popCard', 'memphis', 'closePop', 'packColumns'])
def test_js_defines_functions(js, name):
    assert re.search(rf'function\s+{name}\s*\(', js), name


def test_js_brackets_balance(js):
    code = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', js, flags=re.S))
    code = re.sub(r'`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', '""', code)
    for a, b in ['()', '[]', '{}']:
        assert code.count(a) == code.count(b), f'{a}{b} unbalanced'
# </editor-fold>


# <editor-fold desc="templates">
@pytest.mark.parametrize('name', TEMPLATE_NAMES)
def test_template_parses(name):
    j2env.get_template(name)  # raises TemplateSyntaxError


def referenced_templates(name):
    ast = j2env.parse(read(TEMPLATES, name))
    for node in ast.find_all((nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)):
        if isinstance(node.template, nodes.Const):
            yield node.template.value


@pytest.mark.parametrize('name', TEMPLATE_NAMES)
def test_template_references_resolve(name):
    for ref in referenced_templates(name):
        assert ref in TEMPLATE_NAMES, f'{name} references missing template {ref}'


def test_page_templates_extend_the_layout():
    for name in ('headlines.html', 'glossary.html', 'emotions.html', 'agencies.html', 'edits.html'):
        assert list(referenced_templates(name))[:1] == ['page.html'], name


@pytest.mark.parametrize('name', TEMPLATE_NAMES)
def test_template_local_assets_exist(name):
    """Every local script, stylesheet and icon a template links to is a file we ship (pages are generated)."""
    for ref in re.findall(r'(?:src|href)="(\.?/?[\w.-]+\.(?:js|css|ico|png))(?:\?[^"]*)?"', read(TEMPLATES, name)):
        if '{' in ref:
            continue
        assert os.path.exists(os.path.join(STATIC, ref.removeprefix('./'))), f'{name}: {ref}'


def test_layout_versions_its_assets():
    page = read(TEMPLATES, 'page.html')
    assert re.search(r'href="\./style\.css\?v=\{\{ build_version \}\}"', page)
    assert re.search(r'src="index\.js\?v=\{\{ build_version \}\}"', page)


def test_layout_places_nav_and_footer():
    page = read(TEMPLATES, 'page.html')
    assert page.index('{{ nav }}') < page.index('{% block content %}') < page.index('{{ footer }}')
    assert 'name="viewport"' in page and '<html lang="en">' in page
# </editor-fold>
