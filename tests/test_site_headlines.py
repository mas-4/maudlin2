"""app/site/page_headlines.py: the front page's pure helpers and the HeadlinesPage methods that work on small
synthetic frames. No database, no language model and no embedding model: `embed`, `find_edits` and
`recent_investigations` are monkeypatched wherever a method reaches for them."""
import zlib
from datetime import datetime as dt, timedelta as td
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.site import page_headlines as ph
from app.site.common import j2env
from app.site.page_headlines import HeadlinesPage


def make_page(main_df=None, **context) -> HeadlinesPage:
    page = HeadlinesPage(SimpleNamespace(main_headline_df=main_df if main_df is not None else pd.DataFrame()))
    page.context.update(context)
    return page


class FakeEmbed:
    """Deterministic stand-in for the sentence embedder: a pseudo-random unit vector per text (near orthogonal to the
    others in 512 dimensions), unless the test pins a text's vector. Records every text it's asked about."""
    DIM = 512

    def __init__(self, pinned=None):
        self.pinned = dict(pinned or {})
        self.seen = []

    def vector(self, text):
        if text in self.pinned:
            v = np.asarray(self.pinned[text], dtype=float)
            return np.pad(v, (0, self.DIM - len(v)))
        v = np.random.default_rng(zlib.crc32(text.encode())).normal(size=self.DIM)
        return v / np.linalg.norm(v)

    def __call__(self, texts):
        texts = list(texts)
        self.seen.extend(texts)
        return np.array([self.vector(t) for t in texts])


def unit(i, dim=8):
    v = np.zeros(dim)
    v[i] = 1
    return v


def mix(a, b, cos):
    """A unit vector at cosine `cos` to unit vector `a`, in the plane of a and b (orthogonal unit vectors)."""
    return cos * a + np.sqrt(1 - cos ** 2) * b


# <editor-fold desc="small pure helpers">
@pytest.mark.parametrize('mood, emoji, word', [
    (-1.0, '⛈️', 'grim+'), (-0.6, '⛈️', 'grim+'), (-0.59, '🌧️', 'grim'), (-0.2, '🌧️', 'grim'),
    (-0.19, '🍞', 'plain'), (0.0, '🍞', 'plain'), (0.19, '🍞', 'plain'), (0.2, '🌤️', 'upbeat'),
    (0.59, '🌤️', 'upbeat'), (0.6, '☀️', 'upbeat+'), (1.0, '☀️', 'upbeat+'),
])
def test_weather_bands(mood, emoji, word):
    assert ph.weather(mood) == (emoji, word)


@pytest.mark.parametrize('hours, text', [
    (0, '1 min'), (0.001, '1 min'), (0.5, '30 min'), (1, '1 hour'), (1.4, '1 hour'), (1.6, '2 hours'),
    (2, '2 hours'), (47.4, '47 hours'), (48, '2 days'), (24 * 7, '7 days'),
])
def test_age_text(hours, text):
    assert ph.age_text(hours) == text


@pytest.mark.parametrize('value, position, text', [
    (0.0, 50.0, 'even'), (0.099, 52.5, 'even'), (0.1, 52.5, 'R+0.1'), (-1.2, 20.0, 'L+1.2'),
    (2.0, 100.0, 'R+2.0'), (5.0, 100.0, 'R+5.0'), (-9.0, 0.0, 'L+9.0'),
])
def test_meter_lean(value, position, text):
    m = ph.meter(value, ph.LEAN_RANGE, 'L', 'R')
    assert m['position'] == pytest.approx(position, abs=0.05)
    assert m['text'] == text
    assert m['value'] == round(value, 3)


@pytest.mark.parametrize('value, text', [(0.0, '0.00'), (0.04, '0.00'), (0.05, '+0.05'), (-0.5, '-0.50')])
def test_meter_mood_has_no_side_names(value, text):
    m = ph.meter(value, ph.MOOD_RANGE, '', '')
    assert m['text'] == text
    assert 0 <= m['position'] <= 100


@pytest.mark.parametrize('raw, name', [
    ('Christa Pike (murderer)', 'christa pike'), ('Jean-Luc  Picard', 'jean luc picard'),
    ('  TAYLOR   Swift ', 'taylor swift'), ('Plain', 'plain'),
])
def test_trend_name_normalization(raw, name):
    assert ph._name(raw) == name
