"""Who stayed on a story (app/site/page_story.stayed): the median time each side's rated outlets kept it on their
front pages."""
from datetime import datetime, timedelta as td

from app.site.page_story import stayed

T0 = datetime(2026, 10, 20, 12)


def h(outlet, bias, start=0, hours=10):
    return {'outlet': outlet, 'bias': bias, 'first': T0 + td(hours=start), 'seen': T0 + td(hours=start + hours)}


def side(prefix, bias, hours):
    return [h(f'{prefix}{n}', bias, hours=x) for n, x in enumerate(hours)]


def test_the_side_that_kept_it_up_a_day_longer_gets_a_line():
    heads = side('L', -1, [10, 15, 20, 25, 30]) + side('R', 1, [50, 55, 60, 65, 70]) + \
        [h('C', 0, hours=500), h('Unrated', None, hours=500)]  # center and unrated outlets don't count
    assert stayed(heads) == {'left': 20, 'right': 60, 'left_n': 5, 'right_n': 5, 'longer': 'right', 'hours': 40}


def test_an_outlets_stay_runs_from_its_first_headline_to_its_last_sighting():
    heads = [h('L0', -1, start=0, hours=5), h('L0', -1, start=30, hours=10)] + side('L', -1, [0, 40, 40, 40, 40])[1:] + \
        side('R', 1, [5, 5, 5, 7, 7])  # L0's follow-up headline: 0 to 40 h
    s = stayed(heads)
    assert s['left'] == 40 and s['right'] == 5 and s['longer'] == 'left' and s['right_n'] == 5


def test_small_gaps_and_too_few_outlets_say_nothing():
    assert stayed(side('L', -1, [20] * 5) + side('R', 1, [40] * 5))['longer'] is None  # under a day
    # a day and more, but a small part of a week-long story (Oct 28: noise on long stories)
    assert stayed(side('L', -1, [160] * 5) + side('R', 1, [190] * 5))['longer'] is None
    assert stayed(side('L', -1, [10] * 4) + side('R', 1, [90] * 5)) is None  # four left outlets: too few
    unseen = [dict(x, seen=None) for x in side('L', -1, [0] * 5)] + side('R', 1, [30] * 5)
    assert stayed(unseen)['left'] == 0  # never seen again after its first sighting
