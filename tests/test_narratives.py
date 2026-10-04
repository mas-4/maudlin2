"""Narrative research: telling retold variants from copypasta, and grouping paraphrases. No model, no network."""
import random

import numpy as np

from app import narratives as n


def test_variety_tells_told_from_pasted():
    rng = random.Random(1)
    pasted = ['The ballots were already filled in when they got there'] * 6
    told = ['They had the ballots filled in before anyone showed up', 'My cousin says the votes were pre-marked',
            'Heard the boxes came already stuffed', 'Pre-filled ballots again, same as last time',
            'Somebody marked those ballots before the polls opened']
    assert n.variety(pasted, rng) == 0.0
    assert n.variety(told, rng) > n.FOLK_VARIETY
    posts = [{'text': t, 'author': f'a{i}', 'reply': 0, 'source': 'bluesky'} for i, t in enumerate(pasted + told)]
    assert n.describe(posts, list(range(6)), rng)['kind'] == 'copypasta'
    assert n.describe(posts, list(range(6, 11)), rng)['kind'] == 'told'
    assert n.describe(posts, list(range(6, 11)), rng)['authors'] == 5


def test_groups_join_mutual_neighbours_only(monkeypatch):
    # Two tight pairs and a loner; the loner is near one pair but they aren't each other's neighbours
    v = np.array([[1, 0, 0], [0.99, 0.1, 0], [0, 1, 0], [0.05, 0.99, 0], [0.6, 0.6, 0.5]], dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    monkeypatch.setattr(n, 'embed', lambda texts: v)
    monkeypatch.setattr(n, 'NEIGHBOURS', 1)
    posts = [{'text': str(i)} for i in range(5)]
    assert sorted(sorted(g) for g in n.groups(posts)) == [[0, 1], [2, 3]]
