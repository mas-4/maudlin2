"""app/analysis/filing_confidence.py: the person's decisions on the model's filings, read from the curation log, are
what the confidence model learns from; a filing in a motif made for its claim alone, or from a source too few
decisions have tested, is never passed as sure."""
import json

import numpy as np

from app.analysis import filing_confidence as fc
from app.analysis import motif_index as mi


def test_decisions_are_the_persons_last_word_on_each_filing(tmp_path):
    log = tmp_path / 'curation_log.jsonl'
    rows = [{'action': {'action': 'check', 'claim': 'A', 'id': 'M1', 'answer': 'no'}},
            {'action': {'action': 'check', 'claim': 'A', 'id': 'M1', 'answer': 'yes'}},  # changed their mind
            {'action': {'action': 'batch', 'steps': [{'action': 'check', 'claim': 'B', 'id': 'M1', 'answer': 'yes'},
                                                     {'action': 'unfile', 'claim': 'B', 'id': 'M2'}]}},
            {'action': {'action': 'move', 'claim': 'C', 'source': 'M3', 'target': 'M1'}},
            {'action': {'action': 'check', 'claim': 'D', 'id': 'M1', 'answer': 'yes'}, 'by': 'claude'},  # the person's word, carried out by Claude
            {'action': {'action': 'note', 'id': 'M1', 'note': 'x'}}]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\nnot json\n')
    got = fc.decisions(str(log))
    assert got == {(mi.key('A'), 'M1'): True, (mi.key('B'), 'M1'): True, (mi.key('B'), 'M2'): False,
                   (mi.key('C'), 'M3'): False, (mi.key('D'), 'M1'): True}


def test_a_motif_made_for_the_claim_alone_or_an_untested_source_is_never_sure():
    index = {'entries': {'M1': {'id': 'M1', 'claims': [{'claim': 'A'}, {'claim': 'B'}]},
                         'M2': {'id': 'M2', 'claims': [{'claim': 'A'}]}}}
    tested = {'narrative', 'checker'}
    assert fc.can_be_sure(index, 'A', 'M1', 'narrative', tested)
    assert fc.can_be_sure(index, 'A', 'M1', 'Snopes', tested)  # a fact-checker counts as 'checker'
    assert not fc.can_be_sure(index, 'A', 'M2', 'narrative', tested)  # born of this claim
    assert not fc.can_be_sure(index, 'A', 'M1', 'shows', tested)  # too few of the person's decisions on the shows yet


def test_the_held_out_test_finds_a_sure_threshold_only_where_precision_holds():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 2))
    y = X[:, 0] + 0.3 * rng.normal(size=400) > -0.8  # mostly kept, and the first feature tells
    test = fc.evaluate(X, y, [str(i % 97) for i in range(400)])
    assert test['auc'] > 0.9 and test['sure_at'] is not None
    at = next(t for t in test['thresholds'] if t['at'] == test['sure_at'])
    assert at['precision'] >= fc.SURE and at['passes'] >= 20


def test_weak_filings_are_found_and_their_alternatives_skip_where_the_claim_already_is(monkeypatch, tmp_path):
    m = {'at': 'T1'}
    c = lambda t, **k: {'claim': t, 'source': 'narrative', 'fit_model': 'T1', **k}  # noqa: E731
    index = {'entries': {
        'M1': {'id': 'M1', 'name': 'One', 'done': ['x'], 'claims': [c('weak and new', fit=0.2), c('strong', fit=0.9),
                                                                c('weak but seen again', fit=0.1, checked='yes', rechecked=True),
                                                                c('weak and confirmed', fit=0.3, checked='yes'),
                                                                c('old model', fit=0.1, fit_model='T0')]},
        'M2': {'id': 'M2', 'name': 'Two', 'claims': [c('in a model motif', fit=0.1)]},  # not the person's
        'M3': {'id': 'M3', 'name': 'Three', 'done': ['x'], 'claims': [{'claim': 'weak and confirmed'}]}}}
    monkeypatch.setattr(fc, 'decisions', lambda *a, **k: {})
    assert set(fc.weak_claims(index, m)) == {mi.key('weak and new'), mi.key('weak and confirmed')}
    monkeypatch.setattr(fc, 'ALTERNATIVES', str(tmp_path / 'alt.json'))
    (tmp_path / 'alt.json').write_text(json.dumps({mi.key('weak and confirmed'): {'model': 'T1', 'motifs': [['M3', 0.8], ['M2', 0.5]]}}))
    # filed in M3 since: only M2 is still a suggestion
    assert fc.better(index, 'weak and confirmed') == [{'id': 'M2', 'name': 'Two', 'fit': 0.5}]
    assert fc.better(index, 'strong') == []
    index['entries']['M2']['not_claims'] = [mi.key('weak and confirmed')]  # ✕: not this one
    assert fc.better(index, 'weak and confirmed') == []


def test_retraining_waits_until_the_new_decisions_are_asked(monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    old = {'weights': dict.fromkeys(fc.FEATURES, 0.0), 'bias': 0.0, 'reranker': 'base', 'judge': fc.ms.judge_tag(),
           'at': (datetime.now() - timedelta(days=2)).isoformat(timespec='seconds')}
    monkeypatch.setattr(fc, 'read_json', lambda path, default=None: old)
    monkeypatch.setattr('app.analysis.reranker_teach.tag', lambda: 'base')
    monkeypatch.setattr(fc.mi, 'load', dict)
    trained = []
    monkeypatch.setattr(fc, 'train', lambda: trained.append(1) or {'at': 'new'})
    monkeypatch.setattr(fc, 'warm', lambda index, budget: False)
    assert fc.model(retrain=True, budget=60) is old and not trained  # a run's worth asked, the old model meanwhile
    monkeypatch.setattr(fc, 'warm', lambda index, budget: True)
    assert fc.model(retrain=True, budget=60) == {'at': 'new'}
    assert fc.model(retrain=True) == {'at': 'new'}  # no budget: trains at once, as before


def test_another_judge_means_learning_again(monkeypatch):
    from datetime import datetime
    fresh = {'weights': dict.fromkeys(fc.FEATURES, 0.0), 'bias': 0.0, 'reranker': 'base', 'judge': 'gemma4:26b',
             'at': datetime.now().isoformat(timespec='seconds')}
    monkeypatch.setattr(fc, 'read_json', lambda path, default=None: fresh)
    monkeypatch.setattr('app.analysis.reranker_teach.tag', lambda: 'base')
    monkeypatch.setattr(fc.ms, 'JUDGE_DECIDER', 'nimble:9b')
    monkeypatch.setattr(fc, 'train', lambda: {'at': 'new'})
    assert fc.model() is fresh  # the checker never retrains
    assert fc.model(retrain=True) == {'at': 'new'}  # a day old or not: trained on Gemma's answers, now Nimble's
