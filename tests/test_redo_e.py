"""The Oct 28 redo of the stories, story and saga pages (group E): the story cards' outlet dots and stickers, the
stories page's one-sided stories as a pair of boards, the story pages' broadcast boards and the saga pages' parts and
tellings. Synthetic data only: no database, no models."""
import pytest
from bs4 import BeautifulSoup

from app.site import page_headlines as ph, page_saga, page_story
from app.site.common import j2env


@pytest.fixture
def leans(monkeypatch):
    monkeypatch.setitem(j2env.globals, 'unrated', {'Blog'})
    monkeypatch.setitem(j2env.globals, 'lean_estimates', {'Guess': 1})
    monkeypatch.setitem(j2env.globals, 'icons', {})


def test_a_dot_is_painted_as_its_chip_is(leans):
    assert ph.lean_paint('CNN', -1) == {'fill': ph.bias_colors[2], 'ink': ph.bias_ink[2], 'kind': 'rated',
                                        'word': 'leans left'}
    assert ph.lean_paint('Blog', 0)['kind'] == 'unrated' and ph.lean_paint('Blog', 0)['fill'] == '#ffffff'
    guess = ph.lean_paint('Guess', 0)  # our estimate wins over the placeholder 0, and says it's ours
    assert guess['fill'] == ph.bias_colors[4] and guess['kind'] == 'estimate' and 'our estimate' in guess['word']


def watch(story, side, share, bridge, cluster):
    return {'story': story, 'side': side, 'share': share, 'hit': round(share * 40), 'n': 40, 'has_bridge': bridge,
            'cluster': cluster, 'counts': {'left': 5, 'center': 1, 'right': 0}, 'when': '3 hours',
            'bridge': 'AP has it' if bridge else 'no wire service or center outlet yet', 'title': 'Mostly left: ...'}


def test_one_sided_stories_are_a_pair_of_boards_ranked_by_their_odds():
    boards = ph.crossing_boards([watch('A <b>', 'left', 0.2, True, 1), watch('B', 'left', 0.5, False, 2),
                                 watch('C', 'right', 0.1, False, 3)], {1: 's-11', 2: 's-12'})
    left, right = boards
    assert [b['title'] for b in boards] == ['Mostly left so far', 'Mostly right so far']
    assert [r['name'] for r in left['rows']] == ['B', 'A <b>']  # likeliest to cross first
    assert [r['href'] for r in left['rows']] == ['#s-12', '#s-11'] and right['rows'][0]['href'] == '#story-3'
    assert left['rows'][1]['mark'] == '📡' and left['rows'][0]['mark'] == '⚪'  # the bridge is the colored axis
    assert left['rows'][0]['figure'] == '20 of 40' and left['rows'][0]['bar'] == 50
    assert 'right-leaning outlets within a day' in left['sub']
    html = j2env.from_string('{% import "boards.html" as b %}{{ b.boards(x) }}').render(x=boards)
    assert 'A &lt;b&gt;' in html and 'A <b>' not in html


def test_an_empty_side_says_so():
    left, right = ph.crossing_boards([watch('A', 'left', 0.2, True, 1)], {})
    assert left['rows'] and not right['rows'] and 'only the right' in right['empty']


# --- story pages: broadcast boards and the spread's notes ------------------------------------------------------
def cast(show, place, when, of=5):
    return {'show': show, 'place': place, 'of': of, 'when': when, 'title': 't'}


