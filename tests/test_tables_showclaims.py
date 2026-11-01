"""app/tables/showclaims.py: the shows' and the Focus Group's claims, what the shows retold, the shows' published
transcripts and the episodes read again, kept in data.db; and their one-time import from the JSON files."""
import json
import os
from datetime import datetime as dt

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.models import Base
from app.tables import showclaims as t


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


SHOW_EP = {'source': 'pod_x', 'show': 'Show X', 'lean': 'left', 'title': 'Ep 1', 'date': '2026-10-07', 'read': 2,
           'chunks': 3, 'claims': [{'claim': 'A is B.', 'quote': 'a is b', 'speaker': 'host', 'at': 0},
                                   {'claim': 'C is D.', 'quote': 'c is d', 'speaker': 'clip', 'at': 60, 'reread': '2026-10-28'}],
           'dropped': [{'claim': 'E.', 'quote': 'e', 'speaker': '', 'at': 0, 'why': 'quote not in the transcript'}]}
FG_EP = {'title': 'S6 Ep1', 'date': '2026-10-03', 'read': 1, 'chunks': 1, 'dropped': [],
         'claims': [{'claim': 'Prices are up.', 'quote': 'prices up', 'side': 'Trump voter', 'at': 0, 'support': 'checked'}]}
RETOLD = [{'claim': 'A is B.', 'shows': ['Show X', 'Show Y'], 'tellings': 2, 'leans': {'left': 2}, 'speakers': {'host': 2},
           'date': '2026-10-08', 'ref': 'u1', 'told': [
               {'show': 'Show X', 'url': 'u1', 'at': 0, 'speaker': 'host', 'claim': 'A is B.', 'quote': 'a is b'},
               {'show': 'Show Y', 'url': 'u2', 'at': 30, 'speaker': 'host', 'claim': 'A is really B.', 'quote': 'a b'}]},
          {'claim': 'Z.', 'shows': ['Show Y', 'Show Z'], 'tellings': 2, 'leans': {}, 'speakers': {}, 'date': '2026-10-01',
           'ref': 'u3', 'told': []}]


def test_episodes_round_trip_in_their_old_shape(db):
    from app.analysis import focus_group, show_claims
    show_claims.save({'u1': SHOW_EP})
    focus_group.save({'f1': FG_EP})
    assert show_claims.load() == {'u1': SHOW_EP}
    assert focus_group.load() == {'f1': FG_EP}  # each reader sees only its own


def test_saving_some_episodes_leaves_the_others(db):
    from app.analysis import show_claims
    show_claims.save({'u1': SHOW_EP, 'u2': dict(SHOW_EP, title='Ep 2')})
    store = show_claims.load()
    store['u2']['claims'].append({'claim': 'New.', 'quote': 'n', 'speaker': 'caller', 'at': 120})
    store['u1']['claims'] = []  # changed here, but not saved
    show_claims.save(store, ['u2'])
    got = show_claims.load()
    assert len(got['u1']['claims']) == 2 and got['u2']['claims'][-1]['claim'] == 'New.'
    with db() as s:
        assert s.scalar(select(func.count()).select_from(t.ShowClaim)) == 2 + 3 + 2  # u1's, u2's, both dropped


def test_retold_is_replaced_whole_and_kept_in_rank_order(db):
    from app.analysis import show_claims
    assert not t.any_retold() and show_claims.kept_retold() == []
    t.save_retold(RETOLD)
    assert show_claims.kept_retold() == RETOLD
    assert [c['source'] for c in show_claims.claims()] == [show_claims.SOURCE] * 2
    t.save_retold(RETOLD[1:])
    assert show_claims.kept_retold() == RETOLD[1:]
    with db() as s:
        assert s.scalar(select(func.count()).select_from(t.RetoldTelling)) == 0


def test_published_transcript_links_keep_the_newest(db, monkeypatch):
    from app import sidefeeds
    monkeypatch.setattr(sidefeeds, 'KEEP_TRANSCRIPTS', 2)
    sidefeeds.save_transcript_links({'i1': 't1', 'i2': 't2'}, dt(2026, 11, 1, 10))
    sidefeeds.save_transcript_links({'i3': 't3', 'i1': 't1b'}, dt(2026, 11, 1, 11))
    assert sidefeeds.transcript_links(['i1', 'i2', 'i3', 'i4']) == {'i1': 't1b', 'i3': 't3'}  # i2 the oldest, gone


def test_import_reads_every_file_and_moves_the_ties_to_the_cache(db, tmp_path):
    from scripts.json_import import showclaims as imp
    from app.analysis import focus_group, show_claims
    data, cache = tmp_path / 'data', tmp_path / 'data' / 'cache'
    data.mkdir()
    files = {'show_claims.json': {'u1': SHOW_EP}, 'focus_group_claims.json': {'f1': FG_EP},
             'show_claims_retold.json': RETOLD, 'show_story_ties.json': {'abc': 12, 'def': 0},
             'feed_transcripts.json': {'i1': 't1', 'i2': 't2'},
             'retranscribe_claims.json': {'u1': {'at': '2026-10-31T11:55:00', 'found': 37, 'added': 36}}}
    for name, value in files.items():
        (data / name).write_text(json.dumps(value))
    with db() as s:
        counts = imp.run(s, str(data), str(cache))
        s.commit()
    assert counts == {'show_claims.json': 1, 'focus_group_claims.json': 1, 'show_claims_retold.json': 2,
                      'feed_transcripts.json': 2, 'retranscribe_claims.json': 1, 'show_story_ties.json': 1}
    assert show_claims.load() == {'u1': SHOW_EP} and focus_group.load() == {'f1': FG_EP}
    assert show_claims.kept_retold() == RETOLD
    with db() as s:
        order = s.scalars(select(t.FeedTranscript.item_url).order_by(t.FeedTranscript.seen)).all()
        assert order == ['i1', 'i2']  # the file's order, oldest first
        assert s.get(t.RetranscribedClaims, 'u1').added == 36
    assert json.loads((cache / 'show_story_ties.json').read_text()) == {'abc': 12, 'def': 0}
    assert not (data / 'show_story_ties.json').exists() and (data / 'show_claims.json').exists()


def test_import_of_an_empty_folder_counts_nothing(db, tmp_path):
    from scripts.json_import import showclaims as imp
    with db() as s:
        counts = imp.run(s, str(tmp_path), os.path.join(tmp_path, 'cache'))
    assert set(counts.values()) == {0}
