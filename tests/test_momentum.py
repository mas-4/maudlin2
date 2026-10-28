"""The momentum and crossing tables (app/analysis/momentum.py) on synthetic stories: the counting, the small-cell rule
and the words on the cards."""
from datetime import datetime as dt, timedelta as td

from app.analysis import momentum as m

NOW = dt(2026, 10, 28, 12)
H = td(hours=1)
WIRES = {'AP', 'Reuters'}


def story(sid, birth, joins):
    """joins: (hours from birth, side, name); the earliest sighting of each name counts"""
    outlets = {}
    for hours, side, name in joins:
        at = birth + hours * H
        if name not in outlets or at < outlets[name][0]:
            outlets[name] = (at, side)
    return {'id': sid, 'birth': birth, 'outlets': outlets}


def fast(sid, birth, wide=True):
    """Six outlets in the half hour before birth; if wide, fourteen more 90 minutes after (20 by its third run)"""
    joins = [(-0.5, None, f'o{i}') for i in range(6)]
    if wide:
        joins += [(1.5, None, f'o{i}') for i in range(6, 20)]
    return story(sid, birth, joins)


def slow(sid, birth):
    """Six outlets that trickled in over the ten hours before birth, then nothing"""
    return story(sid, birth, [(-10 + i, None, f'o{i}') for i in range(6)])


def history(n_fast=20, n_fast_flat=5, n_slow=40):
    """Settled stories: fast ones (most went wide), and slow ones (none did)"""
    old = NOW - td(days=5)
    out = [fast(i, old + i * H) for i in range(n_fast)]
    out += [fast(100 + i, old + i * H, wide=False) for i in range(n_fast_flat)]
    out += [slow(200 + i, old + i * H) for i in range(n_slow)]
    return out


def test_state_counts_outlets_and_the_last_three_runs():
    s = story(1, NOW, [(-5, None, 'a'), (-2, None, 'b'), (-0.5, None, 'c'), (0, None, 'd'), (1, None, 'e'),
                       (0.5, None, 'c')])  # c's later headline doesn't move its first sighting
    assert m.state(s, NOW) == {'outlets': 4, 'gained': 3, 'hours': 0.0}
    assert m.state(s, NOW + 3 * H) == {'outlets': 5, 'gained': 1, 'hours': 3.0}


def test_keys_band_the_state_and_stop_when_wide_or_old():
    assert m.momentum_keys({'outlets': 6, 'gained': 6, 'hours': 0.0}) == [
        '7 or fewer|6 or more|in their first 3 hours', '7 or fewer|6 or more']
    assert m.momentum_keys({'outlets': 12, 'gained': 0, 'hours': 6.0})[0] == '11–15|none|6–12 hours in'
    assert m.momentum_keys({'outlets': 20, 'gained': 3, 'hours': 1.0}) == []  # gone wide
    assert m.momentum_keys({'outlets': 8, 'gained': 3, 'hours': 12.0}) == []  # no longer young


def test_table_counts_each_story_once_a_cell():
    tbl = m.build(history(), NOW, WIRES)
    cells = tbl['momentum']['cells']
    # A fast story sits in this cell at hours 0 and 1, and counts once
    assert cells['7 or fewer|6 or more|in their first 3 hours'] == {'n': 25, 'hit': 20}
    assert cells['7 or fewer|6 or more'] == {'n': 25, 'hit': 20}
    # The slow ones, and the fast ones that went flat once their joiners left the three-run window
    assert cells['7 or fewer|none|in their first 3 hours'] == {'n': 45, 'hit': 0}
    assert tbl['momentum']['base'] == {'n': 65, 'hit': 20}
    assert tbl['stories'] == 65


def test_table_leaves_out_young_stories():
    young = [fast(900 + i, NOW - 10 * H) for i in range(30)]
    tbl = m.build(history() + young, NOW, WIRES)
    assert tbl['stories'] == 65
    assert tbl['momentum']['cells']['7 or fewer|6 or more']['n'] == 25


