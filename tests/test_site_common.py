"""app/site/common.py: the Jinja environment's helpers (chip names, chip colors, outlet icons, the date filter) and the
template and path handlers. Nothing here touches the database; files go to tmp_path."""
import os
import re
from datetime import datetime as dt

import pytest
from jinja2 import ChoiceLoader, DictLoader
from markupsafe import Markup

from app.site import common
from app.site.common import (PathHandler, SHORT_NAMES, TemplateHandler, chip_style, date, j2env, outlet_icon,
                             short_name)
from app.site.graphing import bias_colors, bias_ink
from app.utils.config import Config


# <editor-fold desc="short_name">
@pytest.mark.parametrize('name, short', sorted(SHORT_NAMES.items()))
def test_short_name_maps_long_names(name, short):
    assert short_name(name) == short
    assert len(short) < len(name)


@pytest.mark.parametrize('name', ['CNN', 'Fox News', 'The Guardian', '', 'wall street journal'])
def test_short_name_passes_other_names_through(name):
    assert short_name(name) == name


def test_short_name_is_a_template_global():
    assert j2env.globals['short_name'] is short_name
    assert j2env.globals['short_names'] is SHORT_NAMES
# </editor-fold>


# <editor-fold desc="chip_style">
@pytest.fixture
def ratings_globals(monkeypatch):
    """Fresh unrated set and lean estimates, restored after the test."""
    monkeypatch.setitem(j2env.globals, 'unrated', set())
    monkeypatch.setitem(j2env.globals, 'lean_estimates', {})
    return j2env.globals


@pytest.mark.parametrize('bias', [-3, -2, -1, 0, 1, 2, 3])
def test_chip_style_rated_uses_lean_colors(ratings_globals, bias):
    style = chip_style('CNN', bias)
    assert style == f'background-color: {bias_colors[bias + 3]}; color: {bias_ink[bias + 3]}'
    assert 'dashed' not in style


def test_chip_style_accepts_numeric_strings_and_floats(ratings_globals):
    assert chip_style('CNN', '-2') == chip_style('CNN', -2)
    assert chip_style('CNN', 1.0) == chip_style('CNN', 1)


def test_chip_style_unrated_is_dashed_white(ratings_globals):
    ratings_globals['unrated'].add('Mystery Gazette')
    style = chip_style('Mystery Gazette', 2)
    assert 'background-color: #ffffff' in style
    assert 'border-style: dashed' in style
    # its placeholder lean is ignored
    assert bias_colors[5] not in style


def test_chip_style_estimate_beats_unrated(ratings_globals):
    """An outlet we've estimated is also unrated: the estimate's color wins, dashed to say it isn't a rating."""
    ratings_globals['unrated'].add('Mystery Gazette')
    ratings_globals['lean_estimates']['Mystery Gazette'] = -1
    style = chip_style('Mystery Gazette', 0)
    assert style == f'background-color: {bias_colors[2]}; color: {bias_ink[2]}; border-style: dashed'


def test_chip_style_estimate_ignores_the_stored_bias(ratings_globals):
    ratings_globals['lean_estimates']['Mystery Gazette'] = 2
    assert chip_style('Mystery Gazette', -2) == chip_style('Mystery Gazette', 0)
    assert bias_colors[5] in chip_style('Mystery Gazette', -2)


def test_chip_style_only_affects_named_outlets(ratings_globals):
    ratings_globals['unrated'].add('Mystery Gazette')
    ratings_globals['lean_estimates']['Other Gazette'] = 1
    assert chip_style('CNN', -1) == f'background-color: {bias_colors[2]}; color: {bias_ink[2]}'
# </editor-fold>


# <editor-fold desc="outlet_icon">
@pytest.fixture
def icons(monkeypatch):
    monkeypatch.setitem(j2env.globals, 'icons', {})
    return j2env.globals['icons']


def test_outlet_icon_uses_the_favicon_when_there_is_one(icons):
    icons['CNN'] = 'icons/cnn.png'
    html = outlet_icon('CNN')
    assert isinstance(html, Markup)
    assert html == '<img class="outlet-icon" src="icons/cnn.png" alt="" loading="lazy">'


def test_outlet_icon_escapes_the_icon_path(icons):
    icons['Odd'] = 'icons/a"b<c>.png'
    html = str(outlet_icon('Odd'))
    assert 'a&#34;b&lt;c&gt;.png' in html
    assert '"b<c>' not in html


@pytest.mark.parametrize('name, initial', [
    ('CNN', 'C'), ('The Hill', 'H'), ('The Wall Street Journal', 'W'), ('axios', 'A'), ('  spaced', 'S'),
    ('Theory Weekly', 'T'),  # "The" only counts as a word
    ('The', 'T'), ('The ', '?'), ('', '?'),
])
def test_outlet_icon_falls_back_to_the_initial(icons, name, initial):
    html = outlet_icon(name)
    assert isinstance(html, Markup)
    assert html == f'<span class="outlet-icon outlet-mono" aria-hidden="true">{initial}</span>'


def test_outlet_icon_escapes_the_initial(icons):
    assert '&lt;' in str(outlet_icon('<script>'))
    assert '<s' not in str(outlet_icon('<script>')).replace('<span', '')


def test_outlet_icon_empty_path_counts_as_no_icon(icons):
    icons['CNN'] = ''
    assert 'outlet-mono' in outlet_icon('CNN')


def test_outlet_icon_is_safe_in_autoescaped_templates(icons):
    """Markup isn't escaped again where autoescape is on."""
    from jinja2 import Environment
    env = Environment(autoescape=True)
    out = env.from_string('{{ icon }}').render(icon=outlet_icon('CNN'))
    assert out.startswith('<span')
