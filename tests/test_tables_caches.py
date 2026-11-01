"""The caches group (Nov 1): the model answers' files under Config.cache, the fact-checks' labels in data.db, and the
one-time import that moves them."""
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.analysis import factchecks
from app.models import Base
from app.tables.caches import FactcheckLabel
from scripts.json_import import caches as importer


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


LABEL = {'claim': 'The moon landing was staged', 'context': 'Old posts again.', 'genre': 'rumor', 'motif': 'hoax',
         'politics': False, 'rumor_class': 'wedge', 'secret_plot': True, 'conspiracy': 'national', 'family': 'hoaxes',
         'model': 'gemma4:26b', 'read': 'piece', 'claim from the piece': 'Posts say the landing was filmed'}


def test_labels_keep_their_shape_through_the_table(db):
    factchecks.save_labels({'https://a.example/1': LABEL, 'https://a.example/2': {'claim': 'X', 'genre': 'legend'}})
    assert factchecks.load_labels() == {'https://a.example/1': LABEL,
                                        'https://a.example/2': {'claim': 'X', 'genre': 'legend'}}
    factchecks.save_labels({'https://a.example/2': {'claim': 'Y'}})  # read again: replaced whole
    assert factchecks.load_labels()['https://a.example/2'] == {'claim': 'Y'}


def test_the_caches_live_under_the_cache_folder():
    from app import chyrons, episode_kind, narratives
    from app.analysis import (accusations, circulation, edits, factcheck_text, motif_signals, running_order, sagas,
                              scotus, stories, subjects)
    from app.utils import Config
    paths = [edits.JUDGMENTS, sagas.JUDGMENTS, scotus.JUDGMENTS, scotus.GLOSSES, scotus.STORY_GLOSSES, episode_kind.KINDS,
             accusations.CACHE, subjects.TAGS, factcheck_text.TEXTS, running_order.RUNNING, stories.RETURNS,
             narratives.JUDGMENTS, circulation.CACHE, chyrons.CLEAN, chyrons.MATCHES, motif_signals.RERANKS,
             motif_signals.JUDGED]
    # conftest sends some to scratch folders of their own; none is where it was, each keeps its name (but the motif
    # signals', renamed there, and the story seams', built in place by page_headlines)
    for name in set(importer.CACHES) - {'story_seams.json', 'motifs/rerank_cache.json', 'motifs/pair_judge_cache.json'}:
        path = next(p for p in paths if p.endswith(os.sep + name))
        assert path != os.path.join(Config.data, name)
    assert Config.cache.endswith(os.sep + 'cache')


def test_the_import_moves_caches_and_loads_labels(db, tmp_path):
    data, cache = tmp_path / 'data', tmp_path / 'data' / 'cache'
    (data / 'chyrons').mkdir(parents=True)
    (data / 'edit_judgments.json').write_text(json.dumps({'h': {'wording': 'same'}}))
    (data / 'chyrons' / 'clean.json').write_text(json.dumps({'CNN|X': {'kind': 'junk'}}))
    (data / 'factcheck_labels.json').write_text(json.dumps({'https://a.example/1': LABEL}))
    with db() as s:
        counts = importer.run(s, str(data), str(cache))
        s.commit()
    assert counts == {'factcheck_label': 1, 'caches moved': 2}
    assert json.loads((cache / 'chyrons' / 'clean.json').read_text()) == {'CNN|X': {'kind': 'junk'}}
    assert (cache / 'edit_judgments.json').exists() and not (data / 'edit_judgments.json').exists()
    assert (data / 'factcheck_labels.json').exists()  # never deleted: removed by hand later
    with db() as s:
        assert s.get(FactcheckLabel, 'https://a.example/1').to_dict() == LABEL


def test_the_import_with_nothing_there(db, tmp_path):
    with db() as s:
        assert importer.run(s, str(tmp_path), str(tmp_path / 'cache')) == {'factcheck_label': 0, 'caches moved': 0}
