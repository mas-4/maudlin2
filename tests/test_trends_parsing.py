"""Trend sources parsed from canned payloads: `_get` is faked, so nothing touches the network or the database
(fetch_trends(), which writes to the database, is deliberately not exercised here)."""
import hashlib
from types import SimpleNamespace

import pytest

from app import trends
from app.models import Trend
from app.trends import _topic, match_text


class FakeResponse:
    def __init__(self, json=None, content=b''):
        self._json, self.content = json, content

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json


@pytest.fixture
def fake_get(monkeypatch):
    """Answers `_get` from a list of (url substring, response) routes; records each call."""
    routes, calls = [], []

    def get(url, **params):
        calls.append((url, params))
        for fragment, response in routes:
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f'unexpected request: {url}')

    monkeypatch.setattr(trends, '_get', get)
    return routes, calls


# _topic() and match_text()

def test_topic_short_keys_are_prefixed():
    assert _topic('google', 'taylor swift') == 'google:taylor swift'


def test_topic_at_64_chars_is_kept():
    key = 'k' * (64 - len('google:'))
    assert _topic('google', key) == f'google:{key}'


def test_topic_long_keys_are_hashed():
    key = 'https://example.com/' + 'a' * 100
    topic = _topic('mastodon', key)
    assert topic == f'mastodon:{hashlib.sha1(key.encode()).hexdigest()}'
    assert len(topic) <= 64


def test_topic_hash_is_stable_and_distinct():
    a, b = 'x' * 80, 'y' * 80
    assert _topic('wikipedia', a) == _topic('wikipedia', a) != _topic('wikipedia', b)


@pytest.mark.parametrize('description, expected', [
    ('Pop star announces tour', 'Taylor Swift. Pop star announces tour'),
    (None, 'Taylor Swift. '),
    ('', 'Taylor Swift. '),
])
def test_match_text(description, expected):
    assert match_text(Trend(display_name='Taylor Swift', description=description)) == expected


def test_match_text_accepts_any_trend_like_object():
    assert match_text(SimpleNamespace(display_name='Election', description='Votes counted')) == 'Election. Votes counted'


# bluesky()

def test_bluesky(fake_get):
    routes, calls = fake_get
    routes.append(('bsky.app', FakeResponse({'trends': [
        {'topic': 'abc123', 'displayName': 'Election Night', 'description': 'Results', 'category': 'politics',
         'link': '/profile/trending.bsky.app/feed/abc', 'status': 'hot', 'postCount': 4200,
         'startedAt': '2026-10-03T10:00:00Z'},
        {'topic': 'def456', 'displayName': 'Quiet', 'link': None},
    ]})))
    first, second = trends.bluesky()
    assert first == {'topic': 'abc123', 'display_name': 'Election Night', 'description': 'Results',
                     'category': 'politics', 'link': 'https://bsky.app/profile/trending.bsky.app/feed/abc',
                     'status': 'hot', 'post_count': 4200, 'started_at': '2026-10-03T10:00:00Z'}
    assert second['link'] is None
    assert second['description'] is None and second['post_count'] is None and second['started_at'] is None
    assert calls[0][1] == {'limit': trends.LIMIT}


def test_bluesky_empty(fake_get):
    routes, _ = fake_get
    routes.append(('bsky.app', FakeResponse({'trends': []})))
    assert trends.bluesky() == []


# google()

GOOGLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>Taylor Swift</title><ht:approx_traffic>200,000+</ht:approx_traffic>
  <ht:news_item><ht:news_item_title>Swift announces tour</ht:news_item_title>
  <ht:news_item_url>https://news.example/swift</ht:news_item_url></ht:news_item></item>