# </editor-fold>


# <editor-fold desc="break_speed">
@pytest.fixture
def db_start(monkeypatch):
    start = dt(2026, 10, 1, 0, 0)
    monkeypatch.setattr(ph, 'DB_START', start)
    return start


def sighting(agency, when):
    return {'agency': agency, 'first_seen': when}


def test_break_speed_empty(db_start):
    assert ph.break_speed([]) is None


def test_break_speed_none_for_stories_running_when_the_database_started(db_start):
    first = db_start + td(hours=1, minutes=59)
    assert ph.break_speed([sighting('A', first), sighting('B', first + td(minutes=5))]) is None


def test_break_speed_counts_from_two_hours_after_start(db_start):
    first = db_start + td(hours=2)
    assert ph.break_speed([sighting('A', first)]) == 1


def test_break_speed_window_boundary(db_start):
    first = db_start + td(days=1)
    headlines = [sighting('A', first),
                 sighting('B', first + td(minutes=ph.BREAK_WINDOW_MINUTES)),  # just inside
                 sighting('C', first + td(minutes=ph.BREAK_WINDOW_MINUTES, seconds=1)),  # just outside
                 sighting('D', first + td(hours=5))]
    assert ph.break_speed(headlines) == 2


def test_break_speed_counts_each_outlet_once_at_its_earliest(db_start):
    first = db_start + td(days=1)
    headlines = [sighting('A', first), sighting('A', first + td(minutes=10)),
                 sighting('B', first + td(hours=3)), sighting('B', first + td(minutes=20))]
    assert ph.break_speed(headlines) == 2


def test_break_speed_aware_times_against_naive_start(db_start):
    """The database's naive start is UTC; aware sightings are compared to it as such."""
    one_hour_in = pd.Timestamp('2026-10-01 01:00', tz='UTC')
    assert ph.break_speed([sighting('A', one_hour_in)]) is None
    # midnight Eastern is 04:00 UTC, four hours in
    midnight_eastern = pd.Timestamp('2026-10-01 00:00', tz='US/Eastern')
    assert ph.break_speed([sighting('A', midnight_eastern), sighting('B', midnight_eastern + td(minutes=30))]) == 2
# </editor-fold>


# <editor-fold desc="story_feelings">
def ranks_frame(ranks):
    return pd.DataFrame({'emotion_ranks': ranks})


def test_story_feelings_without_rankings():
    assert ph.story_feelings(pd.DataFrame({'title': ['x']})) == []
    assert ph.story_feelings(ranks_frame([None, np.nan])) == []
    assert ph.dominant_emotion(ranks_frame([None])) == {}


def test_story_feelings_threshold_is_inclusive():
    feelings = ph.story_feelings(ranks_frame(['fear', 'fear', 'anger', 'sadness', 'joy']))
    assert feelings[0] == {'emoji': ph.EMOTION_EMOJI['fear'], 'name': 'fear', 'share': 40}
    assert {f['name'] for f in feelings} == {'fear', 'anger', 'sadness'}  # 3 cap; each at exactly 20%
    assert all(f['share'] == 20 for f in feelings[1:])


def test_story_feelings_just_below_threshold_is_left_out():
    feelings = ph.story_feelings(ranks_frame(['fear'] * 5 + ['anger']))  # anger 1/6 ≈ 17%
    assert [f['name'] for f in feelings] == ['fear']


def test_story_feelings_never_include_neutral():
    feelings = ph.story_feelings(ranks_frame(['neutral'] * 4 + ['hope']))
    assert [f['name'] for f in feelings] == ['hope']
    assert ph.story_feelings(ranks_frame(['neutral'] * 3)) == []


def test_story_feelings_at_most_three_strongest_first():
    feelings = ph.story_feelings(ranks_frame(['fear', 'fear', 'fear', 'anger', 'anger', 'joy', 'hope', 'hope']))
    assert len(feelings) == 3
    shares = [f['share'] for f in feelings]
    assert shares == sorted(shares, reverse=True)
    assert feelings[0]['name'] == 'fear'


