"""app/sinclair.py: Sinclair's stations and The National Desk read from their homepages for research (Oct 28). On
trimmed copies of the real homepages (tests/fixtures/sinclair_*.html) and an in-memory database."""
import os
from datetime import datetime as dt, timedelta as td

import pytest
from bs4 import BeautifulSoup as Soup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.scraper as scraper
from app import sinclair
from app.models import Article, Base, Headline, StationSighting
from app.registry import ResearchScrapers, Scrapers
from app.scrapers.komo import KOMO
from app.scrapers.nationaldesk import NationalDesk
from app.scrapers.wbff import WBFF
from app.scrapers.wjla import WJLA

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
SOCIALISM = 'white-house-releases-warning-about-socialism-and-what-it-will-cost-american-families-dsa-alexandria-ocasio-cortez'
COLLEGE_PARK = ('college-park-cornerstone-grill-liquor-license-maryland-suspension-management-umd-bar-closure-underage-'
                'drinking-city-council-prince-georges-halloween-alcohol-employees-jobs')
HAZMAT = ('hazmat-crews-respond-at-kentridge-high-school-2-hospitalized-after-illness-reports-king-county-medic-school-'
          'students-safety-school-emergency')
NOW = dt(2026, 10, 28, 15)


def page(name: str) -> Soup:
    with open(os.path.join(FIXTURES, f'sinclair_{name}.html'), 'rb') as f:
        return Soup(f.read(), 'lxml')


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(sinclair, 'Session', session)
    monkeypatch.setattr(scraper, 'Session', session)
    return session


# <editor-fold desc="The homepages">
def test_a_station_homepage_gives_its_headlines_without_summaries_ads_or_repeats():
    items = sinclair.station_items(page('komo'), 'https://komonews.com/')
    urls = [u for u, _ in items]
    assert items[0] == ('https://komonews.com/news/politics/midterm-election-less-than-a-week-away-key-races-continue-'
                        'to-draw-controversy',
                        'With midterm election less than a week away, key races continue to draw controversy')
    # The trending sidebar's repeat (?teaserSource=trending) is the same link, kept once at its first place
    assert sum(u.endswith(HAZMAT) for u in urls) == 1
    assert all('?' not in u for u in urls)
    assert not any('/sponsored/' in u for u in urls)  # a paid post
    assert 'https://komonews.com/news/nation-world' not in urls  # the section's "See More" link isn't a teaser
    assert f'https://komonews.com/news/nation-world/{SOCIALISM}' in urls
    assert any(u.startswith('https://seattlerefined.com/') for u in urls)  # Sinclair's lifestyle site, on the page
    assert all(len(t.split()) < 20 for _, t in items)  # headlines only, never the summary under them


def test_a_byte_order_mark_is_not_part_of_the_headline():
    items = dict(sinclair.station_items(page('wjla'), 'https://wjla.com/'))
    assert items[f'https://wjla.com/news/local/{COLLEGE_PARK}'] == \
        "College Park's Cornerstone Grill faces 90-day liquor license suspension"


def test_the_national_desk_homepage():
    items = sinclair.national_desk_items(page('tnd'), 'https://thenationaldesk.com/')
    assert [(u, t) for u, t, _ in items][0] == (
        f'https://thenationaldesk.com/news/americas-news-now/{SOCIALISM}',
        'White House releases warning about socialism and what it will cost American families')
    assert len(items) == 4  # "Skip to main content" has no headline
    assert items[-1][1].startswith('Fact Check Team:')


def test_slug_and_section():
    url = f'https://foxbaltimore.com/station/share/{SOCIALISM}'
    assert sinclair.slug(url) == SOCIALISM and sinclair.section(url) == 'station/share'
    assert sinclair.slug(f'https://komonews.com/news/nation-world/{SOCIALISM}') == SOCIALISM
# </editor-fold>


# <editor-fold desc="Sightings and the syndication rule">
def test_record_keeps_the_first_sighting_and_the_highest_place(db):
    items = [('https://kutv.com/news/local/a', 'A headline'), ('https://kutv.com/news/local/b', 'B headline')]
    assert sinclair.record(1, items, now=NOW) == 2
    assert sinclair.record(1, items[::-1], now=NOW + td(hours=1)) == 0
    assert sinclair.record(1, [('https://kutv.com/news/local/a', 'A headline, reworded')], now=NOW + td(hours=2)) == 1
    with db() as s:
        a = s.query(StationSighting).filter_by(title='A headline').one()
        b = s.query(StationSighting).filter_by(title='B headline').one()
        assert (a.first_seen, a.last_seen, a.position, a.slug) == (NOW, NOW + td(hours=1), 0, 'a')
        assert b.position == 0  # second at first, then on top
        assert s.query(StationSighting).filter_by(url='https://kutv.com/news/local/a').count() == 2
        # Sightings, never headlines
        assert s.query(Headline).count() == 0 and s.query(Article).count() == 0


