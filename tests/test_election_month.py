"""#151 aggregators as curators, #152 wire share, #133 trend arrows: offline, with fakes and an in-memory database."""
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.analysis.trends_meter as tm
import app.analysis.wire as wire
import app.site.page_headlines as ph
from app.models import Base


def fake_embed(titles):
    """Titles that share their first three words embed to the same vector."""
    keys = {}
    out = []
    for t in titles:
        k = ' '.join(t.lower().split()[:3])
        keys.setdefault(k, len(keys))
        v = np.zeros(64)
        v[keys[k] % 64] = 1
        out.append(v)
    return np.array(out)


def unit_vectors(texts):
    v = fake_embed(list(texts)).astype(float)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9), 'potion-base-8M'


def test_headline_vectors_fall_back_to_the_static_model(monkeypatch):
    from app.analysis import clustering
    monkeypatch.setattr(clustering, 'ollama_embed', lambda texts: (_ for _ in ()).throw(ConnectionError('down')))
    monkeypatch.setattr(clustering, 'embed', fake_embed)
    v, model = clustering.headline_vectors(['a b', 'c d'])
    assert model == 'potion-base-8M' and np.allclose(np.linalg.norm(v, axis=1), 1)
    assert set(wire.WIRE_MATCH) == set(ph.CURATOR_MATCH) == {clustering.STORY_MODEL, model}  # a threshold for each


# #152 wire share
def test_wire_copy_needs_near_identical_words(monkeypatch):
    monkeypatch.setattr(wire, 'headline_vectors', unit_vectors)
    df = pd.DataFrame({'title': ['Senate passes stopgap bill to avert shutdown',  # AP
                                 'Senate passes stopgap bill to avert shutdown',  # verbatim copy
                                 'Senate passes stopgap: what it means for you and your family',  # same lead words, rewrite
                                 'Something else entirely happened'],
                       'agency': ['AP', 'CNBC', 'CNBC', 'CNBC']})
    assert wire.wire_copies(df).tolist() == [False, True, False, False]


def test_wire_copy_without_wires_is_all_false(monkeypatch):
    monkeypatch.setattr(wire, 'headline_vectors', unit_vectors)
    df = pd.DataFrame({'title': ['A thing', 'Another'], 'agency': ['CNBC', 'Fox News']})
    assert not wire.wire_copies(df).any()


# #151 aggregators as curators
def test_curators_link_live_aggregator_headlines_to_stories(monkeypatch):
    monkeypatch.setattr(ph, 'headline_vectors', unit_vectors)
    page = ph.HeadlinesPage.__new__(ph.HeadlinesPage)
    page.curated = pd.DataFrame({'title': ['Trump holds rally tonight', 'Unrelated aggregator link here'],
                                 'agency': ['Drudge Report', 'Google News']})
    df = pd.DataFrame({'title': ['Trump holds rally in Ohio', 'Storm hits the coast'], 'cluster': [1, 2]})
    clusters = [{'cluster': 1}, {'cluster': 2}]
    page.curators(df, clusters)
    assert clusters[0]['curators'] == ['Drudge Report'] and clusters[1]['curators'] == []


def test_aggregators_listed():
    assert {'Google News', 'Drudge Report'} <= ph.AGGREGATORS


# #133 trend arrows
@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(tm, 'Session', sessionmaker(bind=engine))


@pytest.mark.parametrize('change, n', [(0.05, 0), (0.15, 1), (0.4, 2), (0.7, 3), (-0.4, 2)])
def test_arrows_scale_with_movement(change, n):
    out = tm.arrows(change, tm.LEAN_STEPS, '▶', '◀')
    assert len(out) == n and (n == 0 or out[0] == ('▶' if change > 0 else '◀'))


def test_trends_need_two_hours_of_history(db):
    now = dt(2026, 10, 4, 12)
    tm.save({1: {'lean': 0.0, 'mood': 0.0, 'outlets': 6}, 2: {'lean': 0.0, 'mood': 0.0, 'outlets': 6}}, now - td(hours=4))
    tm.save({2: {'lean': 0.0, 'mood': 0.0, 'outlets': 6}}, now - td(hours=1))
    tm.save({1: {'lean': -0.5, 'mood': 0.3, 'outlets': 12}, 2: {'lean': 0.9, 'mood': -0.9, 'outlets': 8}}, now)
    out = tm.trends([1, 2], now)
    assert out[1]['lean']['arrows'] == '◀◀' and out[1]['mood']['arrows'] == '▲▲'
    assert 'outlets 6 → 12' in out[1]['lean']['tip'] and 'over 4 hours' in out[1]['mood']['tip']
    assert out[2]['lean']['arrows'] == '▶▶▶' and out[2]['mood']['arrows'] == '▼▼▼'


def test_trends_ignore_short_or_old_history(db):
    now = dt(2026, 10, 4, 12)
    tm.save({1: {'lean': 0.0, 'mood': 0.0, 'outlets': 6}}, now - td(hours=10))  # too old
    tm.save({1: {'lean': 0.9, 'mood': 0.9, 'outlets': 6}}, now - td(hours=1))
    tm.save({1: {'lean': 0.0, 'mood': 0.0, 'outlets': 6}}, now)
    assert tm.trends([1], now) == {}  # only an hour of recent history
