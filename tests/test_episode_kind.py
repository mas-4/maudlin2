"""app/episode_kind.py: the shows' new episodes labeled news or evergreen, in batches, each once; a claim told only
in evergreen episodes isn't retold this week (app/analysis/show_claims.py)."""
import numpy as np

from app import episode_kind as ek


def test_new_episodes_are_labeled_once(monkeypatch, tmp_path):
    from app import sidefeeds
    from app.analysis import llm
    monkeypatch.setattr(ek, 'KINDS', str(tmp_path / 'kinds.json'))
    key = next(s['key'] for s in sidefeeds.SOURCES if s['kind'] == 'podcast')
    eps = [{'title': t, 'url': f'https://e.example/{n}', 'summary': '', 'source': key}
           for n, t in enumerate(['The fall of Rome, part 3', 'Trump fires the Fed chair'])]
    monkeypatch.setattr(sidefeeds, 'items_of', lambda keys, days: eps)
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    calls = []
    monkeypatch.setattr(llm, 'complete_json', lambda p, schema, **k: calls.append(p) or {'kinds': ['evergreen', 'news']})
    assert ek.label_new() == 2 and ek.label_new() == 0 and len(calls) == 1
    assert ek.evergreen('https://e.example/0') and not ek.evergreen('https://e.example/1')


def test_a_claim_told_only_in_evergreen_episodes_isnt_retold_this_week(monkeypatch):
    from app import narratives
    from app.analysis import show_claims
    monkeypatch.setattr(narratives, 'groups', lambda items: [list(range(len(items)))])
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.ones((len(texts), 2)))
    c = {'claim': 'Rome fell to decadence', 'at': 0, 'speaker': 'host', 'quote': ''}
    store = {'https://e.example/a': {'show': 'A', 'date': '2026-10-08', 'claims': [c]},
             'https://e.example/b': {'show': 'B', 'date': '2026-10-08', 'claims': [c]}}
    monkeypatch.setattr(ek, 'load', lambda: {'https://e.example/a': 'evergreen', 'https://e.example/b': 'evergreen'})
    assert show_claims.retold(store) == []
    monkeypatch.setattr(ek, 'load', lambda: {'https://e.example/a': 'evergreen'})
    assert show_claims.retold(store) == []  # one news show only
    monkeypatch.setattr(ek, 'load', dict)
    assert show_claims.retold(store)[0]['shows'] == ['A', 'B']
