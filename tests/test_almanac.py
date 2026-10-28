"""The Election Almanac (app/analysis/almanac.py, app/site/page_almanac.py): the seal, the scoring, the page."""
import copy
import json
from datetime import date, datetime

import pytest
from bs4 import BeautifulSoup

from app.analysis import almanac
from app.site.page_almanac import AlmanacPage


def row(motif, day, kind='shows', side=None, teller='S'):
    return {'motif': motif, 'name': motif, 'genre': 'Theories', 'claim': f'{motif} {day}', 'key': f'{motif}{day}',
            'kind': kind, 'teller': teller, 'side': side, 'date': day, 'story': None, 'url': ''}


def forecast(**kw) -> dict:
    """A small forecast in the tracked file's shape: two motifs and a frozen seal"""
    f = {'about': 'test', 'dates': {'baseline': ['2026-10-03', '2026-10-26'], 'window': ['2026-11-03', '2026-11-09'],
                                    'freeze_by': '2026-11-03T00:00:00-05:00', 'count': '2026-11-17'},
         'surge': {'lift': 2, 'floor': 3}, 'side_floor': 3, 'base_rate': 0.25, 'rules': [],
         'forecasts': [{'id': 'M1', 'name': 'Red mirage', 'category': 'count and result', 'p_surge': 0.75,
                        'lead_side': 'left', 'lead_sides': ['left'], 'why': '', 'oct_tellings': 1, 'oct_share_pct': 1},
                       {'id': 'M2', 'name': 'Rigged election', 'category': 'integrity', 'p_surge': 0.5,
                        'lead_side': 'right if D; left if R', 'lead_sides': {'D': ['right'], 'R': ['left']},
                        'why': '', 'oct_tellings': 1, 'oct_share_pct': 1}],
         'answer_calls': [{'p': 0.4, 'motifs': ['M1', 'M2'], 'test': 'share_exceeds', 'call': 'M1 beats M2'},
                          {'p': 0.6, 'motifs': ['M9', 'M1'], 'test': 'prebunk_first', 'call': 'pre-bunked'}],
         'brennan': {'title': 't', 'by': 'b', 'date': '2026-10-09', 'themes': [{'theme': 'Machines', 'motifs': ['M2', 'M9']}]},
         'names': {'M9': 'Ballot dump'}, 'results': {'house': None}, 'frozen': None}
    f.update(kw)
    f['frozen'] = {'at': '2026-11-02T20:00:00-05:00', 'sha256': almanac.digest(f), 'late': False}
    return f


# October: 100 tellings, M1 once (1%), M2 ten times (10%). Shows by side: left 40, right 40, center 20
OCTOBER = ([row('M1', '2026-10-10', side='left')] + [row('M2', '2026-10-12', side='right') for _ in range(10)]
           + [row('X', '2026-10-15', side='left') for _ in range(39)] + [row('X', '2026-10-15', side='right') for _ in range(30)]
           + [row('X', '2026-10-15', side='center') for _ in range(20)])
# The window: 50 tellings. M1 4 (8%: surges), M2 5 (10%: doesn't). Left shows 20 in all, right 20, posts 10
WINDOW = ([row('M1', '2026-11-04', side='left') for _ in range(3)] + [row('M1', '2026-11-05', kind='posts')]
          + [row('M2', '2026-11-04', side='right') for _ in range(2)] + [row('M2', '2026-11-06', side='left') for _ in range(3)]
          + [row('X', '2026-11-04', side='left') for _ in range(14)] + [row('X', '2026-11-04', side='right') for _ in range(18)]
          + [row('X', '2026-11-04', kind='posts') for _ in range(9)])
ROWS = OCTOBER + WINDOW + [row('M2', '2026-11-12', side='right') for _ in range(30)]  # after the window: not counted


def test_the_digest_leaves_out_the_seal_and_the_results():
    f = forecast()
    before = almanac.digest(f)
    f['results']['house'] = 'D'
    f['frozen'] = None
    assert almanac.digest(f) == before
    f['forecasts'][0]['p_surge'] = 0.7
    assert almanac.digest(f) != before


