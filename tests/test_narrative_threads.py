import json

import numpy as np

from app.analysis import llm, narrative_threads as nt


def report(tmp_path, stamp, hours, claims):
    found = [{'authors': 9, 'posts': 10, 'label': {'retold': True, 'narrative': c, 'genre': 'rumor'}} for c in claims]
    found.append({'authors': 9, 'posts': 9, 'label': {'retold': False, 'narrative': 'not retold'}})
    (tmp_path / f'report-{stamp}.json').write_text(json.dumps({'hours': hours, 'found': found}))


def test_a_narrative_told_again_on_a_later_day_joins_its_thread(monkeypatch, tmp_path):
    from app import narratives
    monkeypatch.setattr(narratives, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    report(tmp_path, '2026-10-03-1400', 3, ['a trial report'])  # under six hours: not a day
    report(tmp_path, '2026-10-04-0400', 24, ['Plane crashed off Nantucket', 'Barkley is hurt'])
    report(tmp_path, '2026-10-05-0400', 24, ['Jet missing near Nantucket', 'Chase is hurt', 'Something new'])
    vec = {'Plane crashed off Nantucket': [1, 0, 0], 'Jet missing near Nantucket': [0.95, 0.31, 0],
           'Barkley is hurt': [0, 1, 0], 'Chase is hurt': [0, 0.9, 0.44], 'Something new': [0, 0, 1]}
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array([vec[t] for t in texts], float))
    asked = []

    def complete(prompt, schema, max_tokens, model):
        asked.append(prompt)
        same = 'Nantucket' in prompt.split('Later:')[1].split('\n')[0]
        return {'reason': 'r', 'verdict': 'the same narrative' if same else 'different narratives'}
    monkeypatch.setattr(llm, 'complete_json', complete)
    store = nt.link_days()
    assert store['linked'] == ['report-2026-10-04-0400.json', 'report-2026-10-05-0400.json']
    days = {t['id']: [d['claim'] for d in t['days']] for t in store['threads'].values()}
    assert days == {'N0001': ['Plane crashed off Nantucket', 'Jet missing near Nantucket'], 'N0002': ['Barkley is hurt'],
                    'N0003': ['Chase is hurt'], 'N0004': ['Something new']}
    assert len(asked) == 2  # 'Something new' is near nothing: never asked
    assert nt.thread_of(store, 'report-2026-10-05-0400.json', 'Jet missing near Nantucket')['id'] == 'N0001'
    assert nt.link_days()['linked'] == store['linked'] and len(asked) == 2  # each day once