def test_story_feelings_split_ranked_votes():
    """One headline ranking fear then anger splits its vote 2:1."""
    feelings = ph.story_feelings(ranks_frame(['fear,anger']))
    assert [(f['name'], f['share']) for f in feelings] == [('fear', 67), ('anger', 33)]
    assert ph.dominant_emotion(ranks_frame(['fear,anger']))['name'] == 'fear'


def test_story_feelings_ignore_unknown_emotions():
    assert [f['name'] for f in ph.story_feelings(ranks_frame(['love', 'surprise']))] == ['surprise']
# </editor-fold>


# <editor-fold desc="news_day">
def news_frame(stories):
    """stories: {group: [(agency, live, age_hours), ...]}"""
    rows = [{'group': g, 'agency': a, 'live': live, 'howlong': hours * 3600}
            for g, items in stories.items() for a, live, hours in items]
    return pd.DataFrame(rows)


def run_news_day(stories, **context):
    df = news_frame(stories)
    page = make_page(main_df=pd.DataFrame({'live': [True, True, False]}),
                     titles={g: f'Story {g}' for g in stories}, **context)
    page.news_day(df, df['agency'].nunique())
    return page.context['newsday']


def outlets(prefix, n, live=True, hours=1.0):
    return [(f'{prefix}{i}', live, hours) for i in range(n)]


@pytest.mark.parametrize('on_top, kind', [(9, 'big'), (8, 'normal'), (5, 'normal'), (4, 'slow')])
def test_news_day_tiers_at_their_boundaries(on_top, kind):
    """Of 20 live outlets: 45% (9) is a big day, 25% (5) a normal one. The rest are on an old story."""
    day = run_news_day({1: outlets('top', on_top), 2: outlets('old', 20 - on_top, hours=500)})
    assert day['kind'] == kind
    assert day['story'] == 'Story 1' and day['cluster'] == 1
    assert day['outlets'] == on_top and day['active'] == 20
    assert day['share'] == round(100 * on_top / 20)
    assert day['label'] == ph.NEWS_DAY_LABELS[kind]['label']


@pytest.mark.parametrize('hours, kind', [
    (ph.NEWS_DAY_FRESH_HOURS, 'big'),  # full weight through the fresh hours
    (ph.NEWS_DAY_FRESH_HOURS + ph.NEWS_DAY_HALF_LIFE_HOURS, 'big'),  # one half-life: 0.5
    (ph.NEWS_DAY_FRESH_HOURS + 2 * ph.NEWS_DAY_HALF_LIFE_HOURS, 'normal'),  # 0.25
    (ph.NEWS_DAY_FRESH_HOURS + 3 * ph.NEWS_DAY_HALF_LIFE_HOURS, 'slow'),  # 0.125
])
def test_news_day_age_weighting(hours, kind):
    """A story every outlet carries fades with age once it's past its fresh hours."""
    day = run_news_day({1: outlets('o', 10, hours=hours)})
    assert day['kind'] == kind
    assert day['share'] == 100
    assert day['age'] == ph.age_text(hours)


def test_news_day_story_is_as_old_as_its_oldest_headline():
    """Fresh posts on a running story don't make it new: a dropped two-and-a-half-day-old headline sets its age."""
    fresh = run_news_day({1: outlets('o', 10, hours=1)})
    aged = run_news_day({1: outlets('o', 10, hours=1) + [('gone', False, 60)]})
    assert fresh['kind'] == 'big'
    assert aged['kind'] == 'normal'
    assert aged['active'] == 10  # an outlet with nothing live isn't counted as active


def test_news_day_picks_highest_weighted_story_not_widest():
    day = run_news_day({1: outlets('a', 10, hours=200), 2: outlets('b', 6, hours=1)})
    assert day['cluster'] == 2


def test_news_day_names_a_saga_by_its_lead_story():
    sagas = {100: {'name': 'The Long Saga', 'lead': 7}}
    day = run_news_day({100: outlets('a', 5)}, sagas=sagas, clusters=[{}, {}, {}])
    assert day['story'] == 'The Long Saga'
    assert day['cluster'] == 7
    assert day['stories'] == 3
    assert day['live_headlines'] == 2


def test_news_day_none_when_nothing_is_live():
    assert run_news_day({1: [('a', False, 1), ('b', False, 2)]}) is None
