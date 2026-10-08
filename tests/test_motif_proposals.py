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
    for _ in range(3):
        mp.nightly()
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


def test_links_the_model_thinks_wrong_come_up_for_removal(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    mi.relate('M002', 'M003')
    mi.set_parent('M002', 'M001')
    calls = []

    def judge(prompt, schema, **k):
        calls.append(prompt)
        return {'reason': 'different stories' if 'Rigged' in prompt else 'a narrower one',
                'relation': 'unrelated' if 'Rigged' in prompt else 'A is a kind of B'}
    monkeypatch.setattr(llm, 'complete_json', judge)
    store = {}
    assert mp.review(store, mi.load()) == 1
    write_json(mp.PROPOSALS, store)
    queue = validate.workbench_queue('proposals')
    assert [p['kind'] for p in queue] == ['unrelate']
    validate.workbench_action({**queue[0]['do'], 'proposal': queue[0]['id']})
    assert ['M002', 'M003'] not in mi.load().get('related', [])
    n = len(calls)
    mp.review(mp.load(), mi.load())
    assert len(calls) == n  # the kept link isn't read again while neither motif changes


def test_a_motif_a_person_made_and_noted_is_done(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    claim = lambda t: {'claim': t, 'source': 'narrative', 'checked': 'yes'}  # noqa: E731
    mi.save({'next': 3, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'mine', 'curated': True, 'claims': [claim('a')]},
        'M002': {'id': 'M002', 'name': 'the model\'s', 'claims': [claim('b')]}}})
    mi.set_note('M001', 'What it covers')
    mi.set_note('M002', 'A note on a motif the model named')
    e = mi.load()['entries']
    assert mi.is_done(e['M001']) == 'done' and mi.public(e['M001'])
    assert 'done' not in e['M002']  # the model's motif: not until a person names it or marks it
    mi.rename('M002', 'Now mine')
    assert mi.is_done(mi.load()['entries']['M002']) == 'done'
    mi.mark_done('M001', False)  # unmarked by hand: a later note doesn't mark it done again
    mi.set_note('M001', 'Reworded')
    assert 'done' not in mi.load()['entries']['M001']


