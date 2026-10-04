"""Investigations feeds: date and summary cleanup, feed parsing, the recent() picker and polite fetching. No network:
requests is faked, and the cache lives in tmp_path."""
import json
from datetime import datetime as dt, timedelta as td

import pytest
import pytz
import requests as rq

from app import investigations as inv
from app.investigations import _date, _summary, parse


# _date()

@pytest.mark.parametrize('text, expected', [
    ('Tue, 01 Oct 2024 12:00:00 +0000', '2024-10-01T12:00:00+00:00'),
    ('Tue, 01 Oct 2024 12:00:00 GMT', '2024-10-01T12:00:00+00:00'),
    ('Tue, 01 Oct 2024 12:00:00 -0400', '2024-10-01T16:00:00+00:00'),  # converted to UTC
    ('Tue, 01 Oct 2024 12:00:00', '2024-10-01T12:00:00+00:00'),  # no zone: treated as UTC
    ('2024-10-01T12:00:00Z', '2024-10-01T12:00:00+00:00'),
    ('2024-10-01T12:00:00+02:00', '2024-10-01T10:00:00+00:00'),
    ('2024-10-01T12:00:00', '2024-10-01T12:00:00+00:00'),  # naive ISO: treated as UTC
    ('  2024-10-01T12:00:00Z \n', '2024-10-01T12:00:00+00:00'),
])
def test_date_parses(text, expected):
    assert _date(text) == expected


@pytest.mark.parametrize('text', [None, '', 'garbage', 'next Tuesday', '2024-13-45T99:00:00'])
def test_date_garbage_is_none(text):
    assert _date(text) is None


# _summary()

def test_summary_strips_tags_and_unescapes():
    assert _summary('<p>Hello&nbsp;<b>world</b> &amp; more</p>') == 'Hello world & more'


def test_summary_collapses_whitespace():
    assert _summary('  one\n\n two\t\tthree  ') == 'one two three'


def test_summary_tags_separate_words():
    assert _summary('first<br/>second') == 'first second'


@pytest.mark.parametrize('text', [None, '', '<p></p>'])
def test_summary_empty(text):
    assert _summary(text) == ''


def test_summary_short_text_untouched():
    assert _summary('a short summary', limit=280) == 'a short summary'


def test_summary_truncates_at_a_word():
    out = _summary('alpha beta gamma delta epsilon', limit=14)
    assert out == 'alpha beta…'
    assert len(out) <= 15


def test_summary_exactly_at_limit_not_truncated():
    assert _summary('abcde fghij', limit=11) == 'abcde fghij'


def test_summary_default_limit():
    out = _summary('word ' * 200)
    assert out.endswith('…') and len(out) <= 281 and not out[:-1].endswith(' ')


# parse()

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Tracking &amp;amp; tracing</title><link>https://example.org/one</link>
  <pubDate>Tue, 01 Oct 2024 12:00:00 +0000</pubDate>
  <description>&lt;p&gt;An &lt;b&gt;open-source&lt;/b&gt; probe&lt;/p&gt;</description></item>
<item><title>No date</title><link>https://example.org/two</link></item>
<item><link>https://example.org/untitled</link></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title type="html">Here&amp;#8217;s what we found</title><link href="https://example.org/atom"/>
  <published>2024-10-01T12:00:00Z</published><summary>Short summary</summary></entry>