def test_the_radio_is_one_row_per_programme_with_its_running_order():
    tv = {'channels': [{'name': 'CNN', 'time': '3 min', 'seconds': 180}, {'name': 'Fox News', 'time': '40 s', 'seconds': 40}],
          'captions': [{'channel': 'CNN', 'text': 'A <caption>', 'time': '2 min'}]}
    radio = [cast('NPR News Now', 1, 'Oct 28, 9:00 AM'), cast('NPR News Now', 4, 'Oct 28, 8:00 AM'),
             cast('NPR News Now', 1, 'Oct 28, 7:00 AM'), cast('ABC News Update', 3, 'Oct 28, 9:00 AM')]
    out = page_story.broadcast(tv, radio, {}, {'CNN': 'lean left', 'Fox News': 'right', 'NPR News Now': 'lean left'}, {})
    [(on_tv, on_radio)] = out['pairs']
    assert [r['name'] for r in on_tv['rows']] == ['CNN', 'Fox News'] and on_tv['rows'][0]['bar'] == 100
    assert on_tv['rows'][1]['mark'] == '🐘' and '“A <caption>” (2 min)' in on_tv['rows'][0]['tip']
    npr, abc = on_radio['rows']
    assert (npr['name'], npr['figure'], abc['figure']) == ('NPR News Now', '3× · 🥇 led 2', '1× · best #3')
    assert 'Oct 28, 8:00 AM ET: story 4 of 5' in npr['tip'] and abc['lean'] == 'unrated'
    assert [k['name'] for k in out['key']] == ['leans left', 'right', 'not rated for lean']


def test_a_show_listed_eight_times_is_one_row_and_the_long_tail_shares_one():
    shows = [{'source': 'Pod A', 'title': f'Ep {i}', 'url': f'https://a/{i}'} for i in range(8)]
    shows += [{'source': f'Pod {i}', 'title': 'x', 'url': f'https://b/{i}'} for i in range(page_story.SHOW_ROWS + 2)]
    extras = {'shows': shows, 'satire': [{'source': 'The Onion', 'title': 'j', 'url': 'https://o'}]}
    out = page_story.broadcast(None, [], extras, {}, {'Pod A': 'right'})
    [(on_shows, digging)] = out['pairs']
    first = on_shows['rows'][0]
    assert (first['name'], first['figure'], first['lean']) == ('Pod A', '8', 'right')
    assert len(on_shows['rows']) == page_story.SHOW_ROWS + 1 and on_shows['rows'][-1]['name'] == '3 more shows'
    assert len(out['links']['shows']['Pod A']) == 8 and len(out['links']['shows']['3 more shows']) == 3
    assert digging['rows'][0]['mark'] == '🃏'


def test_no_broadcast_no_boards():
    assert page_story.broadcast(None, [], {}, {}, {})['pairs'] == []


def test_the_notes_draw_wire_copiers_as_lean_dots_and_quotes_as_a_strip(leans):
    outlets = [{'outlet': 'CNN', 'bias': -1}, {'outlet': 'Blog', 'bias': None}]
    out = page_story.notes(outlets, {'wires': 'AP', 'outlets': ['CNN', 'Blog']},
                           {'quotes': [{'phrase': 'a', 'count': 4}, {'phrase': 'b', 'count': 1}]})
    assert [d['kind'] for d in out['wire']] == ['rated', 'unrated']
    assert [q['bar'] for q in out['quotes']] == [100, 25]


def story_context(**extra):
    st = {'id': 7, 'label': 'Story <one>', 'saga': None}
    base = {'story': st, 'outlets': [], 'lean_counts': {'unrated': 0}, 'stickers': [], 'since': 'a', 'until': 'b',
            'flow': [], 'extras': {}, 'notes': {}, 'broadcast': {'pairs': [], 'key': [], 'links': {}},
            'told_as': [], 'folklore': [], 'voters': [], 'names': []}
    return {**base, **extra}


