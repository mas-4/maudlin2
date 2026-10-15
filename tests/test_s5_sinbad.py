"""scripts/experiments/s5_sinbad.py (Sinbad, Oct 15): the replay asks where production would (a titled story due a new
title, 3 headlines a side) and goes on in the new part after a split; the person's blind verdicts are kept."""
import json
import sys
from datetime import datetime as dt, timedelta as td

sys.path.insert(0, 'scripts/experiments')
import lab  # noqa: E402
import s5_sinbad as f  # noqa: E402

T0 = dt(2026, 10, 6)


def story(heads: list[tuple[float, str]], snaps: list[tuple[float, int]]) -> dict:
    """Headlines and snapshots at hours after T0"""
    return {'headlines': [[i, (T0 + td(hours=h)).isoformat(), x] for i, (h, x) in enumerate(heads)],
            'snaps': [[(T0 + td(hours=h)).isoformat(), n] for h, n in snaps], 'saga': None, 'label': 'x'}


def test_a_split_starts_a_part_and_the_walk_goes_on_in_it():
    heads = [(0.5, f'plan {i}') for i in range(4)] + [(13.5, f'cancel {i}') for i in range(4)] + \
        [(26.5, f'react {i}') for i in range(4)]
    s = story(heads, [(h, 5) for h in range(1, 40)])
    asked = []
    checks = f.walk('last', s, T0.isoformat(), lambda c: asked.append(c) or (c['b'][0].startswith('react')))
    assert [c['at'][11:13] for c in checks] == ['14', '03']  # the first run 12 hours on with news since
    assert checks[0]['same'] is False and checks[0]['part_start'] is None
    assert all(x.startswith('cancel') for x in checks[1]['a']) and checks[1]['part_start'] == (T0 + td(hours=1)).isoformat()
    assert [p['first'][0] for p in f.parts_of(s, checks)] == ['plan 0', 'cancel 0']


def test_a_doubled_story_is_asked_before_its_title_is_twelve_hours_old():
    heads = [(0.5, f'plan {i}') for i in range(4)] + [(5.5, f'cancel {i}') for i in range(4)]
    s = story(heads, [(1, 5), (2, 5), (6, 12), (7, 12)])
    checks = f.walk('last', s, T0.isoformat(), lambda c: True)
    assert len(checks) == 1 and checks[0]['due'] == 'grown'


def test_too_few_headlines_a_side_ask_nothing():
    heads = [(0.5, 'plan 0'), (0.6, 'plan 1'), (13.5, 'cancel 0'), (13.6, 'cancel 1'), (13.7, 'cancel 2')]
    s = story(heads, [(h, 5) for h in range(1, 20)])
    assert f.walk('last', s, T0.isoformat(), lambda c: False) == []


def test_the_founding_arm_shows_the_parts_first_headlines():
    heads = [(0.5 + i / 10, f'plan {i}') for i in range(6)] + [(13.5 + i / 10, f'cancel {i}') for i in range(4)]
    s = story(heads, [(h, 5) for h in range(1, 20)])
    first = f.walk('first', s, T0.isoformat(), lambda c: True)[0]
    last = f.walk('last', s, T0.isoformat(), lambda c: True)[0]
    assert first['a'][0] == 'plan 0' and last['a'][0] == 'plan 5' and last['b'][0] == 'cancel 3'


def test_a_blind_verdict_is_kept_and_only_for_the_blind_set(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, 'EXP', str(tmp_path))
    (tmp_path / 's5_sinbad.json').write_text(json.dumps({'blind': [{'key': 'last|1|a|b', 'n': 1}]}))
    lab.verdict('S5', 'last|1|a|b', 'two')
    assert json.loads((tmp_path / 's5_sinbad.json').read_text())['person'] == {'last|1|a|b': 'two'}
    lab.verdict('S5', 'last|1|a|b', None)
    assert json.loads((tmp_path / 's5_sinbad.json').read_text())['person'] == {}
    for key, value in (('last|2|a|b', 'two'), ('last|1|a|b', 'A')):
        try:
            lab.verdict('S5', key, value)
            raise AssertionError('taken')
        except ValueError:
            pass