# </editor-fold>


# <editor-fold desc="date filter and template handler">
def test_date_filter_uses_config_format():
    when = dt(2026, 10, 3, 9, 4, 5)
    assert date(when) == '2026-10-03 09:04:05'
    assert j2env.filters['date'] is date


def test_markdown_filter_is_registered():
    assert '<strong>' in j2env.filters['markdown']('**bold**')


@pytest.fixture
def scratch_templates(monkeypatch):
    """Extra in-memory templates, found before the real ones."""
    loader = DictLoader({
        'unit_test.html': '{{ when|date }}|{{ short_name(name) }}|{{ outlet_icon(name) }}|{{ greeting }}',
        'unit_child.html': '{% extends "unit_base.html" %}{% block b %}child {{ x }}{% endblock %}',
        'unit_base.html': '[{% block b %}{% endblock %}]',
    })
    monkeypatch.setattr(j2env, 'loader', ChoiceLoader([loader, j2env.loader]))
    monkeypatch.setitem(j2env.globals, 'icons', {})


def test_template_handler_defaults_path_to_build_dir(scratch_templates):
    handler = TemplateHandler('unit_test.html')
    assert handler.template_name == 'unit_test.html'
    assert handler.path == os.path.join(Config.build, 'unit_test.html')
    assert TemplateHandler('unit_test.html', 'other.html').path == os.path.join(Config.build, 'other.html')


def test_template_handler_renders_with_globals_and_filters(scratch_templates):
    out = TemplateHandler('unit_test.html').render(
        {'when': dt(2026, 1, 2, 3, 4, 5), 'name': 'The Wall Street Journal', 'greeting': 'hi'})
    assert out.split('|')[0] == '2026-01-02 03:04:05'
    assert out.split('|')[1] == 'WSJ'
    assert 'outlet-mono' in out and '>W<' in out
    assert out.endswith('|hi')


def test_template_handler_write_to_explicit_path(scratch_templates, tmp_path):
    target = tmp_path / 'page.html'
    TemplateHandler('unit_child.html').write({'x': 'é ✨'}, str(target))
    assert target.read_text(encoding='utf-8') == '[child é ✨]'


def test_template_handler_write_default_path(scratch_templates, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    handler = TemplateHandler('unit_child.html', 'out.html')
    handler.write({'x': 1})
    assert (tmp_path / 'out.html').read_text() == '[child 1]'


def test_template_handler_missing_template_raises():
    from jinja2 import TemplateNotFound
    with pytest.raises(TemplateNotFound):
        TemplateHandler('no-such-template.html')
# </editor-fold>


# <editor-fold desc="paths and build helpers">
def test_path_handler(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    p = PathHandler(PathHandler.FileNames.main_wordcloud)
    assert p.path == 'wordcloud.png'
    assert p.build == os.path.join(str(tmp_path), 'wordcloud.png')


def test_path_handler_file_names_are_distinct_pngs():
    names = {k: v for k, v in vars(PathHandler.FileNames).items() if not k.startswith('_')}
    assert names
    assert all(v.endswith('.png') for v in names.values())
    assert len(set(names.values())) == len(names)
    assert j2env.globals['FileNames'] is PathHandler.FileNames


def test_clear_build_removes_files_and_folders(monkeypatch, tmp_path):
    (tmp_path / 'a.html').write_text('x')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'b.png').write_text('y')
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    common.clear_build()
    assert os.listdir(tmp_path) == []


def test_copy_assets(monkeypatch, tmp_path):
    assets, build, styles = tmp_path / 'assets', tmp_path / 'build', tmp_path / 'styles'
    for d in (assets, build, styles):
        d.mkdir()
    (assets / 'style.css').write_text('stale {}')  # a leftover in the static folder never wins over the partials
    (assets / 'index.js').write_text('1;')
    (styles / '010-nav.css').write_text('/* Nav */\n.nav {}\n')
    (styles / '000-base.css').write_text('/* Base */\nbody {}')
    (styles / 'notes.txt').write_text('not css')
    monkeypatch.setattr(Config, 'assets', str(assets))
    monkeypatch.setattr(Config, 'build', str(build))
    monkeypatch.setattr(Config, 'styles', str(styles))
    common.copy_assets()
    assert sorted(os.listdir(build)) == ['index.js', 'style.css']
    assert (build / 'style.css').read_text() == '/* Base */\nbody {}\n\n/* Nav */\n.nav {}\n'


def test_stamp_build_sets_version_and_rerenders_nav(monkeypatch):
    for key in ('built_at', 'build_version', 'built_at_text', 'nav'):
        monkeypatch.setitem(j2env.globals, key, None)
    common.stamp_build()
    g = j2env.globals
    assert re.fullmatch(r'\d{12}', g['build_version'])
    assert dt.fromisoformat(g['built_at']).tzinfo is not None
    assert re.fullmatch(r'\d{1,2}:\d\d [AP]M ET', g['built_at_text'])
    assert f'data-built="{g["built_at"]}"' in g['nav']
    assert g['built_at_text'] in g['nav']


def test_core_template_globals_are_registered():
    for key in ('Config', 'bias', 'credibility', 'now', 'nav', 'footer', 'enumerate', 'icons', 'outlet_icon',
                'chip_style', 'unrated', 'lean_estimates'):
        assert key in j2env.globals, key
    assert j2env.globals['bias']['-2'] == 'Left'
    assert j2env.globals['bias']['0'] == 'Center'
# </editor-fold>
