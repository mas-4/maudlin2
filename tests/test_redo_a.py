"""The Oct 28 redo, group A: the folklore page's motif lists as paired ranked strips, the motif index's slim cards and
the motif pages' claims by side and shows as a ranked strip."""
from datetime import date

from app.site import page_folklore as pf
from app.site import page_motifs as pm


def entry(mid, name, genre, dates, **kw):
    return {'id': mid, 'name': name, 'genre': genre, 'note': f'{name} note', 'count': len(dates), 'recent': 0,
            'claims': [{'claim': f'{name} {i}', 'date': d, 'source': 'narrative'} for i, d in enumerate(dates)],
            'sources': [('people online', len(dates))], 'rests_on': [], 'under': [], 'groups': [], **kw}


def show_row(motif, show, side, speaker='host', kind='shows', key='k'):
    return {'motif': motif, 'kind': kind, 'teller': show, 'side': side, 'speaker': speaker, 'key': key + show,
            'url': f'https://pod/{show}', 'date': '2026-10-20'}


def test_gone_quiet_is_told_a_lot_before_and_little_since():
    today = date(2026, 10, 28)
    quiet = entry('M1', 'Hushed', 'Plots', ['2026-10-10'] * 6 + ['2026-10-25'])
    loud = entry('M2', 'Still going', 'Plots', ['2026-10-10'] * 6 + ['2026-10-25', '2026-10-26'])
    small = entry('M3', 'Never much', 'Plots', ['2026-10-10'] * 4)
    old = entry('M4', 'Long ago', 'Plots', ['2026-09-20'] * 9)  # before the two weeks: not "lately quiet"
    out = pf.gone_quiet([quiet, loud, small, old], today)
    assert [(q['entry']['id'], q['before'], q['since']) for q in out] == [('M1', 6, 1)]


def test_only_the_shows_say_needs_three_shows_and_nobody_else():
    entries = {m: entry(m, m, 'Theories', ['2026-10-20']) for m in ('M1', 'M2', 'M3')}
    rows = [show_row('M1', s, 'right') for s in 'ABC'] \
        + [show_row('M2', s, 'left') for s in 'ABCD'] + [show_row('M2', 'people online', None, kind='posts')] \
        + [show_row('M3', s, 'left') for s in 'AB']
    out = pf.only_shows(entries, pf.motif_stats(rows))
    assert [o['entry']['id'] for o in out] == ['M1']


def test_the_boards_come_in_answering_pairs_with_genre_colors_and_a_lean_split():
    lawfare = entry('M619', 'Lawfare', 'Plots', ['2026-10-27'] * 3)
    voters = entry('M9', 'Work horse', 'Archetypes', ['2026-10-27'])
    shelf = {'entries': [lawfare, voters], 'lately': [{**lawfare, 'recent': 3}], 'lately_days': 3}
    checking = {'unchecked': [{'id': 'M619', 'name': 'Lawfare', 'genre': 'Plots', 'told': 3, 'checked': 0, 'posts': 1,
                               'left': 1, 'right': 3}], 'checked': []}
    rows = [show_row('M619', 'Left pod', 'left'), *[show_row('M619', s, 'right') for s in ('R1', 'R2', 'R3')],
            show_row('M619', 'Clip pod', 'left', speaker='clip')]  # a clip played isn't the show's own voice
    boards = pf.motif_boards(shelf, checking, [{'id': 'M9', 'name': 'Work horse', 'claims': 1}], rows)
    assert [b['key'] for b in boards] == ['unchecked', 'checked', 'lately', 'quiet', 'voters', 'shows']
    row = boards[0]['rows'][0]
    assert row['ink'] == '#a0522d' and row['mark'] == '📜'  # Plots' color and emoji
    assert row['split'] == 25  # one left show of four on either side
    assert row['tip'].startswith('Lawfare: 📜 Plots\nLawfare note')
    assert boards[4]['rows'][0]['split'] is None and boards[4]['rows'][0]['name'] == 'Work horse'
    assert boards[1]['rows'] == [] and boards[1]['empty'].startswith('🦗')


def test_a_slim_cards_bar_counts_each_show_once_by_its_lean():
    key = pm.motif_index.key
    e = entry('M1', 'Lawfare', 'Plots', [])
    e['claims'] = [{'claim': 'Told on shows', 'source': 'shows', 'date': '2026-10-27'},
                   {'claim': 'Told online', 'source': 'narrative', 'date': '2026-10-27'},
                   {'claim': 'Checked', 'source': 'Snopes', 'date': '2026-10-20'},
                   {'claim': 'Said in a room', 'source': 'Focus Group', 'date': '2026-10-20'}]
    tellers = {key('Told on shows'): [{'show': 'A', 'lean': 'left'}, {'show': 'B', 'lean': 'right'},
                                      {'show': 'C', 'lean': 'right'}, {'show': 'D', 'lean': 'crossover'}]}
    parts = pm.mix(e, tellers, {})
    assert [(p['key'], p['n']) for p in parts] == [('left', 1), ('right', 2), ('crossover', 1), ('online', 1),
                                                  ('checks', 1), ('voters', 1)]
    assert [p['key'] for p in parts] == [k for k, *_ in pm.MIX if k in {p['key'] for p in parts}]  # fixed order


def test_the_sparkline_is_three_weeks_of_claims_and_says_so():
    e = entry('M1', 'Lawfare', 'Plots', ['2026-10-28', '2026-10-28', '2026-10-10', '2026-10-01'])
    svg = str(pm.sparkline(e, date(2026, 10, 28)))
    assert 'aria-label="3 claims in the last three weeks, at most 2 a day"' in svg
    assert svg.count('<polyline') == 1 and ' 80,2"' in svg  # today, the top


def test_the_hover_card_holds_the_claims_the_card_no_longer_shows():
    e = entry('M1', 'Lawfare', 'Plots', ['2026-10-27'] * 12)
    e['claims'][0] = {'claim': 'x' * 400, 'source': 'Snopes', 'ref': 'https://snopes.example/1', 'date': '2026-10-27'}
    e['rests_on'] = [{'id': 'M2', 'name': 'Intimidation'}]
    h = pm.hover(e, [{'emoji': '🧶', 'n': 11, 'name': 'people online'}])
    assert len(h['c']) == pm.HOVER_CLAIMS and h['m'] == 12 - pm.HOVER_CLAIMS
    assert h['c'][0][1:] == ['Snopes', 'https://snopes.example/1'] and len(h['c'][0][0]) == pm.HOVER_CHARS
    assert h['x'] == ['🧶 11 people online'] and h['r'][0][1] == 'Intimidation'
