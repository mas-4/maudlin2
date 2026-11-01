"""The runstate group in data.db (Nov 1): run_state's get, put and atomic update, the GPU lease taken in a transaction,
factcheck_seen, the daily motif metrics and the model scout's seen models as rows, and the one-time import."""
import json
import os
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app import runstate
from app.tables.runstate import FactcheckSeen, ModelSeen, MotifMetricsDay, RunState


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


@pytest.fixture
def file_db(tmp_path, monkeypatch):
    """A database in a file with a connection per session, as several processes share data.db"""
    engine = create_engine(f'sqlite:///{tmp_path / "data.db"}', connect_args={'timeout': 30})
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


def test_get_put_delete_and_when(db):
    assert runstate.get('x') is None and runstate.get('x', {}) == {} and runstate.when('x') is None
    default = {'done': []}
    runstate.get('x', default)['done'].append(1)
    assert default == {'done': []}  # a fresh copy of the default each time
    runstate.put('x', {'a': [1, 2]})
    runstate.put('x', {'a': [3]})
    assert runstate.get('x') == {'a': [3]} and runstate.when('x') is not None
    runstate.delete('x')
    assert runstate.get('x') is None


def test_update_changes_in_one_go_and_leaves_it_on_an_error(db):
    assert runstate.update('n', lambda v: {**v, 'k': 1}, {}) == {'k': 1}
    with pytest.raises(ValueError):
        runstate.update('n', lambda v: (_ for _ in ()).throw(ValueError('no')))
    assert runstate.get('n') == {'k': 1}
    with pytest.raises(ValueError):
        runstate.update('fresh', lambda v: (_ for _ in ()).throw(ValueError('no')))
    with db() as s:
        assert s.get(RunState, 'fresh') is None  # its placeholder row went with the rollback
    runstate.update('n', lambda v: runstate.GONE)
    assert runstate.get('n') is None


