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


def test_experiments_are_listed_by_their_lease_names_running_first(monkeypatch):
    """Oct 11: the card took the queue's notes, calling a chain's next step and waiting jobs running"""
    from app import gpu_lease
    ps = ('  6279 /usr/bin/zsh -c ... .venv/bin/python -m app.gpu_lease run --holder s1-judge -- x\n'
          '  6279 .venv/bin/python -m app.gpu_lease run --minutes 20 --holder s1-judge -- python s1.py judge\n'
          '   964 .venv/bin/python -m app.gpu_lease run --minutes 30 --holder s2-resort -- python s2.py\n')
    monkeypatch.setattr(desk, 'sh', lambda *a, **k: ps)
    monkeypatch.setattr(gpu_lease, 'held', lambda: {'holder': 's2-resort'})
    assert desk.lease_jobs() == [{'name': 's2-resort', 'state': 'running 16 min'},
                                 {'name': 's1-judge', 'state': 'waiting for the GPU, 104 min'}]
