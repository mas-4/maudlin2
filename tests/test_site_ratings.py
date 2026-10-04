"""app/ratings.py and ratings.csv. `apply` and `unrated` run against an in-memory database, never data/data.db."""
import csv
from collections import Counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ratings
from app.models import Agency, Base
from app.registry import Scrapers


@pytest.fixture(scope='module')
def rows():
    return ratings.load()


def raw_rows():
    with open(ratings.RATINGS_FILE, newline='') as f:
        return list(csv.DictReader(line for line in f if not line.startswith('#')))


# <editor-fold desc="ratings.csv">
def test_csv_has_the_expected_columns():
    with open(ratings.RATINGS_FILE, newline='') as f:
        header = next(csv.reader(line for line in f if not line.startswith('#')))
    assert header == ['outlet', 'lean', 'allsides_url', 'reliability', 'reliability_note']


def test_csv_has_no_duplicate_outlets():
    names = [r['outlet'] for r in raw_rows()]
    assert [n for n, k in Counter(names).items() if k > 1] == []


def test_csv_rows_are_complete(rows):
    for name, r in rows.items():
        assert None not in r, f'{name}: extra fields'
        assert all(v is not None for v in r.values()), f'{name}: missing fields'
        assert name == name.strip() and name, repr(name)


def test_lean_values_are_known(rows):
    bad = {n: r['lean'] for n, r in rows.items() if r['lean'].strip() and r['lean'].strip() not in ratings.LEAN}
    assert bad == {}


def test_reliability_values_are_known(rows):
    bad = {n: r['reliability'] for n, r in rows.items()
           if r['reliability'].strip() and r['reliability'].strip() not in ratings.RELIABILITY}
    assert bad == {}


def test_rated_outlets_cite_allsides(rows):
    """Every lean has its AllSides page (an unrated outlet may still link to a page AllSides keeps for it)."""
    for name, r in rows.items():
        if r['lean'].strip():
            assert r['allsides_url'].startswith('https://www.allsides.com/'), name
        if r['allsides_url'].strip():
            assert r['allsides_url'].startswith('https://www.allsides.com/'), name


def test_csv_and_registry_list_the_same_outlets(rows):
    registry = {s.agency for s in Scrapers}
    assert set(rows) - registry == set(), 'rated outlets with no scraper'
    assert registry - set(rows) == set(), 'scraped outlets missing from ratings.csv (apply warns and shows them unrated)'


def test_lean_scale():
    assert ratings.LEAN == {'Left': -2, 'Lean Left': -1, 'Center': 0, 'Lean Right': 1, 'Right': 2}
    assert sorted(ratings.LEAN.values()) == [-2, -1, 0, 1, 2]
    assert len(set(ratings.RELIABILITY)) == len(ratings.RELIABILITY) == 4


def test_both_sides_are_rated(rows):
    leans = Counter(ratings.LEAN[r['lean']] for r in rows.values() if r['lean'])
    assert leans[-2] + leans[-1] > 0 and leans[1] + leans[2] > 0 and leans[0] > 0
# </editor-fold>


# <editor-fold desc="load">
SAMPLE = """# a comment line
outlet,lean,allsides_url,reliability,reliability_note
Alpha,Lean Left,https://www.allsides.com/a,generally reliable,
# another comment
Beta,,,,
Gamma,Far Left,https://www.allsides.com/g,mostly fine,"note, with comma"
Delta,Right,  ,deprecated,  spaced note
"""


@pytest.fixture
def sample_csv(tmp_path, monkeypatch):
    path = tmp_path / 'ratings.csv'
    path.write_text(SAMPLE)
    monkeypatch.setattr(ratings, 'RATINGS_FILE', str(path))
    return path


def test_load_skips_comments_and_keys_by_outlet(sample_csv):
    loaded = ratings.load()
    assert list(loaded) == ['Alpha', 'Beta', 'Gamma', 'Delta']
    assert loaded['Alpha']['lean'] == 'Lean Left'
    assert loaded['Gamma']['reliability_note'] == 'note, with comma'
    assert loaded['Beta']['lean'] == ''
# </editor-fold>


# <editor-fold desc="apply and unrated on a scratch database">
@pytest.fixture
def scratch_db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(ratings, 'Session', session)
    with session() as s:
        for i, name in enumerate(['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon']):
            s.add(Agency(name=name, url=f'https://{name.lower()}.example', _bias=3, _credibility=0, _country=0,
                         lean_rated=True, reliability='stale', reliability_note='stale'))
        s.commit()
    yield session
    engine.dispose()


def agencies(session):
    with session() as s:
        return {a.name: (a.lean_rated, a._bias, a.lean_url, a.reliability, a.reliability_note)  # noqa prot attr
                for a in s.query(Agency).all()}


def test_apply_writes_ratings(sample_csv, scratch_db):
    ratings.apply()
    got = agencies(scratch_db)
    assert got['Alpha'] == (True, -1, 'https://www.allsides.com/a', 'generally reliable', None)
    assert got['Delta'] == (True, 2, None, 'deprecated', 'spaced note')


def test_apply_blank_lean_is_unrated(sample_csv, scratch_db):
    ratings.apply()
    assert agencies(scratch_db)['Beta'] == (False, 0, None, None, None)


def test_apply_unknown_values_are_dropped(sample_csv, scratch_db):
    """'Far Left' isn't on AllSides' scale and 'mostly fine' isn't a WP:RSP status: both are left unset."""
    ratings.apply()
    lean_rated, bias, url, reliability, note = agencies(scratch_db)['Gamma']
    assert (lean_rated, bias, reliability) == (False, 0, None)
    assert url == 'https://www.allsides.com/g' and note == 'note, with comma'


def test_apply_outlet_missing_from_csv_is_unrated(sample_csv, scratch_db):
    ratings.apply()
    assert agencies(scratch_db)['Epsilon'] == (False, 0, None, None, None)


def test_unrated_lists_outlets_without_a_lean(sample_csv, scratch_db):
    assert ratings.unrated() == set()  # all start rated
    ratings.apply()
    assert ratings.unrated() == {'Beta', 'Gamma', 'Epsilon'}
# </editor-fold>
