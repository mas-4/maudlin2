"""The claim organizer (app/analysis/claim_organizer.py): triggers fire by name on spread, not on the motif count; the
posts' motifs make tellings (layers stay one); a split is a proposal until a person approves it; applied, the parent
leaves its motifs under its own action, 'split', which the confidence model never reads as "not this motif", stays as
the telling, and its children go to file_claims with its source, story and a split_from link."""
import json

import pytest

from app.analysis import claim_organizer as co
from app.analysis import filing_confidence as fc
from app.analysis import llm
from app.analysis import motif_index as mi
from app.analysis import motif_proposals as mp
from app.analysis import watch_list as wl

PARENT = 'Canadian separatists are working with the United States to break up Canada.'


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(mp, 'PROPOSALS', str(tmp_path / 'proposals.json'))
    rec = lambda fit, **kw: {'claim': PARENT, 'source': 'narrative', 'ref': '2026-10-12T09:12', 'side': 'left',  # noqa: E731
                             'date': '2026-10-12', 'story': 7, 'story_tie': 'same event', 'fit': fit, **kw}
    mi.save({'next': 5, 'claims': {mi.key(PARENT): ['M001', 'M002', 'M003'], mi.key('other'): ['M001']},
             'related': [['M001', 'M002']], 'related_notes': {'M001|M002': 'answers Foreign meddling'},
             'entries': {
                 'M001': {'id': 'M001', 'name': 'Foreign meddling', 'facets': {'genre': 'Plots'}, 'curated': True,
                          'done': [mi.key(PARENT)],
                          'claims': [rec(0.6, checked='yes', carrying=['traitors']),
                                     {'claim': 'other', 'source': 'narrative', 'fit': 0.9}]},
                 'M002': {'id': 'M002', 'name': 'Traitors within', 'facets': {'genre': 'Plots'}, 'claims': [rec(0.5)]},
                 'M003': {'id': 'M003', 'name': 'Hypocrite', 'facets': {'genre': 'Archetypes'}, 'claims': [rec(0.7)]},
                 'M004': {'id': 'M004', 'name': 'Unused', 'claims': []}}})


