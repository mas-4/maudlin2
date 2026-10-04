"""Headline A/B tests (#119): recording Slate's wordings each run and reading tests back, against an in-memory
database; plus the Slate parser's variant capture."""
from datetime import datetime as dt, timedelta as td

import pytest
from bs4 import BeautifulSoup as Soup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.analysis.abtests as ab
from app.models import Agency, Base, HeadlineVariant
from app.scrapers.slate import Slate

URL = 'https://slate.com/news/2026/10/a.html'
T0 = dt(2026, 10, 4, 12)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(ab, 'Session', session)
    with session() as s:
        s.add(Agency(name='Slate', url='https://slate.com', _bias=-2, _credibility=0, _country=0))
        s.commit()
    return session


def test_untested_cards_are_not_saved(db):
    ab.record(1, [(URL, ['Only one wording'], 'Only one wording')], now=T0)
    with db() as s:
        assert s.query(HeadlineVariant).count() == 0


def test_running_then_won(db):
    ab.record(1, [(URL, ['Wording A', 'Wording B', 'Wording  C'], 'Wording B')], now=T0)
    ab.record(1, [(URL, ['Wording A', 'Wording B', 'Wording C'], 'Wording B')], now=T0 + td(hours=1))
    [t] = ab.tests(now=T0 + td(hours=1))
    assert t['state'] == 'running' and len(t['variants']) == 3  # whitespace differences are one wording
    assert {v['text'] for v in t['variants'] if v['default']} == {'Wording B'}
    # The test ends: the card shows one wording, and only that one is seen from now on
    ab.record(1, [(URL, ['Wording A'], 'Wording A')], now=T0 + td(hours=3))
    [t] = ab.tests(now=T0 + td(hours=3))
    assert t['state'] == 'won' and t['winner'] == 'Wording A'
    assert t['variants'][0]['won'] and t['variants'][0]['hours'] == 3
    assert [v['hours'] for v in t['variants'][1:]] == [1, 1]


def test_off_the_page_without_a_winner(db):
    ab.record(1, [(URL, ['A wording', 'B wording'], 'A wording')], now=T0)
    assert ab.tests(now=T0 + td(hours=2))[0]['state'] == 'running'
    assert ab.tests(now=T0 + td(hours=7))[0]['state'] == 'ended'


def test_old_tests_drop_out(db):
    ab.record(1, [(URL, ['A wording', 'B wording'], 'A wording')], now=T0)
    assert ab.tests(now=T0 + td(days=15)) == []


def test_slate_parser_keeps_default_and_every_wording():
    html = '''<a href="/news/2026/10/a.html"><h2 class="story-card__headline"><span id="x">
        <span data-promoline-variant="0" hidden="">First <em>wording </em>here</span>
        <span data-promoline-variant="1" hidden="">Second wording here</span></span>
        <script>reveal()</script><noscript>Second wording here</noscript></h2></a>
        <a href="/news/2026/10/b.html"><h2 class="story-card__headline">Plain headline on the card</h2></a>'''
    scraper = Slate.__new__(Slate)
    scraper.downstream, scraper.variants = [], []
    scraper.setup(Soup(html, 'lxml'))
    assert [t for _, t in scraper.downstream] == ['Second wording here', 'Plain headline on the card']
    url, wordings, default = scraper.variants[0]
    assert [ab._clean(w) for w in wordings] == ['First wording here', 'Second wording here']
    assert default == 'Second wording here'
    assert scraper.variants[1][1] == ['Plain headline on the card']