def test_a_runs_save_keeps_decisions_made_meanwhile(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    store = {}
    mp.add(store, 'relate', {'a': 'M001', 'b': 'M002'}, 'cousins')
    write_json(mp.PROPOSALS, store)
    run = mp.load()  # a run reads the store, then works for a while
    i = next(iter(run))
    mp.decide(i, 'rejected')  # meanwhile the person rejects it in the checker
    run[i]['judge'] = {'score': 2, 'reason': 'a stretch', 'model': 'm'}
    mp.add(run, 'relate', {'a': 'M002', 'b': 'M003'}, 'new one')
    mp.save(run)
    disk = mp.load()
    assert disk[i]['status'] == 'rejected' and disk[i]['judge']['score'] == 2 and len(disk) == 2


def test_best_fit_sorts_the_links_and_folds_the_unlikely(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    monkeypatch.setattr(mp, 'RUNS', str(tmp_path / 'runs.json'))
    monkeypatch.setattr(mp, 'FIT_MIN', 4)
    vec = {'M001': [1, 0, 0], 'M002': [0.9, 0.44, 0], 'M003': [0, 0, 1]}
    import app.narratives
    monkeypatch.setattr(app.narratives, 'embed', lambda texts: np.array(
        [vec[next(k for k, n in (('M001', 'Poltiicians'), ('M002', 'Empty suit'), ('M003', 'Rigged')) if n in t)]
         if any(n in t for n in ('Poltiicians', 'Empty suit', 'Rigged')) else [0, 1, 0] for t in texts], dtype=float))
    store = {}
    # decided: high judge scores approved, low rejected
    for n, (score, status) in enumerate([(9, 'approved'), (8, 'approved'), (2, 'rejected'), (1, 'rejected'), (9, 'approved'), (2, 'rejected')]):
        i = f'd{n}'
        store[i] = {'id': i, 'kind': 'relate', 'args': {'a': 'M001', 'b': 'M003'}, 'status': status, 'made': '1',
                    'judge': {'score': score}}
    mp.add(store, 'relate', {'a': 'M001', 'b': 'M002'}, 'good')
    mp.add(store, 'parent', {'id': 'M003', 'parent': 'M002'}, 'bad')
    mp.add(store, 'rename', {'id': 'M001', 'from': "Poltiicians' empty promises", 'to': "Politicians' empty promises"}, 'typo')
    good, bad = (next(p for p in store.values() if p.get('reason') == r) for r in ('good', 'bad'))
    good['judge'], bad['judge'] = {'score': 9}, {'score': 1}
    info = mp.best_fit(store, mi.load())
    assert info['trained_on'] == 6 and good['fit'] > bad['fit']
    mp.save(store)
    order = mp.open_proposals()
    assert [p['kind'] for p in order] == ['rename', 'relate', 'parent']  # typo fixes first, then best fit first
    assert not order[1]['unlikely'] and order[2]['unlikely']


def test_the_judge_scores_open_links_and_is_shown_the_persons_decisions(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    store = {}
    mp.add(store, 'relate', {'a': 'M001', 'b': 'M002'}, 'cousins')
    store['old'] = {'id': 'old', 'kind': 'relate', 'args': {'a': 'M001', 'b': 'M003'}, 'status': 'rejected', 'made': '1'}
    prompts = []
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, *a, **k: prompts.append(prompt) or {'reason': 'ok', 'score': 7})
    assert mp.judge(store, mi.load()) == 2  # the open one, then the decided one (to train on)
    assert 'REJECTED' in prompts[0] and 'Rigged votes' in prompts[0]  # the person's decision shown
    assert all(p['judge']['score'] == 7 for p in store.values())


def test_rests_on_crosses_genres(tmp_path, monkeypatch):
    """Oct 8, the person: 'kind of' became 'rests on', which may cross genres (an Argument resting on a Theory); the
    within-genre rule of Oct 7 is gone"""
    index_with(tmp_path, monkeypatch)
    mi.set_facet('M001', 'genre', 'Theories')
    mi.set_facet('M002', 'genre', 'Arguments')
    mi.set_parent('M002', 'M001')  # Magic money tree rests on Politicians' empty promises
    mi.set_facet('M003', 'genre', 'Plots')
    mi.set_parent('M003', 'M002')
    mi.set_facet('M003', 'genre', 'Archetypes')  # a genre can change whatever it rests on
    assert mi.parents_of(mi.load()['entries']['M002']) == ['M001']
    import pytest
    with pytest.raises(ValueError):  # never a loop
        mi.set_parent('M001', 'M003')


def test_a_merge_keeps_what_it_rests_on_across_genres(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    mi.set_parent('M002', 'M001')
    mi.set_facet('M001', 'genre', 'Theories')
    mi.set_facet('M003', 'genre', 'Plots')
    mi.merge('M002', 'M003')  # into a Plot: what it rested on, a Theory, comes along
    assert mi.parents_of(mi.load()['entries']['M003']) == ['M001']


def test_genres_are_proposed_from_the_persons_examples(tmp_path, monkeypatch):
    index_with(tmp_path, monkeypatch)
    index = mi.load()
    for i, g in (('M001', 'Theories'), ('M002', 'Archetypes')):
        index['entries'][i]['facets'] = {'genre': g}
    index['entries']['M003']['done'] = [mi.key('c')]  # verified, no genre
    mi.save(index)
    prompts = []
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, schema, **k: prompts.append((prompt, schema)) or {'reason': 'a plot', 'genre': 'Archetypes'})
    store = {}
    assert mp.genres(store, mi.load()) == 1
    p = next(x for x in store.values() if x['kind'] == 'genre')
    assert p['args'] == {'id': 'M003', 'genre': 'Archetypes'} and 'Empty suit' in prompts[0][0]
    assert prompts[0][1]['properties']['genre']['enum'] == ['Archetypes', 'Theories', 'none']
    assert mp.genres(store, mi.load()) == 0  # never asked twice
    assert mp.action(p) == {'action': 'facet', 'id': 'M003', 'facet': 'genre', 'value': 'Archetypes'}
    mi.set_parent('M003', 'M001')  # resting on a Theory: an Archetype still may (Oct 8)
    assert mp.still_holds(p, mi.load())
    mi.set_facet('M003', 'genre', 'Theories')  # given a genre meanwhile: no longer holds
    assert not mp.still_holds(p, mi.load())


def test_a_rests_on_link_needs_no_related_one(tmp_path, monkeypatch):
    """The person, Oct 8: every rests on shouldn't need a relate"""
    index_with(tmp_path, monkeypatch)
    mi.relate('M002', 'M001')
    assert ['M001', 'M002'] in mi.load()['related']
    mi.set_parent('M002', 'M001')  # Empty suit rests on Politicians' empty promises: the related link goes
    assert ['M001', 'M002'] not in mi.load()['related']
    mi.relate('M001', 'M002')  # relating them again adds nothing: the rests-on covers it
    assert ['M001', 'M002'] not in mi.load()['related']
    mi.relate('M003', 'M001')  # a pair without one is related as before
    assert ['M001', 'M003'] in mi.load()['related']
    store = {}
    mp.add(store, 'relate', {'a': 'M001', 'b': 'M002'}, 'x')
    assert not mp.still_holds(next(iter(store.values())), mi.load())
