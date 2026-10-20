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


def test_the_1896_spot_check_takes_right_wrong_or_unsure(tmp_path, monkeypatch):
    """Oct 20: Rip Van Winkle's 50 sure filings, read by the person on the experiments page"""
    import pytest
    monkeypatch.setattr(lab, 'EXP', str(tmp_path))
    (tmp_path / 'a2_newspapers.json').write_text(json.dumps({'spot_check': [{'claim': 'a'}, {'claim': 'b'}]}))
    lab.verdict('A2', '0', 'right')
    lab.verdict('A2', '1', 'wrong')
    lab.verdict('A2', '1', None)
    assert json.loads((tmp_path / 'a2_newspapers.json').read_text())['spot_verdicts'] == {'0': 'right'}
    with pytest.raises(ValueError):
        lab.verdict('A2', '7', 'right')
