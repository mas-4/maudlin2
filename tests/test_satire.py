import numpy as np

from app.analysis import llm, satire
from app.analysis import clustering


def test_jokes_are_a_forced_choice_among_the_closest_stories(monkeypatch, tmp_path):
    monkeypatch.setattr(satire, 'CACHE', str(tmp_path / 'satire.json'))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    # Two jokes, three stories: each joke's closest stories come first in its row
    sim = np.array([[1, 0, .9, .1, .5], [0, 1, .2, .8, .3], [.9, .2, 1, 0, 0], [.1, .8, 0, 1, 0], [.5, .3, 0, 0, 1]])
    monkeypatch.setattr(clustering, 'story_similarity', lambda texts: (sim, 0.8, 'mxbai-embed-large'))
    asked = []

    def complete_json(prompt, schema, max_tokens=0):
        asked.append(prompt)
        return {'reason': '', 'story': '1' if 'Senator eats' in prompt else 'none'}

    monkeypatch.setattr(llm, 'complete_json', complete_json)
    items = [{'title': 'Senator eats filibuster', 'summary': '', 'source': 'The Onion', 'group': 'left'},
             {'title': 'Man unsure about life', 'summary': '', 'source': 'ClickHole', 'group': 'center'}]
    stories = {7: 'Senate filibuster fight', 8: 'Stock markets fall', 9: 'Storm hits coast'}
    found = satire.jokes(stories, items)
    assert list(found) == [7] and found[7][0]['source'] == 'The Onion'
    assert '1. Senate filibuster fight' in asked[0]
    satire.jokes(stories, items)
    assert len(asked) == 2  # cached: asked once


def test_no_model_no_jokes(monkeypatch):
    monkeypatch.setattr(llm, 'backend', lambda: None)
    assert satire.jokes({1: 'A story'}, [{'title': 'A joke', 'summary': '', 'source': 'x', 'group': 'left'}]) == {}


def test_jokes_need_a_close_story_and_the_right_embeddings(monkeypatch, tmp_path):
    monkeypatch.setattr(satire, 'CACHE', str(tmp_path / 'satire.json'))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: {'reason': '', 'story': '1'})
    item = [{'title': 'A joke', 'summary': '', 'source': 'x', 'group': 'left'}]
    far = np.array([[1, .3], [.3, 1]])
    monkeypatch.setattr(clustering, 'story_similarity', lambda texts: (far, 0.8, 'mxbai-embed-large'))
    assert satire.jokes({1: 'A story'}, item) == {}  # nothing close enough to offer
    near = np.array([[1, .7], [.7, 1]])
    monkeypatch.setattr(clustering, 'story_similarity', lambda texts: (near, 0.7, 'potion-base-8M'))
    assert satire.jokes({1: 'A story'}, item) == {}  # another model's scale: skipped
