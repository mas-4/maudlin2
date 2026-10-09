import json
import time

from app import worker


def test_a_fresh_heartbeat_means_a_worker(tmp_path, monkeypatch):
    path = tmp_path / 'worker.json'
    monkeypatch.setattr(worker, 'HEARTBEAT', str(path))
    assert not worker.alive() and not worker.busy()  # none yet
    worker.beat({}, busy=True)
    assert worker.alive() and worker.busy()
    path.write_text(json.dumps({'at': time.time() - worker.FRESH - 1, 'busy': True}))
    assert not worker.alive() and not worker.busy()  # gone quiet: the hourly run processes again
    worker.beat({}, busy=False, at=0)
    assert not worker.alive()  # the way a worker leaves for new code


def test_a_cycle_processes_and_stops_for_the_hourly_run(tmp_path, monkeypatch):
    from app import processing
    monkeypatch.setattr(worker, 'HEARTBEAT', str(tmp_path / 'worker.json'))
    monkeypatch.setattr(worker, 'Awake', lambda: __import__('contextlib').nullcontext())
    calls = []
    monkeypatch.setattr(processing, 'process', lambda limit, stop: calls.append((limit, stop)))
    state = {}
    worker.cycle(state)
    assert calls == [(worker.CYCLE, worker.run_going)]
    assert state['cycles'] == 1 and not state['busy']


def test_the_steps_stop_once_the_hourly_run_begins(monkeypatch):
    from app import processing, transcribe
    ran = []
    monkeypatch.setattr(transcribe, 'transcribe_pending', lambda budget: ran.append('transcription'))
    import app.narratives
    monkeypatch.setattr(app.narratives, 'made_today', lambda: True)
    import app.analysis.focus_group
    monkeypatch.setattr(app.analysis.focus_group, 'extract', lambda budget: ran.append('focus group'))
    processing.process(limit=3600, stop=lambda: True)  # the run has begun: nothing begins
    assert ran == []
