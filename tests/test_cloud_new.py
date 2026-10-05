"""app/site/wordcloudgen.py: words new to the cloud (✨), from the clouds of the day before."""
import json
from datetime import datetime, timedelta

from app.site import wordcloudgen as wc


def words(*texts):
    return [{'text': t, 'tip': t} for t in texts]


def test_new_only_once_the_history_covers_enough(monkeypatch, tmp_path):
    monkeypatch.setattr(wc, 'CLOUD_HISTORY', str(tmp_path / 'h.json'))
    now = datetime(2026, 10, 5, 12)
    assert not any(w['new'] for w in wc.mark_new(words('cornell', 'tariffs'), now - timedelta(hours=3)))  # too little history
    out = wc.mark_new(words('cornell', 'leavitt'), now)
    assert {w['text']: w['new'] for w in out} == {'cornell': False, 'leavitt': False}  # 3 hours of history: not yet
    hist = json.loads((tmp_path / 'h.json').read_text())
    hist[0]['at'] = (now - timedelta(hours=10)).isoformat()  # pretend the first cloud was ten hours ago
    (tmp_path / 'h.json').write_text(json.dumps(hist))
    out = wc.mark_new(words('cornell', 'alito'), now + timedelta(hours=1), save=False)
    assert {w['text']: w['new'] for w in out} == {'cornell': False, 'alito': True}
    assert out[1]['tip'].endswith('✨ new to the cloud')


def test_a_word_absent_for_a_day_is_new_again(monkeypatch, tmp_path):
    monkeypatch.setattr(wc, 'CLOUD_HISTORY', str(tmp_path / 'h.json'))
    now = datetime(2026, 10, 5, 12)
    (tmp_path / 'h.json').write_text(json.dumps([
        {'at': (now - timedelta(hours=30)).isoformat(), 'words': ['hastert']},
        {'at': (now - timedelta(hours=20)).isoformat(), 'words': ['cornell']}]))
    out = wc.mark_new(words('hastert', 'cornell'), now, save=False)
    assert {w['text']: w['new'] for w in out} == {'hastert': True, 'cornell': False}
