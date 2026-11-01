"""The Bluesky drafts: their pure parts: whole lines under the limit, wordings alike but for quotes counted once, marks."""
from datetime import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app import post_drafts as p
from app.models import Base, FrontPageStory


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


def front_page(session, at, titles):
    with session() as s:
        s.add_all(FrontPageStory(at=at, rank=i, title=t, outlets=1) for i, t in enumerate(titles, 1))
        s.commit()


def test_fits_keeps_whole_lines_and_counts_the_rest():
    lines = [f'• {"word " * 20}{i}' for i in range(10)]
    text = p.fits('Head:', lines)
    assert len(text) <= p.LIMIT
    shown = [x for x in text.split('\n') if x.startswith('•')]
    assert all(x in lines for x in shown)  # never a line cut short
    assert text.endswith(f'+{10 - len(shown)} more')


def test_fits_everything_when_it_fits():
    assert p.fits('Head:', ['a', 'b'], '\n(tail)') == 'Head:\na\nb\n(tail)'


def test_same_words_sets_quotes_and_case_aside():
    assert p.same_words('I’m in My 30s. “Old” People') == p.same_words("I'm in my 30s. \"Old\" people")
    assert p.same_words('One wording') != p.same_words('Another wording')


def test_marks(db, monkeypatch):
    monkeypatch.setattr(p, 'MAKERS', [lambda now: [p.draft('rewrite', 'x', 't', 'https://bignews.day/edits.html')]])
    p.make(dt(2026, 11, 1, 20))
    state = p.mark('rewrite:x', 'down', '  too   dull ')
    assert state['drafts'][0]['mark'] == 'down' and state['drafts'][0]['note'] == 'too dull'
    assert next(f for f in state['formats'] if f['id'] == 'rewrite')['down'] == 1
    p.make(dt(2026, 11, 1, 21))  # drafted again: the mark stays
    assert p.state()['drafts'][0]['mark'] == 'down'
    with pytest.raises(ValueError):
        p.mark('rewrite:x', 'maybe')
    with pytest.raises(ValueError):
        p.mark('nothing', 'up')


def test_front_page_theme_and_its_biggest_hour_kept(db, monkeypatch):
    titles = ['Shooting after football game leaves 1 dead', 'Shootings in Dallas leave 4 dead',
              'Pregnant woman killed in Halloween store shooting', 'Gunman opened fire at a mall', 'Senate race tightens',
              'Israel under fire over strikes']
    front_page(db, dt(2026, 11, 1, 21), titles)
    found = {d['key'].split('|')[1]: d for d in p.front_page_themes(dt(2026, 11, 1, 21))}
    assert set(found) == {'shootings'}  # gunfire and "under fire" are not fires
    assert found['shootings']['text'].startswith('🚨 4 of the top 6 stories right now are about shootings:')
    monkeypatch.setattr(p, 'MAKERS', [p.front_page_themes])
    p.make(dt(2026, 11, 1, 21))
    front_page(db, dt(2026, 11, 1, 22), titles[1:4])
    p.make(dt(2026, 11, 1, 22))
    kept = p.state()['drafts'][0]
    assert kept['peak'] == 4 and kept['seen'] == '2026-11-01T22:00' and '4 of the top 6' in kept['text']