# </editor-fold>


# <editor-fold desc="blindspots">
def cluster(cid, left=0, center=0, right=0, unrated=0, prefix=None):
    prefix = prefix or f'c{cid}-'
    data = ([{'agency': f'{prefix}L{i}', 'bias': -1 - i % 2, 'rated': True} for i in range(left)]
            + [{'agency': f'{prefix}C{i}', 'bias': 0, 'rated': True} for i in range(center)]
            + [{'agency': f'{prefix}R{i}', 'bias': 1 + i % 2, 'rated': True} for i in range(right)]
            + [{'agency': f'{prefix}U{i}', 'bias': 0, 'rated': False} for i in range(unrated)])
    return {'cluster': cid, 'data': data}


def right_filler(n):
    """Right-leaning outlets in clusters too small to be judged themselves, to shape the pool."""
    return [cluster(1000 + k, right=5, prefix=f'fill{k}-') for k in range(n)]


def run_blindspots(clusters):
    page = make_page(titles={c['cluster']: f'Story {c["cluster"]}' for c in clusters})
    page.blindspots(clusters)
    return page.context['blindspots']


@pytest.mark.parametrize('left, found', [(7, True), (6, False)])
def test_blindspot_share_boundary(left, found):
    """10 rated outlets: 70% from one side counts, 60% doesn't (the pool is mostly right, so lift is no obstacle)."""
    spots = run_blindspots([cluster(1, left=left, right=10 - left)] + right_filler(4))
    if found:
        assert spots['left'] == [{'cluster': 1, 'title': 'Story 1', 'share': 70, 'left': 7, 'center': 0, 'right': 3}]
    else:
        assert spots is None


@pytest.mark.parametrize('rated, found', [(6, True), (5, False)])
def test_blindspot_min_rated_outlets(rated, found):
    spots = run_blindspots([cluster(1, left=rated)] + right_filler(4))
    assert (spots is not None and len(spots['left']) == 1) == found


def test_blindspot_unrated_outlets_dont_count():
    spots = run_blindspots([cluster(1, left=5, unrated=10)] + right_filler(4))
    assert spots is None


def test_blindspot_lift_against_the_pool():
    """In a pool that's half left (story plus filler), a story 5/7 (71%) left passes the share bar but not the 1.5x
    lift (75%); 5/6 (83%) clears both."""
    assert run_blindspots([cluster(1, left=5, right=2, prefix='s-'), cluster(900, right=3, prefix='p-')]) is None
    spots = run_blindspots([cluster(1, left=5, right=1, prefix='s-'), cluster(900, right=4, prefix='p-')])
    assert spots['left'][0]['share'] == 83


def test_blindspot_mostly_right_story():
    spots = run_blindspots([cluster(1, right=6, left=1)] + [cluster(1000 + k, left=5, prefix=f'L{k}-')
                                                           for k in range(3)])
    assert spots['left'] == []
    assert spots['right'][0]['cluster'] == 1
    assert spots['right'][0]['right'] == 6


def test_blindspot_center_outlets_dilute_the_share():
    spots = run_blindspots([cluster(1, left=6, center=4)] + right_filler(4))
    assert spots is None  # 60%


def test_blindspots_sorted_by_share_then_size():
    clusters = [cluster(1, left=7, right=3), cluster(2, left=9, right=1), cluster(3, left=18, right=2),
                cluster(4, left=8)] + right_filler(10)
    order = [s['cluster'] for s in run_blindspots(clusters)['left']]
    assert order == [4, 3, 2, 1]  # 100%, then 90% with 20 outlets before 90% with 10, then 70%


def test_blindspots_none_when_no_clusters():
    assert run_blindspots([]) is None
# </editor-fold>




# <editor-fold desc="investigations">
def run_investigations(pieces, clusters, embedder, monkeypatch):
    monkeypatch.setattr(ph, 'recent_investigations', lambda: [dict(p) for p in pieces])
    monkeypatch.setattr(ph, 'embed', embedder)
    page = make_page(titles={c['cluster']: f'Story {c["cluster"]}' for c in clusters})
    page.investigations(clusters)
    return page.context['investigations']