def test_freezing_seals_once_and_an_edit_after_breaks_the_seal(tmp_path):
    path = tmp_path / 'almanac.json'
    f = forecast()
    f['frozen'] = None
    path.write_text(json.dumps(f), encoding='utf-8')
    seal = almanac.freeze(str(path), now=datetime.fromisoformat('2026-11-02T21:00:00-05:00'))
    assert seal['sha256'] == almanac.digest(f) and not seal['late']
    with pytest.raises(RuntimeError):
        almanac.freeze(str(path))  # never twice
    frozen = almanac.load(str(path))
    assert almanac.sealed(frozen) and almanac.stage(frozen, date(2026, 11, 1)) == 'frozen'
    frozen['results']['house'] = 'R'  # the House result may be set after: outside the seal
    assert almanac.sealed(frozen)
    edited = copy.deepcopy(frozen)
    edited['forecasts'][0]['p_surge'] = 0.9  # a silent edit
    with pytest.raises(almanac.BrokenSeal):
        almanac.sealed(edited)
    assert almanac.stage(edited, date(2026, 11, 20)) == 'broken'
    assert almanac.score(edited, ROWS, {'M1', 'M2'}, date(2026, 11, 20))['brier'] is None  # never scored
    html = AlmanacPage().template.render(AlmanacPage().context(edited, ROWS, {'M1', 'M2'}, {'M1', 'M2'}, date(2026, 11, 20)))
    assert 'SEAL BROKEN' in html


def test_a_late_freeze_is_marked(tmp_path):
    path = tmp_path / 'almanac.json'
    f = forecast()
    f['frozen'] = None
    path.write_text(json.dumps(f), encoding='utf-8')
    assert almanac.freeze(str(path), now=datetime.fromisoformat('2026-11-03T06:00:00-05:00'))['late']


def test_the_tracked_forecast_is_whole_and_its_seal_holds():
    f = almanac.load()
    almanac.sealed(f)  # raises if it was edited after freezing: the pre-commit hook runs this test
    ids = [x['id'] for x in f['forecasts']]
    assert len(ids) == len(set(ids)) == 30
    for x in f['forecasts']:
        assert 0 < x['p_surge'] < 1 and x['why'] and x['category']
        spec = x['lead_sides']
        for sides in (spec.values() if isinstance(spec, dict) else [spec or []]):
            assert set(sides) <= set(almanac.SIDES)
    assert {c['test'] for c in f['answer_calls']} <= {'counter_follows', 'both_by_sides', 'prebunk_first',
                                                      'share_exceeds', 'mirror_sides'}
    assert f['results']['house'] in (None, 'D', 'R')


def test_nothing_is_scored_before_the_window_or_for_a_draft():
    f = forecast()
    assert almanac.score(f, ROWS, {'M1', 'M2'}, date(2026, 11, 2))['brier'] is None
    draft = dict(f, frozen=None)
    assert almanac.stage(draft, date(2026, 11, 20)) == 'draft'
    assert almanac.score(draft, ROWS, {'M1', 'M2'}, date(2026, 11, 20))['motifs'] == {}


def test_surges_brier_and_skill():
    s = almanac.score(forecast(), ROWS, {'M1', 'M2'}, date(2026, 11, 17))
    assert s['stage'] == 'scored' and not s['provisional']
    assert s['window_n'] == 50 and s['baseline_n'] == 100
    m1, m2 = s['motifs']['M1'], s['motifs']['M2']
    assert (m1['n'], m1['share'], m1['surge']) == (4, 0.08, 1)  # 8x its October share, 4 tellings
    assert (m2['n'], m2['share'], m2['surge']) == (5, 0.1, 0)  # its October share again
    assert s['brier'] == pytest.approx(((0.75 - 1) ** 2 + 0.5 ** 2) / 2)
    assert s['brier_ref'] == pytest.approx(((0.25 - 1) ** 2 + 0.25 ** 2) / 2)
    assert s['skill'] == pytest.approx(1 - 0.15625 / 0.3125)


def test_the_floor_holds_a_rare_motif_back():
    rows = OCTOBER + [r for r in WINDOW if not (r['motif'] == 'M1' and r['kind'] == 'shows')][:-2] \
        + [row('M1', '2026-11-04', side='left')]
    s = almanac.score(forecast(), rows, {'M1', 'M2'}, date(2026, 11, 17))
    assert s['motifs']['M1']['n'] == 2 and s['motifs']['M1']['share'] >= 0.02 and s['motifs']['M1']['surge'] == 0


