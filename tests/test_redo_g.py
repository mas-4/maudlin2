"""The site redo's group G (Oct 28): the Lab's ladders (page_lab.py), the methods log's timeline (page_methods.py) and
the glossary's folklore cards (page_glossary.py)."""
import sqlite3

from app.site import page_lab
from app.site.common import j2env


# The Lab

def test_only_a_plain_a_to_b_on_one_known_scale_gets_a_bar():
    assert page_lab.before_after('Qwen3 with Arctic: top-12 82.3% to 85.2%')['figure'] == '82.3% → 85.2%'
    ba = page_lab.before_after('the element won: AUC 0.54 to 0.79')
    assert (ba['before'], ba['after'], ba['scale']) == (0.54, 0.79, 1)
    # an interval of a gain, a range, counts and words, and "against" (not a before and after): no bar
    assert page_lab.before_after('Babel clears the noise (+2.9, +1.7 to +4.2)') is None
    assert page_lab.before_after('genre calls right 53% to 64-67%') is None
    assert page_lab.before_after('posts 20.7 to 15.9 words') is None
    assert page_lab.before_after('82.9% against 82.3%') is None
    assert page_lab.before_after('') is None
    # the first readable pair wins, past an unreadable one
    assert page_lab.before_after('+3.0 to +9.0; 62.9% to 68.4%')['figure'] == '62.9% → 68.4%'


def _catalog(tmp_path, rows):
    db = tmp_path / 'experiments.sqlite'
    con = sqlite3.connect(db)
    con.execute('create table experiments (code text primary key, name text, family text, question text, script text,'
                ' status text, data text, result text, updated text, codename text, why text)')
    con.executemany('insert into experiments (code, codename, family, name, status, result, updated) '
                    'values (?, ?, ?, ?, ?, ?, ?)', rows)
    con.commit()
    con.close()
    return str(db)


def test_a_family_is_a_ladder_from_in_use_down_to_not_kept_in_code_order(tmp_path, monkeypatch):
    monkeypatch.setattr(page_lab, 'DB', _catalog(tmp_path, [
        ('E11', 'Babel', 'the shortlist', 'Every embedding model', 'in production', 'top-12 82.3% to 85.2%', '2026-10-10'),
        ('E2', 'Morpheus', 'the shortlist', 'Imagined instances', 'not kept', 'nothing', ''),
        ('E0.1', 'the Oracle', 'the shortlist', "Gemma's own yes or no", 'not kept', 'AUC 0.818', ''),
        ('E1', 'Lethe', 'the shortlist', 'Subtract the news', 'in production', 'kept', ''),
        ('J1', 'the Norns', 'the judge', 'A jury', 'running', '', '')]))
    found = page_lab.experiments()
    ladders = {b['key']: b for b in page_lab.ladders(found)}
    assert [r['code'] for r in ladders['e']['rows']] == ['E1', 'E11', 'E0.1', 'E2']
    babel = ladders['e']['rows'][1]
    assert babel['name'] == 'Babel' and babel['ink'] == page_lab.STATUS_INK['in production'] and babel['mark'] == '🏭'
    assert (babel['before'], babel['after'], babel['figure']) == (82.3, 85.2, '82.3% → 85.2%')
    assert '❓ Every embedding model' in babel['tip'] and '🔬 top-12 82.3% to 85.2%' in babel['tip']
    assert ladders['e']['rows'][0]['before'] is None  # "kept": no numbers, no bar
    key = page_lab.status_key(found)
    assert [(k['status'], k['count']) for k in key] == [('in production', 2), ('running', 1), ('not kept', 2)]


def test_the_lab_page_has_real_filters_and_escapes_what_it_shows(tmp_path, monkeypatch):
    monkeypatch.setattr(page_lab, 'DB', _catalog(tmp_path, [
        ('E1', 'Lethe <b>', 'the shortlist', 'Subtract "the news"', 'in production', 'AUC 0.5 to 0.6', '')]))
    found = page_lab.experiments()
    html = j2env.get_template('lab.html').render(ladders=page_lab.ladders(found), total=1,
                                                 key=page_lab.status_key(found), with_bar=1)
    assert 'Lethe &lt;b&gt;' in html and 'Lethe <b>' not in html
    assert 'data-tip="❓ Subtract &#34;the news&#34;' in html or 'data-tip="❓ Subtract &quot;the news&quot;' in html
    assert 'class="lab-filter" data-status="in production"' in html and 'data-status="in production"><div' in html
    assert 'class="lab-ba-after" style="--bar: 60.0%"' in html
    page = html[html.index('lab-hero'):]
    assert ' title=' not in page[:page.index('<script>')]  # hover cards, never tooltips