def test_investigations_match_threshold(monkeypatch):
    s1, s2, other = unit(0), unit(1), unit(2)
    embedder = FakeEmbed({'Story 10': s1, 'Story 20': s2,
                          'Close': mix(s2, other, ph.INVESTIGATION_MATCH + 0.01),
                          'Not quite': mix(s1, other, ph.INVESTIGATION_MATCH - 0.01)})
    pieces = [{'title': 'Close', 'published': '2026-10-03T12:00:00+00:00'},
              {'title': 'Not quite', 'published': '2026-10-03T02:00:00+00:00'}]
    out = run_investigations(pieces, [{'cluster': 10}, {'cluster': 20}], embedder, monkeypatch)
    assert out[0]['story'] == 20 and out[0]['story_title'] == 'Story 20'
    assert out[1]['story'] is None and out[1]['story_title'] is None


def test_investigations_dates_are_eastern(monkeypatch):
    pieces = [{'title': 'A', 'published': '2026-10-03T12:00:00+00:00'},
              {'title': 'B', 'published': '2026-10-03T02:00:00+00:00'}]  # 10 PM the day before in New York
    out = run_investigations(pieces, [{'cluster': 1}], FakeEmbed(), monkeypatch)
    assert [p['date'] for p in out] == ['Oct 3', 'Oct 2']


def test_investigations_none_found(monkeypatch):
    def no_embedding(texts):
        raise AssertionError('embed called')
    assert run_investigations([], [{'cluster': 1}], no_embedding, monkeypatch) == []


def test_investigations_without_stories_have_no_story_link(monkeypatch):
    out = run_investigations([{'title': 'A', 'published': '2026-10-03T12:00:00+00:00'}], [], FakeEmbed(), monkeypatch)
    assert out[0].get('story', 'missing') is None
# </editor-fold>


# <editor-fold desc="trend matching">
def trend(topic, name, description=''):
    return SimpleNamespace(topic=topic, display_name=name, description=description)


def test_match_trends_by_full_name_in_two_headlines(monkeypatch):
    monkeypatch.setattr(ph, 'embed', FakeEmbed())
    df = pd.DataFrame({'cluster': [1, 1, 1, 2, 2],
                       'title': ['Christa Pike executed', 'Christa-Pike appeal fails', 'Tennessee execution',
                                 'Christa Pike mentioned once', 'Budget talks']})
    matches = ph.match_trends_to_stories(df, [trend('t1', 'Christa Pike (murderer)'), trend('t2', 'Pike')])
    assert matches == {'t1': 1}  # a one-word name doesn't name-match, and random vectors don't embed-match


def test_match_trends_name_needs_two_headlines(monkeypatch):
    monkeypatch.setattr(ph, 'embed', FakeEmbed())
    df = pd.DataFrame({'cluster': [1, 1], 'title': ['Christa Pike executed', 'Tennessee execution']})
    assert ph.match_trends_to_stories(df, [trend('t1', 'Christa Pike')]) == {}


def test_match_trends_by_embedding_threshold(monkeypatch):
    a, b, c = unit(0), unit(1), unit(2)
    embedder = FakeEmbed({'h1': a, 'h2': a, 'h3': b,
                          'Near. ': mix(a, c, ph.TREND_MATCH_THRESHOLD + 0.01),
                          'Far. ': mix(b, c, ph.TREND_MATCH_THRESHOLD - 0.01)})
    monkeypatch.setattr(ph, 'embed', embedder)
    df = pd.DataFrame({'cluster': [5, 5, 9], 'title': ['h1', 'h2', 'h3']})
    assert ph.match_trends_to_stories(df, [trend('near', 'Near'), trend('far', 'Far')]) == {'near': 5}


def test_match_trends_nothing_to_match(monkeypatch):
    monkeypatch.setattr(ph, 'embed', FakeEmbed())
    assert ph.match_trends_to_stories(pd.DataFrame({'cluster': [1], 'title': ['x']}), []) == {}
    assert ph.match_trends_to_stories(pd.DataFrame(columns=['cluster', 'title']), [trend('t', 'X Y')]) == {}
# </editor-fold>


