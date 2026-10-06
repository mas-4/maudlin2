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


def test_stickers_count_each_stage_it_reached():
    from app.site.page_story import stickers
    st = story()
    st['id'], st['saga'] = 7, {'parts': [{'id': 5}, {'id': 7}, {'id': 9}]}
    unique = list({o['outlet']: o for o in outlets(st)}.values())
    got = stickers(st, unique, {'left': 1, 'center': 0, 'right': 1, 'unrated': 1}, {'total': '6 min'},
                   [{'show': 'NPR'}], [{'people': 4}, {'people': 3}], [], st['snapshots'])
    by = {k['emoji']: k for k in got}
    assert by['📰']['big'] == 3 and by['📺']['big'] == '6 min' and by['📻']['small'] == 'radio newscast'
    assert by['🧶']['big'] == 7 and by['🧵']['big'] == '2 of 3' and '🔎' not in by


def test_a_saga_draws_a_lane_per_part_and_coverage_stacked_by_part():
    parts = [{'story': 1, 'label': 'Governor appoints a prosecutor', 'first': T, 'last': T + td(hours=30), 'outlets': 20,
              'snapshots': [{'at': T + td(hours=h), 'outlets': 10} for h in (0, 1, 2)]},
             {'story': 2, 'label': 'Faculty vote <no confidence>', 'first': T + td(hours=20), 'last': T + td(hours=26),
              'outlets': 8, 'snapshots': [{'at': T + td(hours=2), 'outlets': 4}]}]
    radio = [{'story': 2, 'at': sc.EASTERN.localize(datetime(2026, 10, 7, 10)), 'show': 'NPR', 'when': 'Oct 7, 10 AM', 'place': 1}]
    svg = sc.saga_lanes(parts, [], radio, [], {})
    assert '1. Governor appoints a prosecutor' in svg and '2. Faculty vote &lt;no confidence&gt;' in svg
    assert '📻 radio' in svg and f'fill="{sc.PART_COLORS[1]}"' in svg  # the newscast in its part's color
    cov = sc.saga_coverage(parts)
    assert cov['peak'] == 14 and cov['svg'].count('<polygon') == 2
