"""The Oct 28 redo, group F: the archive's calendar, the court's docket strips, the aisle's divide by week."""
import app.site.archive as ar


def point(at, score, story=1, label='A story', outlets=30, active=80):
    return {'at': at, 'score': score, 'story': story, 'label': label, 'outlets': outlets, 'active': active}


def test_a_days_number_is_its_average_hour_and_its_shade_and_emoji_agree():
    # Oct 12 ET: 14:00 and 20:00 UTC; 03:00 UTC on Oct 13 is still Oct 12 in the evening, Eastern
    scores = ar.day_scores([point('2026-10-12T14:00:00', 0.2), point('2026-10-12T20:00:00', 0.6, label='Peak'),
                            point('2026-10-13T03:00:00', 0.4), point('2026-10-13T15:00:00', 0.27)])
    assert scores['2026-10-12']['score'] == 0.4 and scores['2026-10-12']['hours'] == 3
    assert scores['2026-10-12']['peak']['label'] == 'Peak'
    assert [ar.shade(s) for s in (None, 0.1, 0.25, 0.3, 0.44, 0.45)] == [0, 1, 2, 3, 4, 5]
    assert [ar.TIER_EMOJI[ar.tier(s)] for s in (0.1, 0.3, 0.5)] == ['🌴', '📰', '🚨']
    key = ar.shade_key()
    assert [k['words'] for k in key] == ['under 0.25', '0.25–0.29', '0.30–0.34', '0.35–0.44', '0.45 and up']
    assert [k['step'] for k in key] == [1, 2, 3, 4, 5]


def test_the_calendar_is_month_by_month_with_a_tile_a_day_since_the_first_edition():
    published = [{'day': '2026-10-04', 'path': '/2026/10/04/', 'label': 'Slow news day…', 'emoji': '🌴🐢',
                  'story': 'Coast <Guard> search', 'stories': 42},
                 {'day': '2026-10-06', 'path': '/2026/10/06/', 'label': None}]
    scores = ar.day_scores([point('2026-10-04T16:00:00', 0.5, label='Coast Guard'), point('2026-10-30T16:00:00', 0.2)])
    [october] = ar.calendar(published, scores, '2026-10-07')
    assert october['name'] == 'October 2026'
    tiles = [t for week in october['weeks'] for t in week if t]
    assert [t['day'] for t in tiles] == [4, 5, 6, 7]  # from the first edition to today
    first, gap, unscored, today = tiles
    assert first['href'] == '/2026/10/04/' and first['shade'] == 5 and first['emoji'] == '🚨'
    assert 'Coast <Guard> search' in first['tip'] and '42 stories' in first['tip'] and 'closed the day: 🌴🐢' in first['tip']
    assert 'about 5 in 10 front pages' in first['tip'] and first['head'] == 'Sunday, October 4'
    assert gap['missing'] and gap['href'] is None
    assert unscored['shade'] == 0 and unscored['emoji'] == '❔'
    assert today['today'] and today['href'] == 'index.html' and 'today, so far' in today['head']
    # Oct 4, 2026 is a Sunday: the week before it, with no tiles, is left out
    assert october['weeks'][0][0]['day'] == 4 and october['weeks'][0][4:] == [None] * 3 and len(october['weeks']) == 1
    assert ar.calendar([], {}, '2026-11-02')[0]['name'] == 'November 2026'


def test_biggest_and_slowest_days_answer_each_other_colored_by_weekday_or_weekend():
    days = [f'2026-10-{d:02d}' for d in range(5, 19)]
    published = [{'day': d, 'path': f"/{d.replace('-', '/')}/", 'story': f'Story {d}'} for d in days]
    scores = ar.day_scores([point(f'{d}T16:00:00', 0.2 + i / 50) for i, d in enumerate(days)])
    big, slow = ar.day_boards(published, scores)
    assert [r['href'] for r in big['rows']][0] == '/2026/10/18/' and len(big['rows']) == ar.BOARD_DAYS
    assert slow['rows'][0]['href'] == '/2026/10/05/'
    assert not {r['href'] for r in big['rows']} & {r['href'] for r in slow['rows']}
    sunday = next(r for r in big['rows'] if r['href'] == '/2026/10/18/')
    assert sunday['ink'] == ar.WEEKEND_INK and sunday['mark'] == '🛋️' and sunday['name'].startswith('Sun Oct 18: ')
    assert next(r for r in slow['rows'] if r['href'] == '/2026/10/05/')['ink'] == ar.WEEKDAY_INK
    few = ar.day_boards(published[:3], scores)  # few days: each on one board only
    assert len(few[0]['rows']) == 3 and few[1]['rows'] == []


def test_a_cases_stage_comes_from_its_dates_and_other_news_by_what_its_headlines_report():
    from datetime import date

    from app.site import page_court as pc
    today = date(2026, 10, 28)
    assert [pc.case_stage(d, today) for d in (None, date(2026, 11, 2), date(2026, 10, 28))] == \
        ['case taken', 'to be argued', 'argued']
    assert pc.news_kind(['ruling', 'emergency order', 'the justices']) == 'orders'
    assert pc.news_kind(['the justices', 'term preview']) == 'justices'  # a tie: the first kind
    assert pc.news_kind([]) == 'other' and pc.news_kind(['other', 'weird']) == 'other'
    assert pc.reported([('ruling', 6), ('term preview', 1)]) == '🔨 a ruling 6 · 🗓️ a preview of the term 1'
    assert pc.lean_split({'left': 3, 'right': 1, 'center': 4}) == 0.75 and pc.lean_split({'center': 2}) is None
    assert pc.sides_text({'left': 1, 'unrated': 2}) == '1 left-leaning, 2 not rated'
    assert [k['name'] for k in pc.key_of(pc.CASE_STAGES, {'argued', 'case taken'})] == ['case taken', 'argued']