def test_updates_from_many_threads_lose_nothing(file_db):
    def bump():
        for _ in range(10):
            runstate.update('count', lambda v: v + 1, 0)
    threads = [threading.Thread(target=bump) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert runstate.get('count') == 40


def test_the_gpu_lease_is_taken_once_and_given_back(file_db):
    from app import gpu_lease
    assert gpu_lease.held() is None
    with gpu_lease.Hold('first', 5):
        assert gpu_lease.held()['holder'] == 'first'
        runstate.put('gpu_lease', {**runstate.get('gpu_lease'), 'pid': os.getppid()})  # another process's
        with pytest.raises(RuntimeError, match='held by first'):
            gpu_lease.Hold('second', 5).take()
        gpu_lease.release(os.getpid())  # not ours now: kept
        assert gpu_lease.held()['pid'] == os.getppid()
        runstate.put('gpu_lease', {**runstate.get('gpu_lease'), 'pid': os.getpid()})
    assert gpu_lease.held() is None


def test_factcheck_seen_rows_replace_the_last_look(db):
    from app.analysis import circulation
    assert circulation.load() == {}
    counts = {'telling': 1, 'arguing': 2, 'people': 3, 'candidates': 4, 'checked': 5, 'at': '2026-11-01T04:55'}
    circulation.save({'hours': 72, 'posts': 10, 'at': '2026-11-01T04:55'}, {'u1': counts, 'u2': counts})
    circulation.save({'hours': 72, 'posts': 12, 'at': '2026-11-02T04:55'}, {'u2': {**counts, 'people': 9}})
    look = circulation.load()
    assert look['posts'] == 12 and list(look['claims']) == ['u2'] and look['claims']['u2']['people'] == 9


def test_metrics_snapshot_keeps_the_latest_of_the_day(db, monkeypatch):
    from app.analysis import motif_filing
    shapes = iter([{'motifs': 1}, {'motifs': 2}])
    monkeypatch.setattr(motif_filing, 'metrics', lambda index=None: next(shapes))
    motif_filing.snapshot_metrics()
    motif_filing.snapshot_metrics()
    snaps = motif_filing.metrics_snapshots()
    assert len(snaps) == 1 and list(snaps.values())[0] == {'motifs': 2}


def test_model_scout_remembers_only_the_new(db):
    from tests.load import script
    scout = script('model_scout')
    assert scout.seen_before() == {}
    scout.remember({'ollama:a': '2026-10-16'})
    scout.remember({'hf:b': '2026-10-23'})
    assert scout.seen_before() == {'ollama:a': '2026-10-16', 'hf:b': '2026-10-23'}


def test_aggregates_refresh_by_when_they_were_kept(db, monkeypatch):
    from app import polling
    asked = []
    monkeypatch.setattr(polling.rq, 'get', lambda *a, **k: asked.append(1) or (_ for _ in ()).throw(OSError('off')))
    runstate.put(polling.AGGREGATES_FILE, {'approval': {'page': 'p', 'rows': []}})
    polling.fetch_aggregates()
    assert asked == []  # kept just now: not asked again
    assert polling.Polling.published_averages() == {'approval': {'page': 'p', 'rows': [], 'mean': None}}


def test_import_reads_each_file_and_moves_the_caches(db, tmp_path):
    from scripts.json_import import runstate as importer
    data, cache = tmp_path / 'data', tmp_path / 'cache'
    (data / 'chyrons').mkdir(parents=True)
    (data / 'motifs').mkdir()
    (data / 'worker.json').write_text(json.dumps({'pid': 1, 'at': 5.0}))
    (data / 'chyrons' / 'state.json').write_text(json.dumps({'done': ['2026-10-02']}))
    (data / 'aggregates.json').write_text('{broken')
    (data / 'factcheck_seen.json').write_text(json.dumps({'hours': 72, 'posts': 9, 'at': '2026-11-01T04:55', 'claims': {
        'u1': {'telling': 1, 'arguing': 0, 'people': 1, 'candidates': 2, 'checked': 2, 'at': '2026-11-01T04:55'}}}))
    (data / 'motifs' / 'metrics.json').write_text(json.dumps({'2026-10-06': {'motifs': 304}}))
    (data / 'model_scout.json').write_text(json.dumps({'seen': {'ollama:beam': '2026-10-16'}}))
    (data / 'replay.json').write_text('{"key": "k"}')
    (data / 'retranscribe_failed.json').write_text(json.dumps({'12': 'over the size limit'}))
    (data / 'archive').mkdir()
    (data / 'archive' / 'days.json').write_text(json.dumps({'2026-10-04': {
        'label': 'Slow news day…', 'emoji': '🌴', 'story': 'Coast Guard searches', 'stories': 42}}))
    with db() as s:
        counts = importer.run(s, str(data), str(cache))
        s.commit()
    assert counts == {'run_state': 4, 'factcheck_seen': 1, 'motif_metrics_day': 1, 'model_seen': 1, 'archive_day': 1,
                      'caches moved': 1}
    assert runstate.get('retranscribe_failed') == {'12': 'over the size limit'}
    from app.site import archive
    assert archive._days()['2026-10-04']['stories'] == 42
    assert runstate.get('worker') == {'pid': 1, 'at': 5.0} and runstate.get('chyrons/state') == {'done': ['2026-10-02']}
    assert runstate.get('aggregates') is None  # unreadable: left out
    from app.analysis import circulation
    assert circulation.load()['claims']['u1']['candidates'] == 2 and circulation.load()['posts'] == 9
    with db() as s:
        assert s.get(MotifMetricsDay, '2026-10-06') and s.get(ModelSeen, 'ollama:beam').first_seen == '2026-10-16'
        assert s.query(FactcheckSeen).count() == 1
    assert (cache / 'replay.json').read_text() == '{"key": "k"}' and not (data / 'replay.json').exists()
    assert (data / 'worker.json').exists()  # sources stay


def test_import_of_an_empty_folder(db, tmp_path):
    from scripts.json_import import runstate as importer
    with db() as s:
        assert set(importer.run(s, str(tmp_path), str(tmp_path / 'cache')).values()) == {0}
