import numpy as np
import pandas as pd

from app.analysis import llm, motifs


def test_pick_is_a_forced_choice_among_the_closest_entries(monkeypatch, tmp_path):
    df = pd.DataFrame({'code': ['K1836', 'D11', 'B81'], 'letter': ['K', 'D', 'B'],
                       'text': ['Disguise of man in woman\'s dress.', 'Transformation: woman to man.', 'Mermaid.'],
                       'section': ['', '', '']})
    monkeypatch.setattr(motifs, 'index', lambda: (df, np.eye(3)))
    monkeypatch.setattr(motifs, 'candidates', lambda claims, k=12: [[0, 1]] * len(claims))
    monkeypatch.setattr(motifs, 'PICKS', str(tmp_path / 'picks.json'))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    asked = []

    def complete_json(prompt, schema, max_tokens=0):
        asked.append((prompt, schema['properties']['entry']['enum']))
        return {'reason': '', 'entry': 'K1836' if 'disguised' in prompt else 'none'}

    monkeypatch.setattr(llm, 'complete_json', complete_json)
    out = motifs.pick(['A man disguised as a woman sneaks in', 'Stocks fell'])
    assert out[0]['code'] == 'K1836' and out[1] is None
    assert asked[0][1] == ['K1836', 'D11', 'none']  # only the candidates (and none) can be answered
    assert 'not whether it is true' in asked[0][0]
    motifs.pick(['A man disguised as a woman sneaks in'])
    assert len(asked) == 2  # cached
