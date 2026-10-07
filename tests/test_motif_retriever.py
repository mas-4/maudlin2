"""app/analysis/motif_retriever.py: trained on the person's confirmed filings, it shortlists the motifs a claim fits
first, adds their broader motifs and kinds, leaves out motifs like nothing in the claim, and filing falls back to the
closest motifs without weights."""
import hashlib

import numpy as np

from app.analysis import motif_index as mi
from app.analysis import motif_retriever as mr

TOPICS = {'bribe': 0, 'vote': 1, 'storm': 2, 'flood': 3, 'spy': 4, 'cabal': 5}


def fake_embed(texts):
    """Each text a unit vector along its topic words (and a little noise), 1024 long like mxbai's"""
    out = []
    for t in texts:
        v = np.zeros(1024)
        for w, i in TOPICS.items():
            if w in t.lower():
                v[i] += 1
        rng = np.random.default_rng(int(hashlib.md5(t.encode()).hexdigest()[:8], 16))
        v += rng.normal(0, 0.005, 1024)
        out.append(v / np.linalg.norm(v))
    return np.array(out)


def index_with(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(mr, 'WEIGHTS', str(tmp_path / 'w.json'))
    monkeypatch.setattr(mr, 'MIN_FILINGS', 4)
    import app.narratives
    monkeypatch.setattr(app.narratives, 'embed', fake_embed)
    c = lambda t: {'claim': t, 'source': 'narrative', 'checked': 'yes'}  # noqa: E731
    entries = {
        'M001': {'id': 'M001', 'name': 'Bought politician', 'note': 'a bribe buys a vote', 'claims': [c('A bribe for a vote'), c('Senator took a bribe')]},
        'M002': {'id': 'M002', 'name': 'Rigged vote', 'note': 'the vote was stolen', 'claims': [c('The vote count was rigged'), c('Dead people vote')], 'parents': ['M001']},
        'M003': {'id': 'M003', 'name': 'Weather weapon', 'note': 'a storm made on purpose', 'claims': [c('The storm was steered'), c('Flood made by a weapon')]},
        'M004': {'id': 'M004', 'name': 'Spy cabal', 'note': 'a cabal of spies', 'claims': [c('A spy cabal runs it'), c('The cabal hides spies')]},
    }
    mi.save({'next': 5, 'claims': {mi.key(x['claim']): [e['id']] for e in entries.values() for x in e['claims']},
             'entries': entries})


def test_train_and_shortlist(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    w = mr.train()
    assert w and w['trained_on'] == 8 and set(w['weights']) == set(mr.FACTS)
    monkeypatch.setattr(mr, 'SHOWN', 1)
    got = [e['id'] for e in mr.shortlist(mi.load(), 'Another bribe for a vote', mr.Vectors(), w)]
    assert got[0] == 'M001' and 'M002' in got  # the best fit, then its kind from the tree
    assert 'M004' not in got  # like nothing in the claim


def test_filing_falls_back_to_the_closest_without_weights(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    monkeypatch.setattr(mr, 'MIN_FILINGS', 10 ** 6)
    assert mr.weights() is None
    seen = []
    monkeypatch.setattr(mi, 'closest', lambda index, claim: seen.append(claim) or [])
    monkeypatch.setattr(mi, 'name_claim', lambda claim, shown: None)
    from app.analysis import llm
    monkeypatch.setattr(llm, 'backend', lambda: 'test')
    mi.file_claims([{'claim': 'A brand new storm claim', 'source': 'narrative'}])
    assert seen == ['A brand new storm claim']
