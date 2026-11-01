"""app/site/wordcloudgen.py: words new to the cloud (✨), from the clouds of the day before."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.models import Base
from app.site import wordcloudgen as wc
from app.tables.records import CloudWord


@pytest.fixture(autouse=True)
def db(monkeypatch):
    """An in-memory data.db: the data folder is production's"""
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


def words(*texts):
    return [{'text': t, 'tip': t} for t in texts]


def test_new_only_once_the_history_covers_enough(db):
    now = datetime(2026, 10, 5, 12)
    assert not any(w['new'] for w in wc.mark_new(words('cornell', 'tariffs'), now - timedelta(hours=3)))  # too little history
    out = wc.mark_new(words('cornell', 'leavitt'), now)
    assert {w['text']: w['new'] for w in out} == {'cornell': False, 'leavitt': False}  # 3 hours of history: not yet
    with db() as s:  # pretend the first cloud was ten hours ago
        s.query(CloudWord).filter(CloudWord.at == now - timedelta(hours=3)).update({'at': now - timedelta(hours=10)})
        s.commit()
    out = wc.mark_new(words('cornell', 'alito'), now + timedelta(hours=1), save=False)
    assert {w['text']: w['new'] for w in out} == {'cornell': False, 'alito': True}
    assert out[1]['tip'].endswith('✨ new to the cloud')


def test_a_word_absent_for_a_day_is_new_again():
    now = datetime(2026, 10, 5, 12)
    wc.keep_cloud(now - timedelta(hours=30), ['hastert'])
    wc.keep_cloud(now - timedelta(hours=20), ['cornell'])
    out = wc.mark_new(words('hastert', 'cornell'), now, save=False)
    assert {w['text']: w['new'] for w in out} == {'hastert': True, 'cornell': False}
