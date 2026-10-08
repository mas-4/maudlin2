"""app/sidefeeds.py: parsing, archiving and selection, against an in-memory database and faked requests."""
import json
from datetime import datetime as dt, timedelta as td

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.sidefeeds as sf
from app.models import Base, SideItem

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Show</title>
<item><title>Ep. 12 - Trump &amp; the Fed</title><link>https://x/12</link><pubDate>Fri, 03 Oct 2026 10:00:00 GMT</pubDate>
<description>&lt;p&gt;Hosts discuss &lt;b&gt;rates&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>No link but a guid</title><guid>abc-123</guid><pubDate>Thu, 02 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Only audio</title><enclosure url="https://cdn/ep.mp3" type="audio/mpeg"/></item>
<item><link>https://x/untitled</link></item>
</channel></rss>"""
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
<entry><title>Stream: the jobs report</title><link rel="alternate" href="https://www.youtube.com/watch?v=1"/>
<published>2026-10-03T12:00:00+00:00</published><media:group><media:description>Live reaction</media:description></media:group></entry>
</feed>"""


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(sf, 'Session', session)
    return session


def test_parse_rss_with_link_guid_and_enclosure():
    items = sf.parse(RSS)
    assert [i['url'] for i in items] == ['https://x/12', 'abc-123', 'https://cdn/ep.mp3']
    assert items[0]['title'] == 'Ep. 12 - Trump & the Fed'
    assert items[0]['summary'] == 'Hosts discuss rates'
    assert items[0]['published'].startswith('2026-10-03T10:00')
    assert items[2]['published'] is None


def test_parse_youtube_atom():
    [item] = sf.parse(ATOM)
    assert item['url'] == 'https://www.youtube.com/watch?v=1'
    assert item['summary'] == 'Live reaction'


def test_parse_keeps_only_newest(monkeypatch):
    monkeypatch.setattr(sf, 'NEWEST', 1)
    assert len(sf.parse(RSS)) == 1


def test_save_is_append_only_and_idempotent(db):
    now = dt(2026, 10, 3, 12)
    items = sf.parse(RSS)
    assert sf.save('psa', items, now) == 3
    assert sf.save('psa', items, now) == 0
    assert sf.save('remnant', items, now) == 3  # same urls under another source are separate rows
    with db() as s:
        assert s.query(SideItem).count() == 6


def test_recent_only_published_sources_one_each_newest_first(db, monkeypatch):
    now = dt.utcnow()
    with db() as s:
        for source, hours, url in [('psa', 1, 'a'), ('psa', 2, 'b'), ('upfirst', 3, 'c'), ('remnant', 0, 'd'),
                                   ('megyn', 24 * 9, 'old')]:
            s.add(SideItem(source=source, title=url, url=url, published=now - td(hours=hours), first_seen=now))
        s.commit()
    picked = sf.recent(days=3)
    assert [p['url'] for p in picked] == ['a', 'c']  # remnant isn't published; megyn's item is too old
    assert picked[0]['source'] == 'Pod Save America' and picked[0]['kind'] == 'podcast'
    assert len(sf.recent(days=3, per_source=2)) == 3


def test_sources_are_well_formed():
    keys = [s['key'] for s in sf.SOURCES]
    assert len(keys) == len(set(keys))
    assert all(s['kind'] in ('podcast', 'newsletter', 'video', 'call-in', 'fact-check', 'satire') for s in sf.SOURCES)
    assert all(s['group'] in ('left', 'right', 'center', 'crossover') for s in sf.SOURCES)
    assert all(len(k) <= 32 for k in keys)
    published = [s for s in sf.SOURCES if s['publish']]
    assert not any(s['publish'] for s in sf.SOURCES if s['kind'] in ('satire', 'call-in', 'fact-check'))  # never in the shows list
    assert {s['group'] for s in published} >= {'left', 'right', 'center'}


