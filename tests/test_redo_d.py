"""The site redo's group D (Oct 28): the emotions page's boards and side bars, the edits page's rewrite boards and
headline races, the names page's strips. The pieces, on canned rows; the pages themselves render in
test_site_pages_render.py."""
import pytest

from app.site import boards as strips
from app.site.common import j2env
from app.site import page_edits, page_emotions as pe


@pytest.fixture
def leans(monkeypatch):
    monkeypatch.setitem(j2env.globals, 'unrated', {'Odd <News>'})
    monkeypatch.setitem(j2env.globals, 'lean_estimates', {'Guessed': -1})


def outlet(name, bias, **shares):
    full = dict.fromkeys(pe.EMOTION_COLUMNS, 0.0)
    full.update(shares)
    lean, words = pe.outlet_lean(name, bias)
    return {'name': name, 'headlines': 40, 'shares': full, 'lean': lean, 'lean_words': words,
            'href': f'outlet-{name.lower()}.html', 'tip': f'{name} tip'}


def test_outlet_lean_says_ratings_estimates_and_unrated(leans):
    assert pe.outlet_lean('Fox', 2) == ('right', 'right')
    assert pe.outlet_lean('CNN', -1) == ('lean left', 'leans left')
    assert pe.outlet_lean('Guessed', 0) == ('lean left', 'leans left (our estimate, not a rating)')
    assert pe.outlet_lean('Odd <News>', 0) == ('unrated', 'lean not rated')
    assert pe.outlet_lean('Anyone', 0, rated=False)[0] == 'unrated'


def test_outlet_boards_pair_the_feelings_and_color_rows_by_lean(leans):
    outlets = [outlet('Fox', 2, fear=0.4, hope=0.1, neutral=0.2), outlet('CNN', -1, fear=0.2, hope=0.3, neutral=0.4),
               outlet('Odd <News>', 0, fear=0.3, neutral=0.1)]
    boards = pe.outlet_boards(outlets)
    assert [b['title'] for b in boards[:4]] == ['Most fearful', 'Most hopeful', 'Angriest', 'Calmest']
    assert len(boards) == 8  # every feeling has its board
    fear = boards[0]
    assert [r['name'] for r in fear['rows']] == ['Fox', 'Odd <News>', 'CNN']
    assert fear['rows'][0]['figure'] == '40%' and fear['rows'][0]['bar'] == 100
    assert fear['rows'][0]['ink'] == strips.LEAN_INK['right'] and fear['rows'][0]['mark'] == '🐘'
    assert fear['rows'][1]['ink'] == strips.LEAN_INK['unrated'] and fear['rows'][1]['mark_label'] == 'lean not rated'
    assert 'fear' in fear['sub'] and 'bar' in fear['sub']
    assert [k['name'] for k in pe.lean_key([r for b in boards for r in b['rows']])] == \
        ['Leans left', 'Right', 'Lean not rated']  # left to right, only the leans shown


def test_side_bars_are_three_with_every_feeling_in_order():
    sides = [{'name': n, 'headlines': 10, 'shares': dict.fromkeys(pe.EMOTION_COLUMNS, 1 / 8)}
             for n in ('Left-leaning', 'Center', 'Right-leaning', 'Not rated')]
    bars = pe.side_bars(sides)
    assert [b['name'] for b in bars] == ['Left-leaning', 'Center', 'Right-leaning']
    assert [g['emotion'] for g in bars[0]['segments']] == pe.EMOTION_COLUMNS
    assert all(g['tint'] == pe.TINT[g['emotion']] for g in bars[0]['segments'])


def rate(agency, edits, headlines, bias=0):
    lean, words = pe.outlet_lean(agency, bias)
    return {'agency': agency, 'edits': edits, 'headlines': headlines, 'per_100': round(100 * edits / headlines, 1),
            'href': f'outlet-{agency.lower()}.html', 'lean': lean, 'lean_words': words}


def test_rewrite_boards_rank_rates_and_the_surest_zeros(leans):
    rates = [rate('A', 5, 100, -2), rate('B', 1, 10, 2), rate('C', 0, 500), rate('D', 0, 50, 1)]
    most, never = page_edits.rate_boards(rates, {'A': 'feed'})
    assert (most['title'], never['title']) == ('Rewrite most', 'Never rewrite')
    assert [r['name'] for r in most['rows']] == ['B', 'A']  # 10 per 100 before 5
    assert most['rows'][0]['figure'] == '10 per 100' and most['rows'][0]['ink'] == strips.LEAN_INK['right']
    assert 'RSS feed' in most['rows'][1]['tip'] and 'front page' in most['rows'][0]['tip']
    assert [r['name'] for r in never['rows']] == ['C', 'D']  # the longest record first
    assert never['rows'][0]['figure'] == '0 of 500'
    assert 'per 100' in most['sub'] and 'surer the zero' in never['sub']


def test_a_headline_test_becomes_a_race():
    t = {'state': 'won', 'variants': [
        {'text': 'Kept', 'default': True, 'live': True, 'won': True, 'hours': 10},
        {'text': 'Gone', 'default': False, 'live': False, 'won': False, 'hours': 0.4}]}
    kept, gone = page_edits.race(t)['lanes']
    assert kept['bar'] == 100 and kept['up'] == '10h' and '🏆' in kept['tip'] and '⭐' in kept['tip']
    assert gone['bar'] == 4 and gone['up'] == 'under an hour' and 'dropped' in gone['tip']
    running = page_edits.race({'state': 'running', 'variants': [{**v, 'won': False} for v in t['variants']]})['lanes']
    assert '🟢 still being tried' in running[0]['tip'] and '🟢' not in running[1]['tip']