def read_all(db):
    """Each site's fixture recorded as one run, as the hourly run would"""
    for cls, name in [(KOMO, 'komo'), (WJLA, 'wjla'), (WBFF, 'wbff')]:
        station = cls()
        station.setup(page(name))
        sinclair.record(station.agency_id, station.sightings, now=NOW)
    tnd = NationalDesk()
    tnd.setup(page('tnd'))
    sinclair.record(tnd.agency_id, tnd.sightings, now=NOW)


def test_a_syndicated_piece_is_kept_on_every_station_and_tied_to_the_national_desk(db):
    read_all(db)
    df = sinclair.sightings()
    piece = df[df['slug'] == SOCIALISM]
    # Nothing dropped because another site saved the same headline first: each station keeps its own sighting
    assert sorted(piece['outlet']) == ['KOMO Seattle', 'The National Desk', 'WBFF Baltimore', 'WJLA Washington']
    assert piece['national_desk'].all() and (piece['sites'] == 4).all()
    assert set(piece['section']) == {'news/nation-world', 'station/share', 'news/americas-news-now'}


def test_neighbours_sharing_a_local_piece_is_syndicated_but_not_the_national_desk(db):
    read_all(db)
    df = sinclair.sightings()
    shared = df[df['slug'] == COLLEGE_PARK]
    assert sorted(shared['outlet']) == ['WBFF Baltimore', 'WJLA Washington']
    assert (shared['sites'] == 2).all() and not shared['national_desk'].any()
    assert set(shared['section']) == {'news/local'}
    local = df[df['slug'] == HAZMAT]
    assert list(local['outlet']) == ['KOMO Seattle'] and (local['sites'] == 1).all()
    assert not local['national_desk'].any()


def test_a_national_desk_piece_seen_earlier_still_counts(db):
    tnd = NationalDesk()
    tnd.setup(page('tnd'))
    sinclair.record(tnd.agency_id, tnd.sightings, now=NOW - td(days=1))
    komo = KOMO()
    komo.setup(page('komo'))
    sinclair.record(komo.agency_id, komo.sightings, now=NOW)
    df = sinclair.sightings(since=NOW)
    assert set(df['outlet']) == {'KOMO Seattle'}  # since: rows last seen then; the flag still looks at all of them
    assert df.loc[df['slug'] == SOCIALISM, 'national_desk'].all()
    assert df.loc[df['slug'].str.startswith('christina-applegate'), 'national_desk'].all()


def test_no_sightings_is_an_empty_frame(db):
    df = sinclair.sightings()
    assert df.empty and {'outlet', 'slug', 'section', 'national_desk', 'sites'} <= set(df.columns)
# </editor-fold>


# <editor-fold desc="The scrapers">
def test_stations_are_research_only_and_the_national_desk_an_outlet():
    research = {s.agency for s in ResearchScrapers}
    assert research == {'KOMO Seattle', 'WJLA Washington', 'KUTV Salt Lake City', 'WPEC West Palm Beach',
                        'WBFF Baltimore'}
    outlets = {s.agency for s in Scrapers}
    assert not research & outlets  # outside every count made from Scrapers
    assert 'The National Desk' in outlets
    assert all(issubclass(s, sinclair.StationScraper) for s in ResearchScrapers)
    assert all(len(s.agency) <= 30 for s in ResearchScrapers + [NationalDesk])  # agency.name is String(30)


def test_a_station_run_records_sightings_and_reports_its_numbers(db, monkeypatch):
    reports = []
    monkeypatch.setattr(sinclair.scraper_health, 'record', lambda agency, url, **kw: reports.append((agency, kw)))
    komo = KOMO()
    komo.setup(page('komo'))
    komo.post_run()
    komo.post_run()  # the next hour, nothing new
    assert reports == [('KOMO Seattle', {'found': 6, 'kept': 6, 'added': 6}),
                       ('KOMO Seattle', {'found': 6, 'kept': 6, 'added': 0})]
    with db() as s:
        assert s.query(StationSighting).count() == 6 and s.query(Headline).count() == 0


def test_the_national_desk_saves_headlines_and_sightings(db, monkeypatch):
    tnd = NationalDesk()
    tnd.setup(page('tnd'))
    assert len(tnd.downstream) == 4
    href, tag = tnd.downstream[0]
    assert href.endswith(SOCIALISM) and tag.get_text(strip=True).startswith('White House releases warning')
    monkeypatch.setattr(scraper.Scraper, 'post_run', lambda self: None)  # its headlines, as for any outlet
    tnd.post_run()
    with db() as s:
        assert s.query(StationSighting).filter_by(agency_id=tnd.agency_id).count() == 4
# </editor-fold>
