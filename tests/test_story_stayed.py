"""Who stayed on a story (app/site/page_story.stayed): the median time each side's rated outlets kept it on their
front pages."""
from datetime import datetime, timedelta as td

from app.site.page_story import stayed

T0 = datetime(2026, 10, 20, 12)


def h(outlet, bias, start=0, hours=10):
    return {'outlet': outlet, 'bias': bias, 'first': T0 + td(hours=start), 'seen': T0 + td(hours=start + hours)}


def test_the_side_that_kept_it_up_a_day_longer_gets_a_line():
    heads = [h('L1', -2, hours=10), h('L2', -1, hours=20), h('L3', -2, hours=30),
             h('R1', 2, hours=50), h('R2', 1, hours=60), h('R3', 2, hours=70),
             h('C', 0, hours=500), h('Unrated', None, hours=500)]  # center and unrated outlets don't count
    s = stayed(heads)
    assert s == {'left': 20, 'right': 60, 'left_n': 3, 'right_n': 3, 'longer': 'right', 'hours': 40}


def test_an_outlets_stay_runs_from_its_first_headline_to_its_last_sighting():
    heads = [h('L1', -1, start=0, hours=5), h('L1', -1, start=30, hours=10),  # a follow-up headline: 0 to 40 h
             h('L2', -1, hours=40), h('L3', -1, hours=40),
             h('R1', 1, hours=5), h('R2', 1, hours=5), h('R3', 1, hours=5), h('R4', 1, hours=7)]
    s = stayed(heads)
    assert s['left'] == 40 and s['right'] == 5 and s['longer'] == 'left' and s['right_n'] == 4


def test_a_small_gap_says_nothing_and_too_few_outlets_say_nothing_at_all():
    even = [h(f'L{n}', -1, hours=20) for n in range(3)] + [h(f'R{n}', 1, hours=40) for n in range(3)]
    assert stayed(even)['longer'] is None  # 20 hours apart: under a day
    few = [h(f'L{n}', -1, hours=10) for n in range(2)] + [h(f'R{n}', 1, hours=90) for n in range(5)]
    assert stayed(few) is None
    unseen = [dict(h(f'L{n}', -1), seen=None) for n in range(3)] + [h(f'R{n}', 1, hours=30) for n in range(3)]
    assert stayed(unseen)['left'] == 0  # never seen again after its first sighting