def test_triggers_fire_by_name(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    index = mi.load()
    also = co.alsos([{'action': {'action': 'batch', 'steps': [{'action': 'also', 'claim': PARENT, 'source': 'M001',
                                                                   'target': 'M004'}]}},
                     {'action': {'action': 'note', 'id': 'M001', 'note': 'x'}}])
    fired = co.triggers(PARENT, index, {'variety': 0.93, 'authors': 22}, also)
    assert set(fired) == {'facing motifs', 'two of one genre', 'varied group', 'many authors', 'middling scores', 'also'}
    assert 'Foreign meddling / Traitors within' in fired['facing motifs']
    assert fired['two of one genre'] == 'Plots: Foreign meddling, Traitors within' and fired['also'] == 'Unused'
    calm = co.triggers(PARENT, index, {'variety': 0.8, 'authors': 6}, {}, fits={'M001': 0.99, 'M002': 0.5, 'M003': 0.5})
    assert set(calm) == {'facing motifs', 'two of one genre'}  # one pick fits well: not middling
    assert co.triggers('other', index) == {}  # one motif, nothing else known


def test_layers_stay_one_telling_and_motifs_on_different_posts_make_several():
    found, broad = co.tellings({'A': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 'B': [0, 1, 2], 'C': [6, 7, 8], 'D': [9]})
    assert broad == ['A']  # told across the posts: a layer of every telling
    assert [t['motifs'] for t in found] == [['B'], ['C']]  # D is told by one post only: not told
    found, broad = co.tellings({'A': [0, 1, 2, 3], 'B': [1, 2]})  # B within A's posts: one telling in layers
    assert [t['motifs'] for t in found] == [['B']] and broad == ['A']
    found, broad = co.tellings({'A': [0, 1, 2], 'B': [1, 2, 3], 'C': [4, 5, 6]})  # A and B overlap: one telling
    assert [sorted(t['motifs']) for t in found] == [['A', 'B'], ['C']] and broad == []


def test_organize_reads_the_posts_and_drafts_a_child_per_telling(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    asked = []

    def answer(prompt, schema, **kw):
        asked.append(prompt)
        if 'tells' in schema['properties']:
            return {'tells': [[1, 2, 3], [4, 5, 9], [1, 2, 3, 4, 5, 6]]}
        return {'claims': ['Alberta separatists are colluding with Trump to break up Canada.',
                           'Anyone who works with a foreign power to break up Canada is a traitor.']}
    monkeypatch.setattr(llm, 'complete_json', answer)
    posts = [f'post {n}' for n in range(1, 7)]
    got = co.organize(PARENT, posts, ['M001', 'M002', 'M003'])
    assert got['split'] and [c['posts'] for c in got['children']] == [[0, 1, 2], [3, 4]]  # 9 is no post: dropped
    assert got['children'][0]['motifs'] == ['M001', 'M003'] and got['broad'] == ['M003']  # told by all: a layer of each
    assert "one side's assertion in that side's own voice" in asked[1] and 'word the argument itself' not in asked[1]
    assert co.organize(PARENT, posts, ['M001'])['reason'] == 'one motif picked' and len(asked) == 2  # no question
    assert 'too few' in co.organize(PARENT, posts[:3], ['M001', 'M002'])['reason']


def test_motifs_told_by_the_same_posts_are_no_split(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: {'tells': [[1, 2, 3, 4], [2, 3], []]})
    got = co.organize(PARENT, [f'post {n}' for n in range(6)], ['M001', 'M002', 'M003'])
    assert not got['split'] and got['reason'] == 'one telling: Foreign meddling, Traitors within told by the same posts'
    store = {}
    i = co.propose(store, got, {'two of one genre': 'Plots'})
    assert store[i]['kind'] == 'no_split' and store[i]['status'] == 'none'
    assert co.asked(store, PARENT, ['M003', 'M002', 'M001'])  # not asked again for the same picks
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: None)
    assert co.propose(store, co.organize(PARENT, ['p'] * 6, ['M001', 'M002'])) is None  # a failed read isn't kept


def proposed(monkeypatch, tmp_path) -> str:
    setup(monkeypatch, tmp_path)
    result = {'claim': PARENT, 'motifs': ['M001', 'M002', 'M003'], 'posts': 6, 'split': True, 'reason': 'r',
              'children': [{'claim': 'Alberta separatists collude with Trump.', 'posts': [0, 1], 'motifs': ['M001']},
                           {'claim': 'Separatists are traitors.', 'posts': [2, 3], 'motifs': ['M002']}]}
    store = mp.load()
    i = co.propose(store, result, {'facing motifs': 'x'}, keys=[['k1'], ['k2', 'k2b'], ['k3'], ['k4'], ['k5'], ['k6']])
    mp.save(store)
    return i


def test_a_split_is_a_proposal_until_approved(monkeypatch, tmp_path):
    i = proposed(monkeypatch, tmp_path)
    p = mp.load()[i]
    assert p['kind'] == 'split' and p['status'] == 'open' and p['args']['children'][0]['keys'] == ['k1', 'k2', 'k2b']
    assert 'text' not in json.dumps(p)  # the posts' words stay in the post store
    assert i not in {x['id'] for x in mp.open_proposals()}  # its own checklist, not the workbench's
    opened = co.open_splits()
    assert [x['id'] for x in opened] == [i] and opened[0]['do'] == {
        'action': 'split', 'proposal': i, 'claim': PARENT,
        'children': ['Alberta separatists collude with Trump.', 'Separatists are traitors.']}
    assert [f['id'] for f in opened[0]['filings']] == ['M001', 'M002', 'M003']
    assert opened[0]['children'][0]['names'] == ['Foreign meddling']
    assert mi.load()['entries']['M001']['claims'][0]['claim'] == PARENT  # nothing applied


def test_applying_a_split_keeps_the_telling_and_refiles_the_children(monkeypatch, tmp_path):
    i = proposed(monkeypatch, tmp_path)
    filed = []
    monkeypatch.setattr(mi, 'file_claims', lambda claims, **kw: filed.extend(claims))
    done = co.apply_split(i, why='two tellings')
    assert done == {'action': 'split', 'claim': PARENT, 'ids': ['M001', 'M002', 'M003'],
                    'children': ['Alberta separatists collude with Trump.', 'Separatists are traitors.'],
                    'proposal': i, 'why': 'two tellings'}
    index = mi.load()
    k = mi.key(PARENT)
    assert index['claims'][k] == [] and all(c['claim'] != PARENT for e in index['entries'].values() for c in e['claims'])
    assert not any(k in e.get('not_claims', []) for e in index['entries'].values())  # not "not this motif"
    assert k not in index['entries']['M001']['done'] and 'M002' in index['entries']  # an emptied motif stays
    told = index['tellings'][k]
    assert told['by'] == 'model' and told['children'] == done['children'] and told['proposal'] == i
    assert told['filings'][0]['id'] == 'M001' and told['filings'][0]['carrying'] == ['traitors']
    assert filed == [{'source': 'narrative', 'ref': '2026-10-12T09:12', 'side': 'left', 'date': '2026-10-12',
                      'story': 7, 'story_tie': 'same event', 'claim': c, 'split_from': PARENT} for c in done['children']]
    assert mp.load()[i]['status'] == 'approved' and 'final' not in mp.load()[i] and mp.load()[i]['why'] == 'two tellings'
    assert co.open_splits() == []
    with pytest.raises(ValueError):
        co.apply_split(i)  # decided already
    with pytest.raises(ValueError):
        co.apply_split(claim=PARENT, children=['again'])  # split already


def test_the_confidence_model_never_reads_a_split_as_not_this_motif(tmp_path):
    log = tmp_path / 'curation_log.jsonl'
    rows = [{'action': {'action': 'split', 'claim': PARENT, 'ids': ['M001', 'M002'], 'children': ['a', 'b']}},
            {'action': {'action': 'batch', 'steps': [{'action': 'split', 'claim': 'B', 'ids': ['M003'], 'children': ['c']},
                                                     {'action': 'unfile', 'claim': 'C', 'id': 'M003'}]}}]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    assert fc.decisions(str(log)) == {(mi.key('C'), 'M003'): False}
    assert fc.decisions(str(log), hand=True) == {(mi.key('C'), 'M003'): False}


def test_a_hand_split_and_edited_children_take_the_same_path(monkeypatch, tmp_path):
    i = proposed(monkeypatch, tmp_path)
    done = co.apply_split(i, children=['Alberta separatists collude with Trump.', {'claim': ' A  third  telling '}, PARENT],
                          refile=False)
    assert done['children'] == ['Alberta separatists collude with Trump.', 'A third telling']  # the parent isn't its own child
    assert mp.load()[i]['final'] == {'action': 'split', 'claim': PARENT, 'children': done['children']}
    assert mi.load()['tellings'][mi.key(PARENT)]['by'] == 'person'
    waiting = co.pending()  # not filed yet: the hourly run's
    assert [c['claim'] for c in waiting] == done['children'] and waiting[0]['split_from'] == PARENT
    assert waiting[0]['story'] == 7
    hand = co.apply_split(claim='other', children=['one part', 'another'], refile=False)
    assert 'proposal' not in hand and hand['ids'] == ['M001'] and mi.load()['tellings'][mi.key('other')]['by'] == 'person'
    with pytest.raises(ValueError):
        co.apply_split(claim='never filed', children=['x'])


def test_a_rejected_split_is_kept_and_a_telling_is_never_watched_as_plain(monkeypatch, tmp_path):
    i = proposed(monkeypatch, tmp_path)
    co.reject_split(i, 'one telling in layers')
    assert mp.load()[i]['status'] == 'rejected' and co.open_splits() == []
    co.apply_split(claim=PARENT, children=['a', 'b'], refile=False)
    index = mi.load()
    assert wl.state(index, mi.key(PARENT), set()) is None  # no motif, but a telling, not plain news