def test_small_cells_merge_then_say_nothing():
    cells = {'a|b|c': {'n': m.MIN_STORIES - 1, 'hit': 5}, 'a|b': {'n': 40, 'hit': 10}}
    found = m.lookup(cells, ['a|b|c', 'a|b'])
    assert (found['key'], found['level'], found['share']) == ('a|b', 1, 0.25)
    cells['a|b']['n'] = m.MIN_STORIES - 1
    assert m.lookup(cells, ['a|b|c', 'a|b']) is None
    assert m.lookup({}, []) is None


def test_no_badge_from_a_small_history():
    tbl = m.build(history(n_fast=15, n_fast_flat=4), NOW, WIRES)  # 19 fast stories: under MIN_STORIES
    assert m.badge(tbl, fast(1, NOW), NOW) is None


def test_badge_words():
    tbl = m.build(history(), NOW, WIRES)
    line = m.badge(tbl, fast(1, NOW), NOW)
    assert (line['emoji'], line['label'], line['kind']) == ('📈', 'gaining fast', 'fast')
    assert line['text'] == 'stories gathering like this went wide 8 times in 10 (25 stories)'
    assert line['title'].startswith('Of the 25 stories in the last 30 days that had 7 or fewer outlets with 6 or more '
                                    'new in the last three hourly runs, in their first 3 hours')
    assert '20 went on to reach 20 or more outlets; of all stories, 31% did' in line['title']
    assert m.badge(tbl, slow(2, NOW), NOW) is None  # a slow story says nothing (Oct 28: no "slow so far")
    assert m.badge(tbl, fast(3, NOW - 13 * H), NOW) is None  # an old story says nothing


def test_badge_says_nothing_near_the_base_rate():
    # Half the fast stories went wide, as half of all stories did
    tbl = m.build(history(n_fast=10, n_fast_flat=10, n_slow=0), NOW, WIRES)
    assert tbl['momentum']['cells']['7 or fewer|6 or more'] == {'n': 20, 'hit': 10}
    assert tbl['momentum']['base'] == {'n': 20, 'hit': 10}
    assert m.badge(tbl, fast(1, NOW), NOW) is None


def test_odds_in_plain_words():
    assert m.odds(8, 10) == '8 times in 10'
    assert m.odds(42, 52) == '8 times in 10'
    assert m.odds(1, 10) == 'about 1 time in 10'
    assert m.odds(1, 20) == 'about 1 time in 20'
    assert m.odds(9, 403) == 'about 1 time in 40'
    assert m.odds(1, 200) == 'less than 1 time in 100'
    assert m.odds(19, 20) == 'almost every time'
    assert m.odds(20, 20) == 'every time'
    assert m.odds(0, 20) == 'never'
    assert m.said('went wide', 0, 20) == 'never went wide'
    assert m.said('went wide', 3, 20) == 'went wide 2 times in 10'


def one_sided(sid, birth, side, crossed=True, bridge=None):
    """Five outlets of `side` (plus a center or wire outlet if bridge), and three from the other side five hours
    after birth if it crossed"""
    joins = [(-1, side, f'{side}{i}') for i in range(5)]
    if bridge == 'center':
        joins.append((-1, 'center', 'Middle'))
    elif bridge:  # AP leans left (AllSides), Reuters is center
        joins.append((-1, 'left' if bridge == 'AP' else 'center', bridge))
    if crossed:
        joins += [(5, m.OTHER[side], f'x{i}') for i in range(3)]
    return story(sid, birth, joins)


def crossing_history():
    old = NOW - td(days=5)
    out = []
    for side in ('left', 'right'):
        base = 0 if side == 'left' else 1000
        out += [one_sided(base + i, old + i * H, side, crossed=i < 15) for i in range(20)]  # 15 of 20 crossed
        out += [one_sided(base + 100 + i, old + i * H, side, crossed=i < 2, bridge='Reuters') for i in range(10)]
    return out