# <editor-fold desc="summaries, chips and the table">
def test_summarize_prefers_labels_then_the_most_centrist_headline():
    df = pd.DataFrame({'cluster': [1, 1, 1, 2, 2], 'agency': ['L', 'C', 'R', 'X', 'Y'],
                       'bias': [-2, 0, 2, -1, 2], 'title': ['left take', 'center take', 'right take', 'x', 'y']})
    page = make_page()
    page.summarize(df, {2: 'A neutral label'})
    assert page.context['titles'] == {1: 'center take', 2: 'A neutral label'}
    assert page.context['summaries'] == {1: 'C: center take', 2: 'A neutral label'}


@pytest.fixture
def chip_globals(monkeypatch):
    monkeypatch.setitem(j2env.globals, 'icons', {})
    monkeypatch.setitem(j2env.globals, 'unrated', set())
    monkeypatch.setitem(j2env.globals, 'lean_estimates', {})


def chip_cluster(entries, first_minutes=600, speed=None):
    now = pd.Timestamp.now(tz='US/Eastern')
    data = []
    for i, e in enumerate(entries):
        first = now - td(hours=e.get('hours_live', 5))
        data.append({'agency': e.get('agency', f'Outlet {i}'), 'bias': e.get('bias', 0), 'url': e.get('url', f'u{i}'),
                     'title': f'Headline {i}', 'live': e.get('live', True), 'appearance': first,
                     'first_seen': first, 'last_seen': now - td(hours=e.get('hours_gone', 0)),
                     'sentiment': e.get('sentiment', 0.0), 'deviation': 0.0})
    return {'cluster': 1, 'data': data, 'coverage': 5.0, 'first': first_minutes * 60, 'speed': speed}


def run_chips(cluster_, rewritten=(), monkeypatch=None):
    edits = pd.DataFrame({'url': list(rewritten)}) if rewritten else pd.DataFrame()
    monkeypatch.setattr(ph, 'find_edits', lambda: (edits, None))
    page = make_page()
    page.make_agency_lists([cluster_])
    return page.context['agency_lists'][1], cluster_


@pytest.mark.parametrize('n, rewrites, churn', [(6, 3, True), (6, 2, False), (30, 5, True), (30, 4, False)])
def test_churn_badge_threshold(chip_globals, monkeypatch, n, rewrites, churn):
    """At least CHURN_OUTLETS rewrites and CHURN_SHARE of the outlets: 3 of 6, but 5 of 30."""
    html, c = run_chips(chip_cluster([{}] * n), rewritten=[f'u{i}' for i in range(rewrites)], monkeypatch=monkeypatch)
    assert c['rewrites'] == rewrites
    assert ('class="churn"' in html) == churn
    assert html.count(' ✏️') == rewrites


def test_chip_states(chip_globals, monkeypatch):
    html, _ = run_chips(chip_cluster([
        {'agency': 'Fresh', 'bias': -2, 'hours_live': 1},
        {'agency': 'Live', 'bias': 0, 'hours_live': 5},
        {'agency': 'Fading', 'bias': 1, 'live': False, 'hours_gone': 6},
        {'agency': 'Ghost', 'bias': 2, 'live': False, 'hours_gone': 30},
    ]), monkeypatch=monkeypatch)
    chips = html.split('<div class="chips">')[1].split('</a>')
    by_name = {name: next(c for c in chips if f'>{name} ' in c) for name in ('Fresh', 'Live', 'Fading', 'Ghost')}
    assert 'chip-fresh' in by_name['Fresh'] and '✨' in by_name['Fresh'] and 'opacity: 1.00' in by_name['Fresh']
    assert 'chip-live' in by_name['Live'] and '✨' not in by_name['Live']
    assert 'chip-gone' in by_name['Fading'] and 'opacity: 0.50' in by_name['Fading'] and '👻' in by_name['Fading']
    assert f'opacity: {ph.GHOST_OPACITY:.2f}' in by_name['Ghost']
    # left to right by lean
    assert html.index('>Fresh ') < html.index('>Live ') < html.index('>Fading ') < html.index('>Ghost ')
    assert '2 of 4 outlets still showing it' in html


def test_chip_smileys_and_short_names(chip_globals, monkeypatch):
    html, _ = run_chips(chip_cluster([
        {'agency': 'The Wall Street Journal', 'sentiment': 0.4},
        {'agency': 'CNN', 'sentiment': -0.3}, {'agency': 'AP', 'sentiment': 0.0}]), monkeypatch=monkeypatch)
    assert 'WSJ 😊' in html and 'CNN 😠' in html and 'AP 😐' in html
    assert 'Wall Street Journal 😊' not in html


