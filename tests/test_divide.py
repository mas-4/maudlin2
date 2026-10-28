"""The weekly divide index (app/analysis/divide.py): how different left and right shows' motifs are each week, less
what random splits of the same shows give."""
from datetime import date

import numpy as np
import pytest

from app.analysis import divide


def row(motif, side, teller, day='2026-10-21'):
    return {'motif': motif, 'name': motif.title(), 'side': side, 'teller': teller, 'date': day, 'kind': 'shows',
            'speaker': 'host', 'url': ''}


def test_jsd_is_zero_for_the_same_mix_and_one_bit_for_nothing_shared():
    assert divide.jsd(np.array([2, 4, 0]), np.array([1, 2, 0]))[0] == pytest.approx(0)
    assert divide.jsd(np.array([3, 0]), np.array([0, 5]))[0] == pytest.approx(1)
    # half the mass shared: p = (1/2, 1/2, 0), q = (0, 1/2, 1/2) gives 0.5 bits
    assert divide.jsd(np.array([1, 1, 0]), np.array([0, 1, 1]))[0] == pytest.approx(0.5)


def test_weeks_run_tuesday_to_monday():
    assert divide.week_of('2026-11-03') == '2026-11-03'  # election day starts a week
    assert divide.week_of('2026-11-09') == '2026-11-03'
    assert divide.week_of('2026-11-02') == '2026-10-27'


def sorted_week(split: bool, shows: int = 6, each: int = 12) -> list[dict]:
    """`shows` left and `shows` right shows; split: each side tells its own motifs, else every show tells all alike"""
    rows = []
    for side in ('left', 'right'):
        for s in range(shows):
            for n in range(each):
                motif = f'{side}{n % 4}' if split else f'm{n % 4}'
                rows.append(row(motif, side, f'{side}-show-{s}'))
    return rows


def test_sides_that_tell_different_stories_beat_the_shuffled_floor_and_alike_ones_dont():
    apart = divide.gap(sorted_week(split=True))
    assert apart['jsd'] == pytest.approx(1) and apart['index'] > 0.5 and apart['jsd'] > apart['floor_p95']
    alike = divide.gap(sorted_week(split=False))
    assert alike['jsd'] == pytest.approx(0) and alike['index'] <= 0
    assert alike['left_shows'] == alike['right_shows'] == 6 and alike['left'] == 72


def test_one_loud_show_alone_doesnt_make_a_divide():
    # Every show tells its own motifs: the sides differ only as much as any two piles of shows do
    rows = [row(f'own-{side}{s}', side, f'{side}{s}') for side in ('left', 'right') for s in range(6) for _ in range(10)]
    g = divide.gap(rows)
    assert abs(g['index']) < 0.05


def test_a_small_week_isnt_measured_and_the_week_in_progress_is_left_out():
    assert divide.gap(sorted_week(split=True, shows=3)) is None  # too few shows a side
    assert divide.gap(sorted_week(split=True, each=3)) is None  # too few tellings a side
    rows = sorted_week(split=True) + [dict(r, date='2026-10-27') for r in sorted_week(split=True)]
    out = divide.weekly(rows, today=date(2026, 10, 28))
    assert [w['week'] for w in out['weeks']] == ['2026-10-20']
    assert out['latest']['week'] == '2026-10-20' and out['weeks'][0]['partial'] is False


def test_the_latest_weeks_lists_split_shared_from_one_sided():
    rows = sorted_week(split=False)
    rows += [row('ours', 'left', f'left-show-{s}') for s in range(4) for _ in range(5)]
    rows += [row('theirs', 'right', f'right-show-{s}') for s in range(4) for _ in range(5)]
    c = divide.contrasts(rows)
    assert c['mostly_left'][0]['name'] == 'Ours' and c['mostly_right'][0]['name'] == 'Theirs'
    assert {m['name'] for m in c['shared']} == {'M0', 'M1', 'M2', 'M3'}
