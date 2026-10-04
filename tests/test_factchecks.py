import numpy as np

from app.analysis import clustering, factchecks, llm


def test_fact_checks_tie_only_above_the_floor_by_forced_choice(monkeypatch, tmp_path):
    monkeypatch.setattr(factchecks, 'STORY_CACHE', str(tmp_path / 'fc.json'))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    sim = np.array([[1, 0, .7, .2], [0, 1, .55, .5], [.7, .55, 1, 0], [.2, .5, 0, 1]])
    monkeypatch.setattr(clustering, 'story_similarity', lambda texts: (sim, 0.8, 'mxbai-embed-large'))
    prompts = []
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, schema, max_tokens=0: prompts.append(prompt) or
                        {'reason': '', 'pick': '1'})
    items = [{'title': 'FAKE video of FlyDubai pilot', 'summary': '', 'source': 'Lead Stories'},
             {'title': 'Taxpayer-funded ads', 'summary': '', 'source': 'FactCheck.org'}]
    found = factchecks.for_stories({1: 'FlyDubai co-pilot attack', 2: 'Paxton ads air'}, items)
    assert found == {1: [items[0]]}
    assert len(prompts) == 1 and 'is a fact-checker' in prompts[0]  # the second was under the floor: never asked
