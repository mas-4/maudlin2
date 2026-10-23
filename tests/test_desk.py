"""app/desk.py: the desktop panel shows every part, and a part that fails doesn't take the rest down"""
from app import desk


def test_a_failing_part_leaves_the_rest(monkeypatch, tmp_path):
    monkeypatch.setattr(desk, 'sh', lambda *a, **k: '')  # no nvidia-smi, systemctl or ollama answers

    def lease_line():
        raise RuntimeError('lease file garbled')
    monkeypatch.setattr(desk, 'lease_line', lease_line)
    text = desk.panel()
    assert '🎛 GPU: unreadable' in text and 'lease_line: lease file garbled' in text
    assert '🧪 experiments: none' in text
    assert desk.KEY in text and '🖥 up' in text


def test_experiments_are_listed_by_their_figures_running_first(monkeypatch):
    """Oct 11: the card took the queue's notes, calling a chain's next step and waiting jobs running; and leases show
    as the experiments' folklore figures, never codes"""
    from app import gpu_lease
    ps = ('  6279 /usr/bin/zsh -c ... .venv/bin/python -m app.gpu_lease run --holder s1-judge -- x\n'
          '  6279 .venv/bin/python -m app.gpu_lease run --minutes 20 --holder s1-judge -- python s1.py judge\n'
          '   964 .venv/bin/python -m app.gpu_lease run --minutes 30 --holder s2-resort -- python s2.py\n')
    monkeypatch.setattr(desk, 'sh', lambda *a, **k: ps)
    monkeypatch.setattr(gpu_lease, 'held', lambda: {'holder': 's2-resort'})
    assert desk.lease_jobs() == [{'name': 'Penelope · resort', 'state': 'running 16 min'},
                                 {'name': 'Janus · judge', 'state': 'waiting for the GPU, 104 min'}]
    assert desk.figure_of('atropos-judge') == 'Atropos · judge' and desk.figure_of('unknown') == 'unknown'


def test_tokens_today_and_what_gemma_would_cost_rented(monkeypatch, tmp_path):
    from datetime import datetime as dt
    from app.analysis import token_log
    monkeypatch.setattr(token_log, 'DIR', str(tmp_path))
    assert desk.tokens_today() == ('none logged yet', 'nothing yet')
    (tmp_path / f"{dt.now():%Y-%m-%d}.csv").write_text(
        'x,show_claims,gemma4:26b,3000000,200000,9.0\n' 'x,stories,qwen3:8b,500000,10000,1.0\n')
    # Gemma only, at the cheapest price: 3M x $0.07 + 0.2M x $0.34
    assert desk.tokens_today() == ('3.5M read · 210k written', '$0.28 so far today')


def test_ollama_says_when_it_needs_a_restart(monkeypatch):
    import requests
    from app import desk

    class R:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body
    models = {'models': [{'name': m} for m in desk.NEEDED]}
    from app import gpu_lease
    monkeypatch.setattr(desk, 'going', lambda: False)
    monkeypatch.setattr(gpu_lease, 'held', lambda: None)
    monkeypatch.setattr(desk, 'sh', lambda *a, **k: 'ollama 0.40.3-1')
    monkeypatch.setattr(requests, 'get', lambda url, timeout: R({'version': '0.40.2'} if 'version' in url else models))
    assert desk.ollama_words().startswith('⚠️ restart it now: 0.40.3 installed, 0.40.2 running')
    monkeypatch.setattr(gpu_lease, 'held', lambda: {'holder': 'echo-claims'})
    assert desk.ollama_words().startswith('⚠️ restart it now, though Echo · claims loses the calls it has in flight')
    monkeypatch.setattr(desk, 'sh', lambda *a, **k: 'ollama 0.40.2-1')
    assert desk.ollama_words() == '0.40.2 ✓'

    def down(url, timeout):
        raise requests.ConnectionError
    monkeypatch.setattr(requests, 'get', down)
    assert desk.ollama_words().startswith('⛔ not answering')


def test_a_heartbeat_left_before_a_sleep_is_not_the_worker_down(monkeypatch, tmp_path):
    """Oct 23: after a 47-minute suspend the widget said the worker was down; the heartbeat's awake clock stops in sleep"""
    import json
    import time
    from app import desk, worker
    from app.utils import Config
    monkeypatch.setattr(Config, 'data', str(tmp_path))
    beat = {'at': time.time() - 47 * 60, 'awake': time.monotonic() - 30, 'boot': worker.boot_id(), 'busy': True}
    (tmp_path / 'worker.json').write_text(json.dumps(beat))
    assert desk.worker_line() == '🛠 worker: back from sleep, carrying on'
    (tmp_path / 'worker.json').write_text(json.dumps({**beat, 'awake': time.monotonic() - 47 * 60}))
    assert 'down (last beat' in desk.worker_line()  # awake all that time: stuck or gone
