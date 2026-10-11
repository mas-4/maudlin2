"""app/desk.py: the desktop panel shows every part, and a part that fails doesn't take the rest down"""
from app import desk


def test_a_failing_part_leaves_the_rest(monkeypatch, tmp_path):
    monkeypatch.setattr(desk, 'sh', lambda *a, **k: '')  # no nvidia-smi, systemctl or ollama answers
    monkeypatch.setattr(desk, 'QUEUE', str(tmp_path / 'queue.md'))
    (tmp_path / 'queue.md').write_text('## Running now (...)\n- [BND3] A1 folktales\n\n## Next\n- not this\n')

    def lease_line():
        raise RuntimeError('lease file garbled')
    monkeypatch.setattr(desk, 'lease_line', lease_line)
    text = desk.panel()
    assert '🎛 GPU: unreadable' in text and 'lease_line: lease file garbled' in text
    assert '   · A1 folktales' in text and 'not this' not in text
    assert desk.KEY in text and '🖥 up' in text
