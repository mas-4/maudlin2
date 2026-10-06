from datetime import datetime, timedelta as td

from app.site import story_charts as sc

T = datetime(2026, 10, 6, 12)  # 8 AM Eastern


def story():
    heads = [{'outlet': 'Left Daily', 'bias': -2, 'title': 'A', 'first': T, 'last': T + td(hours=5)},
             {'outlet': 'Right Times', 'bias': 2, 'title': 'B', 'first': T + td(hours=2), 'last': T + td(hours=5)},
             {'outlet': 'Right Times', 'bias': 2, 'title': 'B, again', 'first': T + td(hours=3), 'last': T + td(hours=5)},
             {'outlet': 'Unrated & Co', 'bias': None, 'title': 'C <b>', 'first': T + td(hours=4), 'last': T + td(hours=5)}]
    snaps = [{'at': T + td(hours=h), 'outlets': 0} for h in range(6)]
    return {'first': T, 'last': T + td(hours=5), 'headlines': heads, 'snapshots': snaps}


def outlets(st):
    return [{'outlet': h['outlet'], 'bias': h['bias'], 'short': h['outlet']} for h in st['headlines']]


def test_ticks_are_eastern_hours_with_the_day_first():
    labels = [label for _, label in sc.ticks(T, T + td(hours=5))]
    assert labels == ['Oct 6, 9 AM', '10 AM', '11 AM', '12 PM', '1 PM']
    assert [label for _, label in sc.ticks(T, T + td(days=2))][0].startswith('Oct 6')
    assert len(sc.ticks(T, T + td(days=2))) <= 7


def test_coverage_is_stacked_by_lean():
    st = story()
    chart = sc.by_lean(st, outlets(st))
    assert chart['peak'] == 3
    assert [g['name'] for g in chart['legend']] == ['left', 'right', 'not rated']
    assert chart['svg'].count('<polygon') == 3


def test_timeline_has_a_row_per_outlet_in_pickup_order_and_lanes_for_what_it_has():
    st = story()
    radio = [{'at': sc.EASTERN.localize(datetime(2026, 10, 6, 10)), 'show': 'NPR', 'when': 'Oct 6, 10 AM',
              'place': 1, 'of': 5}]
    svg = sc.timeline(st, outlets(st), [], radio, None, {})
    assert svg.index('Left Daily') < svg.index('Right Times') < svg.index('Unrated &amp; Co')
    assert 'C &lt;b&gt;' in svg  # titles escaped
    assert '📻 radio' in svg and '📺 TV' not in svg and '🧶 online' not in svg
    assert svg.count('<circle') == 2  # one new headline, one newscast
    assert sc.timeline({**st, 'headlines': []}, [], [], [], None, {}) is None
