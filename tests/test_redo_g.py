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
    assert 'class="pick-chip" data-status="in production"' in html and 'data-status="in production"><div' in html
    assert 'class="lab-ba-after" style="--bar: 60.0%"' in html
    page = html[html.index('lab-hero'):]
    assert ' title=' not in page[:page.index('<script>')]  # hover cards, never tooltips


# The methods log

LOG = """# Methods log

Opening paragraph, the page's own.

## 2026-10-28
- **Show claims tied to stories.** What the shows said reaches the story pages, with `code`.
- **One outlet's failure no longer fails the hourly run;** a broken scraper is skipped.
- **Story coherence check tried, not adopted.** It cost more than it caught.
- **Hand labels.** 200 headlines labeled by hand to check the model.
  - *Nested:* a sub-point kept in the card.
- **A merge keeps everything.** Its claims stay with it.

## 2026-10-03 (evening)
- **Shows archive begins.** 40 newsletters and podcasts.

## History
- **2024-01 to 2024-08: built by hand** as Maudlin.
"""


def test_the_log_becomes_days_of_one_line_entries_with_the_text_folded_under():
    from app.site import page_methods
    days = page_methods.parse(LOG)
    assert [(d['anchor'], d['label'], d['short']) for d in days] == [
        ('2026-10-28', 'Oct 28', '28'), ('2026-10-03-evening', 'Oct 3, evening', '3🌙'), ('history', 'History', '🕰️')]
    first = days[0]['entries']
    assert [e['line'] for e in first] == ['Show claims tied to stories', "One outlet's failure no longer fails the hourly run",
                                          'Story coherence check tried, not adopted', 'Hand labels',
                                          'A merge keeps everything']
    assert '<code>code</code>' in first[0]['body'] and 'Show claims tied' not in first[0]['body']
    assert '<em>Nested:</em>' in first[3]['body']  # the sub-list stays with its entry
    assert 'Opening paragraph' not in str(days)


def test_an_entry_is_colored_by_the_first_area_its_line_names_and_tagged_by_kind():
    from app.site import page_methods
    first = page_methods.parse(LOG)[0]['entries']
    assert [e['area'] for e in first] == ['shows', 'outlets', 'stories', 'measures', 'motifs']  # the last from its next sentence
    assert [e['kind'] for e in first] == ['changed', 'fix', 'dropped', 'changed', 'changed']
    assert page_methods.area_of('Nothing named here') == 'site' and page_methods.kind_of('Shows archive begins') == 'new'


def test_the_methods_page_keeps_every_day_anchor_and_filters_by_area():
    from app.site import page_methods
    days = page_methods.parse(LOG)
    areas, kinds = page_methods.keys(days)
    for d in days:
        for e in d['entries']:
            a = next(x for x in areas if x['key'] == e['area'])
            e.update(area_mark=a['mark'], area_name=a['name'], ink=a['ink'], kind_mark='🔧', kind_name='changed')
    html = j2env.get_template('methods.html').render(days=days, areas=areas, kinds=kinds, top=5, total=7)
    assert 'id="2026-10-28"' in html and 'href="#2026-10-03-evening"' in html
    assert 'class="pick-chip" data-area="shows"' in html and 'data-area="shows" style="--ink: #ff6b1a"' in html
    assert html.count('<details>') == 7 and 'methods-paper' in html


# The glossary's folklore cards

def test_the_glossary_explains_the_folklore_half_each_card_opening_with_its_real_badge():
    from bs4 import BeautifulSoup
    from app.site.page_glossary import folk
    from app.site.boards import GENRE_INK
    f = folk()
    assert 'Joe Rogan Experience' in f['crossover'] and 'Theo Von' in f['crossover']
    assert not any('Theo Von' in c and c != 'Theo Von' for c in f['crossover'])  # its podcast feed is the same show
    assert [k['ink'] for k in f['genre_key'][:5]] == list(GENRE_INK.values())
    html = j2env.get_template('glossary.html').render(folk=f, emotions=[], tiers={})
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('#folklore + .table-intro + .terms > .term')
    assert [c['id'] for c in cards] == ['motif', 'genre', 'rests-on', 'answer', 'own-words', 'divide', 'aisle',
                                        'crossover', 'replay']
    for c in cards:  # the badge first, then the heading
        assert c.find(recursive=False) == c.select_one('.gloss-badge') and c.select_one('.gloss-badge').find_next('h3')
    badge = {c['id']: c.select_one('.gloss-badge') for c in cards}
    assert badge['motif'].select_one('a.motif-chip').get_text() == '🧩 Voter fraud'
    assert [a.get_text() for a in badge['rests-on'].select('.motif-chip')] == ['🧩 Voter fraud', '🧩 Rigged election']
    assert badge['answer'].select('.motif-chip')[1].get_text() == '🧩 Voter suppression'
    assert badge['genre'].select_one('.folk-genre').get_text().strip() == '🕵️ Theories'
    assert cards[1].select_one('.rank-key') is not None  # the genre colors' key
    assert badge['own-words'].select_one('.meter .variety-track .meter-dot') is not None
    assert badge['aisle'].select_one('svg.aisle-svg .aisle-arc') is not None
    assert '3+' in badge['replay'].get_text() and badge['crossover'].select('.show-chip')
    assert not soup.select('#folklore ~ .terms [title]')  # hover cards, never tooltips