class FakeResponse:
    def __init__(self, status, text='', headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_fetch_conditional_requests_spacing_and_state(db, monkeypatch, tmp_path):
    state = tmp_path / 'state.json'
    monkeypatch.setattr(sf, 'STATE', str(state))
    monkeypatch.setattr(sf, 'HOST_PAUSE', 0)
    monkeypatch.setattr(sf, 'SOURCES', [sf._source('a', 'A', 'podcast', 'left', 'https://feeds.megaphone.fm/A', True),
                                         sf._source('b', 'B', 'podcast', 'left', 'https://feeds.megaphone.fm/B', True),
                                         sf._source('c', 'C', 'newsletter', 'right', 'https://c.example/feed', True)])
    calls = []

    def get(url, headers, timeout):
        calls.append((url, headers))
        if url.endswith('/B'):
            raise RuntimeError('down')
        if url.endswith('/A'):
            return FakeResponse(200, RSS, {'ETag': '"e1"', 'Last-Modified': 'Fri, 03 Oct 2026 10:00:00 GMT'})
        return FakeResponse(304)
    monkeypatch.setattr(sf.rq, 'get', get)
    sf.fetch_sidefeeds()
    saved = json.loads(state.read_text())
    assert saved['a']['etag'] == '"e1"' and 'fetched' in saved['b'] and 'fetched' in saved['c']
    with db() as s:
        assert s.query(SideItem).filter(SideItem.source == 'a').count() == 3
    calls.clear()
    sf.fetch_sidefeeds()  # nothing is due yet
    assert calls == []
    sf.fetch_sidefeeds(force=True)
    sent = dict(calls)
    assert sent['https://feeds.megaphone.fm/A']['If-None-Match'] == '"e1"'


def test_parse_keeps_podcast_audio():
    items = sf.parse(RSS)
    assert items[0]['audio'] is None
    assert items[2]['audio'] == 'https://cdn/ep.mp3'


def test_sources_have_a_refresh_interval():
    assert all(s['refresh'] <= sf.REFRESH or s['refresh'] == sf.BIG_FEED for s in sf.SOURCES)
    assert all(sf.BY_KEY[k]['refresh'] == sf.BIG_FEED for k in ('jessekelly', 'claybuck', 'michaelberry'))  # iHeart's 10 MB feeds
    assert sf.BY_KEY['nprnewsnow']['refresh'] < sf.REFRESH and not sf.BY_KEY['nprnewsnow']['publish']


def test_hosts_are_read_side_by_side_but_each_host_one_request_at_a_time(db, monkeypatch, tmp_path):
    import threading
    import time
    monkeypatch.setattr(sf, 'STATE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(sf, 'HOST_PAUSE', 0.2)
    monkeypatch.setattr(sf, 'SOURCES', [sf._source(k, k, 'podcast', 'left', f'https://{host}/{k}', True)
                                         for k, host in (('a', 'feeds.megaphone.fm'), ('b', 'feeds.megaphone.fm'),
                                                         ('c', 'www.youtube.com'), ('d', 'www.youtube.com'))])
    spans, lock = [], threading.Lock()

    def get(url, headers, timeout):
        start = time.monotonic()
        time.sleep(0.2)
        with lock:
            spans.append((url.split('/')[2], start, time.monotonic()))
        return FakeResponse(304)
    monkeypatch.setattr(sf.rq, 'get', get)
    began = time.monotonic()
    sf.fetch_sidefeeds()
    took = time.monotonic() - began
    for host in ('feeds.megaphone.fm', 'www.youtube.com'):
        (_, s1, e1), (_, s2, _) = sorted(s for s in spans if s[0] == host)[:2]
        assert s2 >= e1 + 0.19  # the same host: one at a time, the pause between
    assert took < 0.9  # the two hosts at once (one after the other: 1.2 s)


def test_episodes_sharing_the_shows_link_are_told_apart_by_guid():
    xml = '''<rss><channel>
      <item><title>Monday</title><link>https://show.example/the-daily</link><guid>abc-1</guid></item>
      <item><title>Tuesday</title><link>https://show.example/the-daily</link><guid>abc-2</guid></item>
      <item><title>Special</title><link>https://show.example/special</link><guid>abc-3</guid></item>
    </channel></rss>'''
    assert [i['url'] for i in sf.parse(xml)] == [
        'https://show.example/the-daily#abc-1', 'https://show.example/the-daily#abc-2', 'https://show.example/special']


def test_a_transcript_the_show_publishes_is_noted_timed_first():
    xml = '''<rss xmlns:podcast="https://podcastindex.org/namespace/1.0"><channel><item><title>Ep</title><link>https://s.example/1</link>
      <podcast:transcript url="https://t.example/1.txt" type="text/plain"/>
      <podcast:transcript url="https://t.example/1.vtt" type="text/vtt"/></item>
      <item><title>Plain only</title><link>https://s.example/2</link><podcast:transcript url="https://t.example/2.txt" type="text/plain"/></item>
    </channel></rss>'''
    items = sf.parse(xml)
    assert items[0]['transcript'] == 'https://t.example/1.vtt' and 'transcript' not in items[1]  # untimed: Whisper's
