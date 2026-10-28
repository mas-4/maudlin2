"""Breitbart's RSS feed read alongside its front page (Oct 28): feed items date an article's first sighting and never
become headlines. Against an in-memory database, with a trimmed copy of the real feed (tests/fixtures)."""
import os
from datetime import datetime as dt, timedelta as td

import pytest
from bs4 import BeautifulSoup as Soup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.feed_sightings as fs
import app.scraper as scraper
from app.models import Article, Base, FeedSighting, Headline
from app.scrapers.breitbart import Breitbart

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'breitbart_feed.xml')
NETANYAHU = 'https://www.breitbart.com/politics/2026/10/27/netanyahu-claims-decisive-majority-vows-national-right-wing-government/'
EARLIER = scraper.SCRAPE_TIME - td(hours=9)  # an earlier hourly run's feed read


def feed_items():
    with open(FIXTURE, 'rb') as f:
        return fs.parse(Soup(f.read(), 'xml'))


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(fs, 'Session', session)
    monkeypatch.setattr(scraper, 'Session', session)
    return session


def front_page_headline(url: str, title: str, pos: int) -> scraper.ArticleTuple:
    return scraper.ArticleTuple(url, f'<a href="{url}">{title}</a>', title, title.lower(), pos,
                                None, None, None, None, None, None, None, None)


def test_parse_reads_links_titles_and_dates():
    items = feed_items()
    assert len(items) == 4
    url, title, published = items[0]
    assert url == NETANYAHU  # the item's own <link>, not the atom:link beside it
    assert title.startswith('Netanyahu Claims ‘Decisive Majority,’')  # entities decoded
    assert published == dt(2026, 10, 28, 3, 30, 3)  # naive UTC
    assert items[2][1].startswith("EXCLUSIVE–Paxton's")


def test_record_keeps_the_first_sighting(db):
    items = feed_items()
    assert fs.record(1, items, now=EARLIER) == 4
    assert fs.record(1, items[:2], now=EARLIER + td(hours=1)) == 0
    with db() as s:
        row = s.query(FeedSighting).filter_by(url=NETANYAHU).one()
        assert (row.first_seen, row.last_seen) == (EARLIER, EARLIER + td(hours=1))
        assert row.published == dt(2026, 10, 28, 3, 30, 3)
        # Feed items are not front-page headlines, and make no articles of their own
        assert s.query(Headline).count() == 0 and s.query(Article).count() == 0
        assert fs.first_seen(s, 1, NETANYAHU) == EARLIER and fs.first_seen(s, 2, NETANYAHU) is None


def test_front_page_article_takes_the_feeds_earlier_sighting(db):
    bb = Breitbart()
    fs.record(bb.agency_id, feed_items(), now=EARLIER)
    other = 'https://www.breitbart.com/politics/2026/10/28/not-in-the-feed/'
    bb.batch_articles = {}
    with db() as s:
        bb.process(s, front_page_headline(NETANYAHU, 'Netanyahu claims decisive majority in Israel vote', 17))
        bb.process(s, front_page_headline(other, 'A story the feed never listed for us here', 3))
        s.commit()
    with db() as s:
        article = s.query(Article).filter_by(url=NETANYAHU).one()
        assert article.first_accessed == EARLIER  # first seen in the feed
        headline = article.headlines[0]
        assert headline.position == 17  # the headline is the front page's, at its time
        assert headline.first_accessed > EARLIER
        assert s.query(Article).filter_by(url=other).one().first_accessed > EARLIER
        assert s.query(Headline).count() == 2


def test_a_sighting_from_this_run_changes_nothing(db):
    bb = Breitbart()
    fs.record(bb.agency_id, feed_items(), now=scraper.SCRAPE_TIME + td(seconds=5))
    bb.batch_articles = {}
    with db() as s:
        bb.process(s, front_page_headline(NETANYAHU, 'Netanyahu claims decisive majority in Israel vote', 2))
        s.commit()
    with db() as s:
        article = s.query(Article).filter_by(url=NETANYAHU).one()
        assert article.first_accessed == article.headlines[0].first_accessed


def test_side_feed_is_one_request_with_our_user_agent(db, monkeypatch):
    calls = []

    class Response:
        def __init__(self):
            with open(FIXTURE, 'rb') as f:
                self.content = f.read()

        def raise_for_status(self):
            pass

    bb = Breitbart()
    monkeypatch.setattr(bb.rq, 'get', lambda url, headers, **kw: calls.append((url, headers)) or Response())
    bb.read_side_feed()
    assert calls == [(Breitbart.side_feed, {'User-Agent': 'Maudlin Bot'})]
    assert len(bb.feed_items) == 4


def test_a_failed_feed_read_leaves_no_items(db, monkeypatch):
    bb = Breitbart()

    def down(*a, **kw):
        raise ConnectionError('feed down')
    monkeypatch.setattr(bb.rq, 'get', down)
    bb.read_side_feed()
    assert bb.feed_items == []
