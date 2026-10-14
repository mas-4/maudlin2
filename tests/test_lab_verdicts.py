"""scripts/experiments/lab.py: the experiments page's verdicts. Ptah's blind pairs take A, B or neither, kept as the
naming order each letter stood for (the report counts orders, not letters)."""
import json
import sys

sys.path.insert(0, 'scripts/experiments')
import f23_ptah as f  # noqa: E402
import lab  # noqa: E402


def test_a_blind_pick_is_kept_as_the_order_it_was(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, 'EXP', str(tmp_path))
    a, b = f.PROPOSER
    (tmp_path / 'f23_ptah.json').write_text(json.dumps({'blind': [{'case': 'c1', 'first': b}, {'case': 'c2', 'first': a}]}))
    lab.verdict('F23', 'c1', 'A')  # A was the note-first arm here
    lab.verdict('F23', 'c2', 'B')
    lab.verdict('F23', 'c2', None)
    lab.verdict('F23', 'c2', 'neither')
    assert json.loads((tmp_path / 'f23_ptah.json').read_text())['verdicts'] == {'c1': b, 'c2': 'neither'}
