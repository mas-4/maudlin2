"""The Oct 28 redo of the stories, story and saga pages (group E): the story cards' outlet dots and stickers, the
stories page's one-sided stories as a pair of boards, the story pages' broadcast boards and the saga pages' parts and
tellings. Synthetic data only: no database, no models."""
import pytest

from app.site import page_headlines as ph
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