<entry><title>Updated only</title><link href="https://example.org/upd"/><updated>2024-10-02T08:00:00+02:00</updated></entry>
</feed>"""


def test_parse_rss_items():
    items = parse(RSS)
    assert [i['url'] for i in items] == ['https://example.org/one', 'https://example.org/two']
    first = items[0]
    assert first['title'] == 'Tracking & tracing'  # double-encoded entity unescaped
    assert first['published'] == '2024-10-01T12:00:00+00:00'
    assert first['summary'] == 'An open-source probe'


def test_parse_rss_missing_fields():
    second = parse(RSS)[1]
    assert second['published'] is None
    assert second['summary'] == ''


def test_parse_atom_entries():
    items = parse(ATOM)
    assert items[0] == {'title': 'Here’s what we found', 'url': 'https://example.org/atom',
                        'published': '2024-10-01T12:00:00+00:00', 'summary': 'Short summary'}
    assert items[1]['url'] == 'https://example.org/upd'
    assert items[1]['published'] == '2024-10-02T06:00:00+00:00'


def test_parse_keeps_at_most_keep():
    body = ''.join(f'<item><title>T{i}</title><link>https://e/{i}</link></item>' for i in range(inv.KEEP + 5))
    items = parse(f'<rss><channel>{body}</channel></rss>')
    assert len(items) == inv.KEEP
    assert items[0]['title'] == 'T0'


def test_parse_empty_feed():
    assert parse('<rss><channel></channel></rss>') == []


# recent()

def iso(**ago):
    return (dt.now(pytz.UTC) - td(**ago)).isoformat()


def item(title, published):
    return {'title': title, 'url': f'https://e/{title}', 'published': published, 'summary': ''}


@pytest.fixture
def fake_cache(monkeypatch):
    cache = {}
    monkeypatch.setattr(inv, '_load', lambda: cache)
    return cache


def test_recent_at_most_two_per_source(fake_cache):
    fake_cache['bellingcat'] = {'items': [item(f'b{i}', iso(hours=i + 1)) for i in range(5)]}
    out = inv.recent()
    assert [p['title'] for p in out] == ['b0', 'b1']
    assert out[0]['source'] == 'Bellingcat' and out[0]['home'] == 'https://www.bellingcat.com/'


def test_recent_newest_first_across_sources(fake_cache):
    fake_cache['bellingcat'] = {'items': [item('b-old', iso(days=3))]}
    fake_cache['icij'] = {'items': [item('i-new', iso(hours=1))]}
    fake_cache['occrp'] = {'items': [item('o-mid', iso(days=1))]}
    assert [p['title'] for p in inv.recent()] == ['i-new', 'o-mid', 'b-old']


def test_recent_drops_old_and_undated(fake_cache):
    fake_cache['icij'] = {'items': [item('old', iso(days=20)), item('undated', None), item('fresh', iso(days=2))]}
    assert [p['title'] for p in inv.recent(days=14)] == ['fresh']


def test_recent_old_items_dont_use_up_the_two(fake_cache):
    fake_cache['icij'] = {'items': [item('old', iso(days=30)), item('a', iso(hours=1)), item('b', iso(hours=2))]}
    assert [p['title'] for p in inv.recent()] == ['a', 'b']


def test_recent_days_window(fake_cache):
    fake_cache['icij'] = {'items': [item('a', iso(days=2)), item('b', iso(days=5))]}
    assert [p['title'] for p in inv.recent(days=3)] == ['a']


def test_recent_limit(fake_cache):
    for n, source in enumerate(inv.SOURCES):
        fake_cache[source['key']] = {'items': [item(f'{source["key"]}{i}', iso(hours=n * 2 + i)) for i in range(2)]}
    out = inv.recent(limit=5)
    assert len(out) == 5
    assert [p['title'] for p in out] == ['bellingcat0', 'bellingcat1', 'icij0', 'icij1', 'occrp0']


def test_recent_ignores_unknown_sources_and_empty_cache(fake_cache):
    assert inv.recent() == []
    fake_cache['not-a-source'] = {'items': [item('x', iso(hours=1))]}
    assert inv.recent() == []


def test_recent_two_newest_even_if_feed_out_of_order(fake_cache):
    fake_cache['icij'] = {'items': [item('older', iso(days=3)), item('old', iso(days=2)), item('newest', iso(hours=1))]}
    assert [p['title'] for p in inv.recent()] == ['newest', 'old']


# _load() and fetch_investigations()

@pytest.fixture
def cache_file(tmp_path, monkeypatch):
    path = tmp_path / 'investigations.json'
    monkeypatch.setattr(inv, 'CACHE', str(path))
    return path


def test_load_missing_or_corrupt_cache(cache_file):
    assert inv._load() == {}
    cache_file.write_text('{not json')
    assert inv._load() == {}
    cache_file.write_text('{"icij": {"items": []}}')
    assert inv._load() == {'icij': {'items': []}}


class FakeResponse:
    def __init__(self, status=200, text='', headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise rq.HTTPError(f'{self.status_code}')


FEED = '<rss><channel><item><title>New piece</title><link>https://e/new</link></item></channel></rss>'


@pytest.fixture
def fake_get(monkeypatch):
    """rq.get answering per feed url from `responses` (a FakeResponse or an exception); records request headers."""
    responses, calls = {}, {}

    def get(url, headers=None, timeout=None):
        calls[url] = headers
        answer = responses.get(url, FakeResponse(304))
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(inv.rq, 'get', get)
    return responses, calls


def feed_of(key):
    return next(s['feed'] for s in inv.SOURCES if s['key'] == key)


def test_fetch_stores_items_and_validators(cache_file, fake_get):
    responses, calls = fake_get
    responses[feed_of('icij')] = FakeResponse(200, FEED, {'ETag': '"abc"', 'Last-Modified': 'Tue, 01 Oct 2024'})
    inv.fetch_investigations()
    saved = json.loads(cache_file.read_text())
    assert saved['icij']['items'][0]['title'] == 'New piece'
    assert saved['icij']['etag'] == '"abc"'
    assert saved['icij']['modified'] == 'Tue, 01 Oct 2024'
    assert dt.fromisoformat(saved['icij']['fetched']).tzinfo is not None
    assert len(calls) == len(inv.SOURCES)
    assert calls[feed_of('icij')]['User-Agent'] == inv.USER_AGENT


def test_fetch_without_cache_sends_no_conditional_headers(cache_file, fake_get):
    _, calls = fake_get
    inv.fetch_investigations()
    for headers in calls.values():
        assert 'If-None-Match' not in headers and 'If-Modified-Since' not in headers


def test_fetch_sends_conditional_headers_when_cached(cache_file, fake_get):
    _, calls = fake_get
    cache_file.write_text(json.dumps({'icij': {'items': [], 'etag': '"e1"', 'modified': 'Mon, 30 Sep 2024'},
                                      'occrp': {'items': [], 'etag': None, 'modified': 'Sun, 29 Sep 2024'}}))
    inv.fetch_investigations()
    assert calls[feed_of('icij')]['If-None-Match'] == '"e1"'
    assert calls[feed_of('icij')]['If-Modified-Since'] == 'Mon, 30 Sep 2024'
    assert 'If-None-Match' not in calls[feed_of('occrp')]
    assert calls[feed_of('occrp')]['If-Modified-Since'] == 'Sun, 29 Sep 2024'


def test_fetch_304_keeps_cache_entry(cache_file, fake_get):
    old = {'items': [item('kept', '2024-10-01T00:00:00+00:00')], 'etag': '"e1"', 'modified': None,
           'fetched': '2024-10-01T00:00:00+00:00'}
    cache_file.write_text(json.dumps({'icij': old}))
    inv.fetch_investigations()  # every source answers 304
    assert json.loads(cache_file.read_text())['icij'] == old


@pytest.mark.parametrize('failure', [rq.ConnectionError('down'), FakeResponse(500), FakeResponse(200, None)])
def test_fetch_failure_keeps_old_items(cache_file, fake_get, failure):
    responses, _ = fake_get
    old = {'items': [item('kept', '2024-10-01T00:00:00+00:00')], 'etag': None, 'modified': None}
    cache_file.write_text(json.dumps({'icij': old}))
    responses[feed_of('icij')] = failure
    responses[feed_of('bellingcat')] = FakeResponse(200, FEED)
    inv.fetch_investigations()  # one source failing doesn't stop the others
    saved = json.loads(cache_file.read_text())
    assert saved['icij'] == old
    assert saved['bellingcat']['items'][0]['url'] == 'https://e/new'


def test_fetch_200_replaces_old_items(cache_file, fake_get):
    responses, _ = fake_get
    cache_file.write_text(json.dumps({'icij': {'items': [item('stale', None)], 'etag': '"old"'}}))
    responses[feed_of('icij')] = FakeResponse(200, FEED, {'ETag': '"new"'})
    inv.fetch_investigations()
    saved = json.loads(cache_file.read_text())['icij']
    assert [i['title'] for i in saved['items']] == ['New piece']
    assert saved['etag'] == '"new"' and saved['modified'] is None