@pytest.mark.parametrize('minutes, breaking', [(ph.BREAKING_MINUTES - 1, True), (ph.BREAKING_MINUTES, False)])
def test_breaking_fallback_text(chip_globals, monkeypatch, minutes, breaking):
    html, _ = run_chips(chip_cluster([{}], first_minutes=minutes), monkeypatch=monkeypatch)
    assert ('BREAKING!' in html) == breaking
    if not breaking:
        assert 'First seen 1 hour ago' in html


@pytest.mark.parametrize('speed, shown', [(ph.FAST_BREAK, True), (ph.FAST_BREAK - 1, False), (None, False)])
def test_fast_break_badge(chip_globals, monkeypatch, speed, shown):
    html, _ = run_chips(chip_cluster([{}], speed=speed), monkeypatch=monkeypatch)
    assert ('fast-break' in html) == shown


def test_table_rows():
    eastern = lambda s: pd.Timestamp(s, tz='US/Eastern')
    main = pd.DataFrame({'url': ['a', 'a', 'b', 'c'],
                         'first_accessed': [eastern('2026-10-03 09:00'), eastern('2026-10-03 08:00'),
                                            eastern('2026-10-03 10:00'), eastern('2026-10-03 11:00')]})
    df = pd.DataFrame({
        'agency': ['AP', 'CNN', 'Fox News', 'BBC'], 'bias': [-1, -1, 2, 0], 'url': ['a', 'b', 'c', 'zz'],
        'title': ['  Alpha  ', 'Bravo', 'Charlie', 'Delta'], 'score': [1, 2, 3, 4],
        'live': [True, True, True, False],
        'emotion_ranks': ['fear,neutral,bogus', None, 'hope', 'joy'], 'topic': ['Big Topic', None, '', 'x'],
        'event_score': [1.0, np.nan, -2.0, 0.0], 'loaded_score': [np.nan, 2.0, 0.0, 1.0],
    })
    page = make_page(main_df=main, clusters=[{'cluster': 7, 'data': [{'url': 'a'}, {'url': 'q'}]}],
                     summaries={7: 'AP: Alpha'})
    rows = page.table_rows(df)
    assert [r['url'] for r in rows] == ['c', 'b', 'a']  # live only, highest buzz first
    assert [r['buzz'] for r in rows] == [75, 50, 25]  # percentiles over every headline, live or not
    a = rows[2]
    assert a['title'] == 'Alpha'
    assert a['seen'] == int(eastern('2026-10-03 08:00').timestamp())  # its earliest sighting
    assert a['topic_url'] == 'Big_Topic.html'
    assert a['feelings'] == [[ph.EMOTION_EMOJI['fear'], 'fear']]
    assert (a['story'], a['story_title'], a['story_size']) == (7, 'AP: Alpha', 2)
    assert a['mood'] == 1 and a['loaded'] is None
    b = rows[1]
    assert b['mood'] is None and b['loaded'] == 2 and b['topic'] == '' and b['topic_url'] == ''
    assert b['feelings'] == [] and b['story'] is None and b['story_size'] == 0
    assert rows[0]['seen'] == int(eastern('2026-10-03 11:00').timestamp())


def test_table_rows_url_never_seen_in_main():
    page = make_page(main_df=pd.DataFrame({'url': ['other'], 'first_accessed': [pd.Timestamp('2026-10-03', tz='UTC')]}))
    df = pd.DataFrame({'agency': ['AP'], 'bias': [0], 'url': ['x'], 'title': ['t'], 'score': [0], 'live': [True],
                       'emotion_ranks': [None], 'topic': [None], 'event_score': [np.nan], 'loaded_score': [np.nan]})
    assert page.table_rows(df)[0]['seen'] is None
# </editor-fold>


# <editor-fold desc="formatting the headline frames">
def raw_headlines(times):
    return pd.DataFrame({
        'title': [f'Senate votes on the budget bill number {i}' for i in range(len(times))],
        'country': [0] * len(times), 'agency': ['AP'] * len(times),
        'first_accessed': pd.to_datetime(times).tz_localize('US/Eastern'),
        'last_accessed': pd.to_datetime(times).tz_localize('US/Eastern'),
    })