<item><title>  Hurricane &amp; Flood  </title></item>
</channel></rss>"""


def test_google(fake_get):
    routes, calls = fake_get
    routes.append(('trends.google.com', FakeResponse(content=GOOGLE_RSS)))
    first, second = trends.google()
    assert first == {'topic': 'google:taylor swift', 'display_name': 'Taylor Swift',
                     'description': 'Swift announces tour',
                     'link': 'https://trends.google.com/trends/explore?geo=US&q=Taylor%20Swift',
                     'post_count': 200000, 'category': 'https://news.example/swift'}
    assert second['display_name'] == 'Hurricane & Flood'
    assert second['topic'] == 'google:hurricane & flood'
    assert second['link'].endswith('q=Hurricane%20%26%20Flood')
    assert second['description'] is None and second['post_count'] is None and second['category'] is None
    assert calls[0][1] == {'geo': 'US'}


def test_google_caps_at_limit(fake_get):
    routes, _ = fake_get
    items = ''.join(f'<item><title>Query {i}</title></item>' for i in range(trends.LIMIT + 5))
    routes.append(('trends.google.com', FakeResponse(content=f'<rss><channel>{items}</channel></rss>'.encode())))
    result = trends.google()
    assert len(result) == trends.LIMIT
    assert result[0]['display_name'] == 'Query 0'


# wikipedia()

def wiki_routes(routes, articles, summaries):
    for title, summary in summaries.items():
        routes.append((f'/page/summary/{title}', summary))
    routes.append(('wikimedia.org/api/rest_v1/metrics/pageviews/top',
                   FakeResponse({'items': [{'articles': articles}]})))


def test_wikipedia(fake_get):
    routes, calls = fake_get
    wiki_routes(routes, [
        {'article': 'Main_Page', 'views': 9_000_000},
        {'article': 'Special:Search', 'views': 1_000_000},
        {'article': 'Hurricane_Milton', 'views': 500_000},
        {'article': 'Taylor_Swift', 'views': 300_000},
    ], {
        'Hurricane_Milton': FakeResponse({'description': 'Category 5 Atlantic hurricane in 2024'}),
        'Taylor_Swift': FakeResponse({}),
    })
    milton, swift = trends.wikipedia()
    assert milton == {'topic': 'wikipedia:Hurricane_Milton', 'display_name': 'Hurricane Milton',
                      'description': 'Category 5 Atlantic hurricane in 2024',
                      'link': 'https://en.wikipedia.org/wiki/Hurricane_Milton', 'post_count': 500_000}
    assert swift['description'] is None
    # Skipped pages aren't even looked up
    assert not any('Main_Page' in url or 'Special' in url for url, _ in calls[1:])


def test_wikipedia_summary_failure_is_not_fatal(fake_get):
    routes, _ = fake_get
    wiki_routes(routes, [{'article': 'Kamala_Harris', 'views': 10}],
                {'Kamala_Harris': RuntimeError('summary api down')})
    [trend] = trends.wikipedia()
    assert trend['display_name'] == 'Kamala Harris' and trend['description'] is None


def test_wikipedia_quotes_titles_in_links(fake_get):
    routes, _ = fake_get
    wiki_routes(routes, [{'article': 'Café_Society', 'views': 10}], {'Caf%C3%A9_Society': FakeResponse({'description': 'Film'})})
    [trend] = trends.wikipedia()
    assert trend['link'] == 'https://en.wikipedia.org/wiki/Caf%C3%A9_Society'
    assert trend['display_name'] == 'Café Society' and trend['description'] == 'Film'


def test_wikipedia_summary_url_escapes_slashes(fake_get):
    routes, calls = fake_get
    wiki_routes(routes, [{'article': 'AC/DC', 'views': 10}], {'AC%2FDC': FakeResponse({'description': 'Band'})})
    [trend] = trends.wikipedia()
    assert trend['description'] == 'Band'


def test_wikipedia_stops_at_limit(fake_get):
    routes, calls = fake_get
    articles = [{'article': f'Page_{i}', 'views': 100 - i} for i in range(trends.LIMIT + 5)]
    routes.append(('/page/summary/', FakeResponse({})))
    wiki_routes(routes, articles, {})
    result = trends.wikipedia()
    assert len(result) == trends.LIMIT
    assert len(calls) == 1 + trends.LIMIT  # no summaries fetched past the limit


@pytest.mark.parametrize('article', ['Wikipedia:About', 'Portal:Current_events', 'File:X.jpg', 'Help:Contents',
                                     'Talk:Foo', 'Template:Bar', 'Category:Baz', 'User:Someone'])
def test_wikipedia_skip_pattern(article):
    assert trends.WIKIPEDIA_SKIP.match(article)


@pytest.mark.parametrize('article', ['Mainz', 'Special_forces', 'Filet_mignon', 'Userland'])
def test_wikipedia_skip_pattern_keeps_articles(article):
    assert not trends.WIKIPEDIA_SKIP.match(article)


# mastodon()

def test_mastodon(fake_get):
    routes, calls = fake_get
    routes.append(('mastodon.social', FakeResponse([
        {'url': 'https://news.example/a', 'title': 'Big story', 'provider_name': 'Example News',
         'history': [{'day': '3', 'accounts': '40', 'uses': '50'}, {'day': '2', 'accounts': '10', 'uses': '12'},
                     {'day': '1', 'accounts': '999', 'uses': '999'}]},
        {'url': 'https://news.example/' + 'b' * 80, 'title': 'Long url'},
    ])))
    first, second = trends.mastodon()
    assert first == {'topic': 'mastodon:https://news.example/a', 'display_name': 'Big story', 'description': None,
                     'category': 'Example News', 'link': 'https://news.example/a', 'post_count': 50}
    assert second['post_count'] == 0 and second['category'] is None
    assert len(second['topic']) <= 64 and second['topic'].startswith('mastodon:')
    assert calls[0][1] == {'limit': trends.LIMIT}


def test_sources_registry():
    assert set(trends.SOURCES) == {'bluesky', 'google', 'wikipedia', 'mastodon'}
    assert all(callable(f) for f in trends.SOURCES.values())


def test_wikipedia_falls_back_a_day_while_yesterday_is_not_published(monkeypatch):
    import requests as rq
    from app import trends
    asked = []

    class Missing:
        status_code = 404

    def get(url, **params):
        asked.append(url)
        if '/pageviews/top/' in url and len(asked) == 1:
            raise rq.HTTPError(response=Missing())
        if '/pageviews/top/' in url:
            return type('R', (), {'json': lambda self: {'items': [{'articles': []}]}})()
        raise AssertionError(url)

    monkeypatch.setattr(trends, '_get', get)
    assert trends.wikipedia() == []
    assert len(asked) == 2 and asked[0] != asked[1]  # the day before, after a 404
