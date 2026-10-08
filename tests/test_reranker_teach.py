"""app/analysis/reranker_teach.py: which reranker scores come from (cached apart), and when teaching is due."""
import json
from datetime import datetime as dt, timedelta as td

from app.analysis import reranker_teach as rt


def test_the_tag_names_the_taught_reranker_and_teaching_waits_a_week_and_new_decisions(monkeypatch, tmp_path):
    monkeypatch.setattr(rt, 'TAUGHT', str(tmp_path / 'taught.pt'))
    monkeypatch.setattr(rt, 'META', str(tmp_path / 'taught.json'))
    assert rt.tag() == 'base' and rt.due()  # never taught
    (tmp_path / 'taught.pt').write_bytes(b'x')
    week_ago = (dt.now() - td(days=8)).isoformat(timespec='seconds')
    (tmp_path / 'taught.json').write_text(json.dumps({'at': week_ago, 'decisions': 700}))
    assert rt.tag() == week_ago
    monkeypatch.setattr(rt.fc, 'decisions', lambda *a, **k: dict.fromkeys(range(720)))
    assert not rt.due()  # a week, but only 20 new decisions
    monkeypatch.setattr(rt.fc, 'decisions', lambda *a, **k: dict.fromkeys(range(760)))
    assert rt.due()
    (tmp_path / 'taught.json').write_text(json.dumps({'at': dt.now().isoformat(timespec='seconds'), 'decisions': 0}))
    assert not rt.due()  # taught today


def test_nothing_taught_leaves_the_base_model_as_it_is(monkeypatch, tmp_path):
    monkeypatch.setattr(rt, 'TAUGHT', str(tmp_path / 'none.pt'))
    model = object()
    assert rt.load_into(model) is model
