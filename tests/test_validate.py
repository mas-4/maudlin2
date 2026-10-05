"""scripts/validate.py: a label check's verdict goes straight onto the headline as hand labels."""
import importlib.util
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis import newsfilter
from app.models import Agency, Article, Base, Headline

spec = importlib.util.spec_from_file_location('validate', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'validate.py'))
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(validate, 'Session', session)
    with session() as s:
        agency = Agency(name='AP', url='x', _bias=0, _credibility=0, _country=0)
        h = Headline(title='Storm hits coast', article=Article(url='u', agency=agency), event_score=-1.0,
                     loaded_score=1.0, emotion='fear', emotion_ranks='fear,sadness', scored_by='qwen3:8b rubric:x')
        s.add(h)
        s.commit()
        return session, h.id


def test_a_correction_becomes_the_headlines_hand_labels(db):
    session, hid = db
    validate.apply_label({'headline_id': hid, 'model': {'mood': -1, 'spice': 1, 'feelings': ['fear', 'sadness']},
                          'mood': {'ok': False, 'should': -2}, 'spice': {'ok': True},
                          'feelings': {'ok': False, 'should': ['sadness', 'surprise']}})
    with session() as s:
        h = s.get(Headline, hid)
        assert (h.event_score, h.loaded_score, h.emotion_ranks, h.scored_by) == (-2.0, 1.0, 'sadness,surprise',
                                                                               newsfilter.HAND_JUDGE)


def test_an_incomplete_verdict_changes_nothing(db):
    session, hid = db
    with pytest.raises(ValueError):
        validate.apply_label({'headline_id': hid, 'model': {'mood': -1, 'spice': 1, 'feelings': []},
                              'mood': {'ok': True}})
    with session() as s:
        assert s.get(Headline, hid).scored_by == 'qwen3:8b rubric:x'