def test_filter_score_sort_formats_and_scores():
    df = HeadlinesPage.filter_score_sort(raw_headlines(['2026-10-03 09:41', '2026-10-03 09:42']))
    assert set(df['country']) == {'us'}
    assert set(df['first_accessed']) == {'Oct 3 9:41 AM', 'Oct 3 9:42 AM'}
    assert set(df['last_accessed']) == {'9:41 AM', '9:42 AM'}
    assert (df['score'] > 0).all()
    assert 'prepared' not in df


def test_filter_score_sort_is_newest_first():
    df = HeadlinesPage.filter_score_sort(raw_headlines(['2026-10-03 09:41', '2026-10-03 10:15']))
    assert list(df['first_accessed']) == ['Oct 3 10:15 AM', 'Oct 3 9:41 AM']


# </editor-fold>


# show_coverage: news-of-the-day items split into pieces and matched to several story cards

def test_show_coverage_splits_rundowns_onto_several_cards(monkeypatch):
    import numpy as np
    import app.site.page_headlines as ph
    items = [{'title': 'Wages Vs Inflation, Tennessee Failed Execution, Cornell Case', 'summary': '',
              'source': 'Up First (NPR)', 'kind': 'podcast', 'group': 'center', 'url': 'u1',
              'published': '2026-10-03T10:00:00+00:00'},
             {'title': 'Cornell Case', 'summary': '', 'source': 'Up First (NPR)', 'kind': 'podcast',
              'group': 'center', 'url': 'u0', 'published': '2026-10-02T10:00:00+00:00'},
             {'title': 'Something else entirely', 'summary': '', 'source': 'Ruthless', 'kind': 'podcast',
              'group': 'right', 'url': 'u2', 'published': '2026-10-03T09:00:00+00:00'}]
    monkeypatch.setattr(ph.sidefeeds, 'recent', lambda **kw: items)
    vecs = {'Wages Vs Inflation': [1, 0, 0, 0], 'Tennessee Failed Execution': [0, 1, 0, 0],
            'Cornell Case': [0, 0, 1, 0], 'Something else entirely': [0, 0, 0, 1],
            'Jobs report': [1, 0, 0, 0], 'Execution fails': [0, 1, 0, 0], 'Cornell': [0, 0, 1, 0]}
    monkeypatch.setattr(ph, 'embed', lambda texts: np.array([vecs.get(t, [0.1, 0.1, 0.1, 0.1]) for t in texts], float))
    page = ph.HeadlinesPage.__new__(ph.HeadlinesPage)
    page.context = {'titles': {1: 'Jobs report', 2: 'Execution fails', 3: 'Cornell'}}
    page.show_coverage([{'cluster': 1}, {'cluster': 2}, {'cluster': 3}])
    cov = page.context['show_coverage']
    assert set(cov) == {1, 2, 3}  # one rundown lands on all three cards; the unrelated item on none
    assert [c['url'] for c in cov[3]] == ['u1']  # one chip per show, its newest item
    assert cov[1][0]['emoji'] == '🎙️'


# feed.xml (#123)
def test_feed_is_valid_rss_with_stable_guids(tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET
    from app.utils import Config
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    page = ph.HeadlinesPage.__new__(ph.HeadlinesPage)
    page.story_of = {7: 1234}
    page.context = {
        'clusters': [{'cluster': 7, 'first': 3600, 'lean': {'text': 'L+0.4'}, 'mood': {'word': 'grim'},
                      'feelings': [{'emoji': '😱', 'name': 'fear'}]}],
        'news_trends': [{'cluster': 7, 'title': 'Storms & floods <hit> coast', 'now': 12, 'outlets': 30, 'saga': 3}],
    }
    page.write_feed()
    root = ET.parse(tmp_path / 'feed.xml').getroot()
    [item] = root.iter('item')
    assert item.findtext('title') == 'Storms & floods <hit> coast'
    assert item.findtext('guid') == 'bignews-story-1234'
    assert '12 outlets' in item.findtext('description') and '3-part saga' in item.findtext('description')
