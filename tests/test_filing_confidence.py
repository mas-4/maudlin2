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
            {'action': {'action': 'check', 'claim': 'D', 'id': 'M1', 'answer': 'yes'}, 'by': 'claude'},  # not the person's
            {'action': {'action': 'note', 'id': 'M1', 'note': 'x'}}]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\nnot json\n')
    got = fc.decisions(str(log))
    assert got == {(mi.key('A'), 'M1'): True, (mi.key('B'), 'M1'): True, (mi.key('B'), 'M2'): False,
                   (mi.key('C'), 'M3'): False}


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