def test_side_calls_by_rate_and_the_house_branch():
    # M2 in the window: right shows 2 of their 20 (10%), left shows 3 of their 20 (15%): left leads
    s = almanac.score(forecast(), ROWS, {'M1', 'M2'}, date(2026, 11, 17))
    assert s['motifs']['M1']['lead'] == 'left' and s['motifs']['M1']['side_hit'] is True
    assert s['motifs']['M2']['lead'] == 'left' and s['motifs']['M2']['side_hit'] is None  # House not called yet
    assert s['sides'] == {'hits': 1, 'scored': 1, 'persistence': 0}  # M1 had too few October show tellings
    s = almanac.score(forecast(results={'house': 'R'}), ROWS, {'M1', 'M2'}, date(2026, 11, 17))
    assert s['motifs']['M2']['side_hit'] is True and s['sides']['scored'] == 2
    s = almanac.score(forecast(results={'house': 'D'}), ROWS, {'M1', 'M2'}, date(2026, 11, 17))
    assert s['motifs']['M2']['side_hit'] is False and s['motifs']['M2']['oct_lead'] == 'right'
    assert s['sides'] == {'hits': 1, 'scored': 2, 'persistence': 0}


def test_during_the_window_the_numbers_are_provisional_and_cut_at_today():
    s = almanac.score(forecast(), ROWS, {'M1', 'M2'}, date(2026, 11, 4))
    assert s['stage'] == 'scoring' and s['provisional'] and s['through'] == '2026-11-04'
    assert s['motifs']['M1']['n'] == 3 and s['motifs']['M2']['n'] == 2
    later = almanac.score(forecast(), ROWS, {'M1', 'M2'}, date(2026, 11, 12))
    assert later['provisional'] and later['through'] == '2026-11-09' and later['motifs']['M2']['n'] == 5


def test_answer_calls():
    s = almanac.score(forecast(), ROWS, {'M1', 'M2'}, date(2026, 11, 17))
    assert s['answers'][0]['result'] == 'miss'  # M1 4 vs M2 5
    assert s['answers'][1]['result'] is None  # M9 isn't public
    win = almanac.period(ROWS + [row('M9', '2026-11-05', kind='posts')], '2026-11-03', '2026-11-09')
    pre = {'p': 0.6, 'motifs': ['M9', 'M1'], 'test': 'prebunk_first'}
    assert almanac.answer(pre, win, {'M1', 'M9'}, 3)['result'] == 'hit'  # M1 first told Nov 4, M9 Nov 5
    follows = {'p': 0.6, 'motifs': ['M2', 'M1'], 'test': 'counter_follows'}
    assert almanac.answer(follows, win, {'M1', 'M2'}, 3)['result'] == 'hit'  # M1's shows are all left
    mirror = {'p': 0.5, 'motifs': ['M2', 'M1'], 'test': 'mirror_sides'}
    assert almanac.answer(mirror, win, {'M1', 'M2'}, 3)['result'] == 'miss'  # left shows lead M2, not right


def test_the_page_links_public_motifs_only_and_shows_its_stage():
    page = AlmanacPage()
    f = forecast()
    soup = BeautifulSoup(page.template.render(page.context(dict(f, frozen=None), ROWS, {'M1', 'M2'}, {'M1', 'M2'},
                                                           date(2026, 10, 28))), 'html.parser')
    assert 'DRAFT' in soup.select_one('.almanac-status').text
    assert not soup.select('.almanac-outcome')  # nothing scored before the window
    assert len(soup.select('svg.almanac-bar')) == 2
    unlinked = [s.text for s in soup.select('.almanac-unlinked')]
    assert '🧩 Ballot dump' in unlinked and not soup.select('a[href="motif-m9.html"]')
    soup = BeautifulSoup(page.template.render(page.context(f, ROWS, {'M1', 'M2'}, {'M1', 'M2'}, date(2026, 11, 5))),
                         'html.parser')
    status = soup.select_one('.almanac-status').text
    assert 'SCORING' in status and f['frozen']['sha256'] in status
    assert 'so far' in soup.select_one('.almanac-outcome').text
