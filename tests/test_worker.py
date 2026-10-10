import json
import sys
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
    assert len(calls) == 1 and calls[0][0] == worker.CYCLE
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


def test_a_lease_makes_the_worker_wait(tmp_path, monkeypatch):
    from app import gpu_lease
    monkeypatch.setattr(gpu_lease, 'LEASE', str(tmp_path / 'lease.json'))
    monkeypatch.setattr(worker, 'run_going', lambda: False)
    assert worker.yielding() is None and gpu_lease.held() is None
    with gpu_lease.Hold('an experiment', 5):
        assert 'an experiment' in worker.yielding()
        try:
            with gpu_lease.Hold('another', 5):
                pass
        except RuntimeError:
            pass  # a second holder is refused
    assert worker.yielding() is None  # given back


def test_a_lease_runs_out(tmp_path, monkeypatch):
    import json
    import os
    from app import gpu_lease
    monkeypatch.setattr(gpu_lease, 'LEASE', str(tmp_path / 'lease.json'))
    now = time.time()
    (tmp_path / 'lease.json').write_text(json.dumps({'holder': 'x', 'pid': os.getpid(), 'until': now - 1, 'renewed': now}))
    assert gpu_lease.held() is None  # past its time
    (tmp_path / 'lease.json').write_text(json.dumps({'holder': 'x', 'pid': os.getpid(), 'until': now + 600,
                                                     'renewed': now - gpu_lease.STALE - 1}))
    assert gpu_lease.held() is None  # its holder stopped renewing
    (tmp_path / 'lease.json').write_text(json.dumps({'holder': 'x', 'pid': 2 ** 22 + 12345, 'until': now + 600, 'renewed': now}))
    assert gpu_lease.held() is None  # its holder is gone


def test_run_holds_the_lease_for_the_command(tmp_path, monkeypatch):
    from app import gpu_lease
    monkeypatch.setattr(gpu_lease, 'LEASE', str(tmp_path / 'lease.json'))
    monkeypatch.setattr(gpu_lease, '_hourly_run_going', lambda: False)
    monkeypatch.setattr(gpu_lease, '_worker_busy', lambda: False)
    out = tmp_path / 'seen'
    code = f"import json; open({str(out)!r}, 'w').write(json.load(open({str(tmp_path / 'lease.json')!r}))['holder'])"
    assert gpu_lease.run([sys.executable, '-c', code], minutes=1, holder='test') == 0
    assert out.read_text() == 'test' and gpu_lease.held() is None


def test_run_waits_for_the_worker_to_finish_its_step(tmp_path, monkeypatch):
    from app import gpu_lease
    monkeypatch.setattr(gpu_lease, 'LEASE', str(tmp_path / 'lease.json'))
    monkeypatch.setattr(gpu_lease, '_hourly_run_going', lambda: False)
    busy = [True, True, False]
    monkeypatch.setattr(gpu_lease, '_worker_busy', lambda: busy.pop(0) if len(busy) > 1 else busy[0])
    monkeypatch.setattr(gpu_lease.time, 'sleep', lambda s: None)
    assert gpu_lease.run([sys.executable, '-c', 'pass'], minutes=1, holder='test') == 0
    assert busy == [False]  # asked until the worker was done


def test_run_waits_again_when_another_takes_the_lease_first(tmp_path, monkeypatch):
    from app import gpu_lease
    monkeypatch.setattr(gpu_lease, 'LEASE', str(tmp_path / 'lease.json'))
    monkeypatch.setattr(gpu_lease, '_hourly_run_going', lambda: False)
    monkeypatch.setattr(gpu_lease, '_worker_busy', lambda: False)
    monkeypatch.setattr(gpu_lease.time, 'sleep', lambda s: None)
    tries = []
    real = gpu_lease.Hold.take

    def take(self):
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError('taken')
        return real(self)
    monkeypatch.setattr(gpu_lease.Hold, 'take', take)
    assert gpu_lease.run([sys.executable, '-c', 'pass'], minutes=1, holder='test') == 0
    assert len(tries) == 2 and gpu_lease.held() is None


def test_a_short_cycle_never_takes_the_awake_lock(monkeypatch, tmp_path):
    """Only a cycle past `after` seconds keeps the machine awake: empty cycles mustn't restart the idle countdown"""
    started = []
    monkeypatch.setattr(worker.os.path, 'exists', lambda p: True)
    monkeypatch.setattr(worker.subprocess, 'run', lambda *a, **k: type('R', (), {'returncode': 0})())

    class Proc:
        pid = 1

        def wait(self, timeout=None):
            pass
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: started.append(a) or Proc())
    monkeypatch.setattr(worker.os, 'killpg', lambda pid, sig: None)
    with worker.Awake(after=5):
        pass
    assert started == []  # done before its minute: no lock
    with worker.Awake(after=0.01):
        time.sleep(0.2)
    assert len(started) == 1  # still working past it: the lock
