"""The correction proposer (app/analysis/motif_proposals.py): proposals are atomic, never made twice, dropped once the
change is made or overtaken, approved through the workbench's own actions, and a rejection sticks."""
import importlib.util

import numpy as np
import os

from app.analysis import llm
from app.analysis import motif_index as mi
from app.analysis import motif_proposals as mp
from app.utils.store import write_json

spec = importlib.util.spec_from_file_location('validate', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'validate.py'))
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


def index_with(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(mp, 'PROPOSALS', str(tmp_path / 'proposals.json'))
    claim = lambda t: {'claim': t, 'source': 'narrative'}  # noqa: E731
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001'], mi.key('b'): ['M002'], mi.key('c'): ['M003']},
             'groups': {'G01': {'id': 'G01', 'name': 'Archetypes'}}, 'entries': {
                 'M001': {'id': 'M001', 'name': "Poltiicians' empty promises", 'claims': [claim('a')], 'note': 'They promsie'},
                 'M002': {'id': 'M002', 'name': 'Empty suit', 'claims': [claim('b')]},
                 'M003': {'id': 'M003', 'name': 'Rigged votes', 'claims': [claim('c')]}}})


def test_typo_fixes_must_be_small():
    assert mp.small_fix("Poltiicians' empty promises", "Politicians' empty promises")
    assert not mp.small_fix('Empty suit', 'A politician with nothing behind the image')  # a rewrite, not a typo
    assert not mp.small_fix('Empty suit', 'Empty suit')


def test_typos_from_the_model_become_proposals(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: {'fixes': [
        {'n': 1, 'name': "Politicians' empty promises", 'note': 'They promise'},
        {'n': 2, 'name': 'A whole new name for it', 'note': ''}, {'n': 9, 'name': 'x', 'note': ''}]})
    store = {}
    assert mp.typos(store, mi.load()) == 2 and mp.typos(store, mi.load()) == 0  # never the same proposal twice
    kinds = sorted((p['kind'], p['args']['to']) for p in store.values())
    assert kinds == [('note', 'They promise'), ('rename', "Politicians' empty promises")]


