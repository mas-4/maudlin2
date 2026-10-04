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


def test_shared_side_needs_enough_rated_shares():
    from app.narratives import shared_side
    leans = {'Fox News': 2, 'Breitbart': 2, 'NPR': -1, 'Reuters': 0}
    assert shared_side([('Fox News', 3), ('NPR', 1)], leans) == 'right'
    assert shared_side([('NPR', 2), ('Reuters', 1)], leans) == 'left'
    assert shared_side([('Reuters', 4)], leans) == 'center'
    assert shared_side([('Fox News', 1)], leans) is None  # one share isn't enough
    assert shared_side([('Some blog', 9)], leans) is None  # unrated outlets don't count