def test_side_state():
    s = one_sided(1, NOW, 'right', crossed=False, bridge='AP')  # AP leans left: one left outlet
    ss = m.side_state(s, NOW, WIRES)
    assert (ss['side'], ss['counts'], ss['wire'], ss['bridge']) == ('right', {'left': 1, 'center': 0, 'right': 5},
                                                                     ['AP'], True)
    assert m.side_state(one_sided(2, NOW, 'left'), NOW + 6 * H, WIRES) is None  # three right outlets: crossed
    few = story(3, NOW, [(0, 'left', f'l{i}') for i in range(4)] + [(0, None, 'u')])
    assert m.side_state(few, NOW, WIRES) is None  # four rated outlets aren't enough


def test_crossing_table_and_the_merge():
    tbl = m.build(crossing_history(), NOW, WIRES)
    cells = tbl['crossing']['cells']
    assert cells['left|no bridge|under 6 hours'] == {'n': 20, 'hit': 15}
    assert cells['right|no bridge|under 6 hours'] == {'n': 20, 'hit': 15}
    assert cells['left|bridge'] == {'n': 10, 'hit': 2}  # too few: the side's whole count speaks instead
    assert cells['left'] == {'n': 30, 'hit': 17}
    line = m.crossing(tbl, one_sided(1, NOW, 'left', crossed=False, bridge='Reuters'), NOW, WIRES)
    assert line['text'] == 'mostly-left stories had 3+ right-leaning outlets within a day 6 times in 10 (30 stories)'
    assert line['bridge'] == 'Reuters has it'


def test_crossing_words_are_the_same_both_ways():
    tbl = m.build(crossing_history(), NOW, WIRES)
    left = m.crossing(tbl, one_sided(1, NOW + 2 * H, 'left', crossed=False), NOW + 4 * H, WIRES)
    right = m.crossing(tbl, one_sided(2, NOW + 2 * H, 'right', crossed=False), NOW + 4 * H, WIRES)

    def flipped(text):
        return text.replace('left', '\0').replace('right', 'left').replace('\0', 'right')
    assert left['text'] == 'stories like this had 3+ right-leaning outlets within a day 8 times in 10 (20 stories)'
    assert right['text'] == flipped(left['text'])
    assert right['title'] == flipped(left['title'])
    assert (left['emoji'], right['emoji'], left['when'], left['bridge']) == ('🫏', '🐘', '2 hours',
                                                                            'no wire service or center outlet yet')
    assert m.crossing(tbl, one_sided(3, NOW - 25 * H, 'left', crossed=False), NOW, WIRES) is None  # a day old


def test_from_headlines_reads_a_story_page():
    s = m.from_headlines(5, NOW, [
        {'outlet': 'CNN', 'bias': -1, 'first': NOW + H}, {'outlet': 'CNN', 'bias': -1, 'first': NOW},
        {'outlet': 'Fox News', 'bias': 2, 'first': NOW}, {'outlet': 'Newsweek', 'bias': None, 'first': NOW},
        {'outlet': 'Google News', 'bias': None, 'first': NOW}, {'outlet': 'Reuters', 'bias': 0, 'first': None}])
    assert s['outlets'] == {'CNN': (NOW, 'left'), 'Fox News': (NOW, 'right'), 'Newsweek': (NOW, None)}


def test_table_is_kept_a_day(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'TABLE_FILE', str(tmp_path / 'momentum.json'))
    monkeypatch.setattr(m, '_made', {})
    monkeypatch.setattr(m.Config, 'debug', False)
    calls = []
    monkeypatch.setattr(m, 'load', lambda since=None, ids=None: calls.append(since) or history())
    first = m.table(NOW)
    assert m.table(NOW + 23 * H) is first and len(calls) == 1
    monkeypatch.setattr(m, '_made', {})
    assert m.table(NOW + 23 * H)['built'] == first['built']  # from the kept file
    assert m.table(NOW + 25 * H)['built'] == (NOW + 25 * H).isoformat(timespec='seconds') and len(calls) == 2