def test_approve_and_reject_through_the_workbench(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    store = {}
    mp.add(store, 'rename', {'id': 'M001', 'from': "Poltiicians' empty promises", 'to': "Politicians' empty promises"}, 'typo')
    mp.add(store, 'parent', {'id': 'M002', 'parent': 'M001'}, 'an empty suit makes empty promises')
    mp.add(store, 'group', {'id': 'M002', 'group': 'G01'}, 'an archetype')
    mp.add(store, 'merge', {'a': 'M003', 'b': 'M001'}, 'nope')
    write_json(mp.PROPOSALS, store)
    queue = {p['kind']: p for p in validate.workbench_queue('proposals')}
    assert set(queue) == {'rename', 'parent', 'group', 'merge'}
    for kind in ('rename', 'parent', 'group'):
        p = queue[kind]
        validate.workbench_action({**p['do'], 'proposal': p['id']})
    validate.workbench_action({'action': 'proposal_reject', 'proposal': queue['merge']['id']})
    e = mi.load()['entries']
    assert e['M001']['name'] == "Politicians' empty promises" and 'M001' in mi.parents_of(e['M002'])
    assert 'G01' in mi.groups_of(e['M002']) and not e['M003'].get('merged_into')
    assert validate.workbench_queue('proposals') == []  # done or rejected: nothing left
    assert {p['status'] for p in mp.load().values()} == {'approved', 'rejected'}
    mp.add(store := mp.load(), 'merge', {'a': 'M003', 'b': 'M001'}, 'again')
    assert store[mp.pid('merge', {'a': 'M003', 'b': 'M001'})]['status'] == 'rejected'  # a rejection sticks


def test_a_proposal_overtaken_by_hand_drops_out(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    store = {}
    mp.add(store, 'relate', {'a': 'M002', 'b': 'M003'}, 'told together')
    mp.add(store, 'note', {'id': 'M001', 'from': 'They promsie', 'to': 'They promise'}, 'typo')
    write_json(mp.PROPOSALS, store)
    mi.relate('M002', 'M003')
    mi.set_note('M001', 'Rewritten by hand')
    assert mp.open_proposals() == []


def test_a_claim_checked_after_done_counts_as_seen():
    claim = lambda t, **k: {'claim': t, 'source': 'narrative', **k}  # noqa: E731
    e = {'id': 'M001', 'name': 'x', 'done': [mi.key('old')],
         'claims': [claim('old'), claim('checked since', checked='yes'), claim('unsure', checked='unsure'), claim('model')]}
    assert [c['claim'] for c in mi.public_claims(e)] == ['old', 'checked since']
    assert mi.is_done(e) == 'new'  # the model's filing and the unsure one still wait
    e['claims'] = e['claims'][:2]
    assert mi.is_done(e) == 'done'


def test_the_models_no_is_asked_again_once_a_motif_changes(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    monkeypatch.setattr(mp, 'RUNS', str(tmp_path / 'runs.json'))
    asked = []

    def judge(prompt, schema, **k):
        asked.append(prompt)
        if 'relation' in schema['properties']:
            return {'reason': 'different stories', 'relation': 'unrelated'}
        return {'fixes': []}
    monkeypatch.setattr(llm, 'complete_json', judge)
    monkeypatch.setattr(mp, 'vectors', lambda entries: np.eye(len(entries)) * 0 + 0.9)  # every pair alike
    assert mp.propose(budget=60)['finished']
    first = len(asked)
    assert first > 0 and mp.propose()['finished'] and len(asked) == first  # nothing changed: nothing asked
    mi.set_note('M002', 'A politician with nothing behind the image')
    mp.propose()
    assert len(asked) > first  # its pairs and its typo reading come back


def test_nightly_once_a_day(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    monkeypatch.setattr(mp, 'RUNS', str(tmp_path / 'runs.json'))
    runs = []
    monkeypatch.setattr(mp, 'propose', lambda budget=None: runs.append(1) or {'finished': len(runs) > 1})
    mp.nightly(); mp.nightly(); mp.nightly()
    assert len(runs) == 2  # cut short once, finished the second time, then done for the day


def test_a_merge_brings_everything_the_merged_motif_had(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    claim = lambda t, **k: {'claim': t, 'source': 'narrative', **k}  # noqa: E731
    mi.save({'next': 6, 'claims': {mi.key('a'): ['M001'], mi.key('b'): ['M002']}, 'related': [['M001', 'M004']],
             'not_same': [['M001', 'M005']], 'groups': {'G01': {'id': 'G01', 'name': 'Archetypes'}}, 'entries': {
                 'M001': {'id': 'M001', 'name': 'x', 'claims': [claim('a')], 'parents': ['M003'], 'groups': ['G01'],
                          'facets': {'genre': 'rumor'}, 'note': 'its note', 'note_by': 'person', 'done': [mi.key('a')]},
                 'M002': {'id': 'M002', 'name': 'y', 'claims': [claim('b')], 'done': [mi.key('b')]},
                 'M003': {'id': 'M003', 'name': 'broader', 'claims': []},
                 'M004': {'id': 'M004', 'name': 'cousin', 'claims': []},
                 'M005': {'id': 'M005', 'name': 'not it', 'claims': []},
                 'M006': {'id': 'M006', 'name': 'a kind of x', 'claims': [], 'parents': ['M001']}}})
    mi.merge('M001', 'M002')
    index = mi.load()
    y = index['entries']['M002']
    assert mi.parents_of(y) == ['M003'] and mi.groups_of(y) == ['G01'] and y['facets'] == {'genre': 'rumor'}
    assert y['note'] == 'its note' and mi.is_done(y) == 'done'  # x's claim was seen when x was marked done
    assert ['M002', 'M004'] in index['related'] and ['M002', 'M005'] in index['not_same']
    assert mi.parents_of(index['entries']['M006']) == ['M002']


def test_a_merge_never_makes_a_motif_a_kind_of_its_own_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    # x is a kind of k, and k is a kind of y: x into y mustn't make y a kind of k (its own kind)
    mi.save({'next': 4, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'x', 'claims': [], 'parents': ['M003']},
        'M002': {'id': 'M002', 'name': 'y', 'claims': []},
        'M003': {'id': 'M003', 'name': 'k', 'claims': [], 'parents': ['M002']}}})
    mi.merge('M001', 'M002')
    entries = mi.load()['entries']
    assert mi.parents_of(entries['M002']) == [] and mi.parents_of(entries['M003']) == ['M002']