def test_a_story_page_renders_its_boards_and_notes_escaped(leans):
    radio = [cast('NPR <News>', 1, 'Oct 28, 9:00 AM')]
    bc = page_story.broadcast(None, radio, {}, {}, {})
    wire = {'wires': 'AP', 'outlets': ['CNN']}
    ex = {'quotes': [{'phrase': 'said <it>', 'count': 2}], 'wording': {'left': [{'phrase': 'w <l>'}]}}
    html = j2env.get_template('story.html').render(**story_context(
        broadcast=bc, wire=wire, extras=ex, notes=page_story.notes([{'outlet': 'CNN', 'bias': -1}], wire, ex),
        names=['Name <n>']))
    soup = BeautifulSoup(html, 'html.parser')
    assert soup.select_one('#broadcast .rank-board-radio .rank-name').get_text() == 'NPR <News>'
    assert soup.select_one('#broadcast .rank-board-tv .stage-empty')  # the pair's other half says it found nothing
    assert '<News>' not in html and soup.select_one('.story-note-phrase').get_text() == '“said <it>”'
    assert soup.select_one('.story-note-dots .outlet-dot')['data-tip-head'] == 'CNN'
    assert soup.select_one('.story-note-left li:nth-child(2)').get_text() == 'w <l>'
    assert soup.select_one('.story-note-names span').get_text() == 'Name <n>'
    assert not soup.select('.stage-notes') and not soup.select('#broadcast .show-chip')


# --- saga pages: the parts once in full, beads up top, the telling by readable day ------------------------------
def part(i, outlets, page=True, now=False):
    return {'story': i, 'label': f'Part <{i}>', 'outlets': outlets, 'color': '#3a86ff', 'when': 'Oct 3, 2 PM',
            'lasted': '4 hours', 'page': f'story-{i}.html' if page else None, 'now': now, 'first_title': 'First <t>',
            'first_outlets': ['AP'], 'tv': None, 'radio': [], 'folklore': []}


def test_a_sagas_parts_are_one_board_with_their_details_in_the_hover_cards():
    board = page_saga.part_board([part(1, 4), part(2, 8, page=False), part(3, 2, now=True)])
    rows = board['rows']
    assert [r['mark'] for r in rows] == ['📄', '🗄️', '🔴'] and [r['bar'] for r in rows] == [50, 100, 25]
    assert rows[1]['href'] is None and 'no page of its own' in rows[1]['tip']
    assert '“First <t>” first on AP' in rows[0]['tip'] and rows[0]['figure'] == '4 outlets'


def test_a_sagas_telling_reads_its_days_and_colors_its_genres():
    rows = [{'story': 1, 'date': '2026-10-21', 'motif': 'M1', 'name': 'Lawfare', 'genre': 'Theories'},
            {'story': 1, 'date': '2026-10-21', 'motif': 'M1', 'name': 'Lawfare', 'genre': 'Theories'},
            {'story': 1, 'date': '2026-10-20', 'motif': 'M2', 'name': 'Odd one', 'genre': 'Values'}]
    days = page_saga.drift(rows, {1})
    assert [d['label'] for d in days] == ['Wed Oct 21', 'Tue Oct 20'] and days[0]['day'] == '2026-10-21'
    assert days[0]['motifs'][0]['ink'] == '#8a5cff' and days[1]['motifs'][0]['ink'] == '#ffffff'


def test_a_saga_page_lists_its_parts_once_in_full(leans, monkeypatch):
    monkeypatch.setitem(j2env.globals, 'motif_pages', set())
    parts = [part(1, 4), part(2, 8, page=False)]
    days = page_saga.drift([{'story': 1, 'date': '2026-10-21', 'motif': 'M1', 'name': 'Law <fare>', 'genre': None}], {1})
    html = j2env.get_template('saga.html').render(
        saga={'id': 1, 'name': 'S', 'now': False}, parts=parts, stickers=[], color='#ff4fa3', since='a', until='b',
        drift=days, drift_key=[], part_board=page_saga.part_board(parts), retellings=[])
    soup = BeautifulSoup(html, 'html.parser')
    beads = soup.select('.saga-beads .saga-bead-dot')
    assert [b.get_text() for b in beads] == ['1', '2'] and beads[0]['href'] == 'story-1.html' and beads[1].name == 'span'
    assert len(soup.select('.rank-board-parts .rank-row')) == 2 and not soup.select('.story-page-card')
    assert soup.select_one('.saga-drift-date').get_text() == 'Wed Oct 21'
    assert 'Law <fare>' in soup.select_one('.saga-drift-seg').get_text() and 'Law <fare>' not in html
