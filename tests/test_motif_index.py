import json

import numpy as np
import pytest

from app.analysis import llm, motif_index as mi


def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))


def test_files_new_and_matching_claims(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    names = {'Biden is too old to govern': 'the ruler is senile', 'Trump is losing his mind': 'the ruler is senile',
             'Texas will turn blue this year': 'the realignment that keeps not coming'}

    def complete_json(prompt, schema, max_tokens=0, model=None):
        # Filing is judged by JUDGE_MODEL; matching a new name to an existing motif stays with MODEL
        assert model == (mi.MODEL if 'pick' in schema['properties'] else mi.JUDGE_MODEL)
        claim = prompt.splitlines()[1]  # the claim's own line: the shown motifs' example claims come later
        name = next(v for k, v in names.items() if k in claim)
        if 'motifs' in schema['properties']:  # the first claim, with nothing in the index to show
            return {'motifs': [name + '.']}
        if 'fits' in schema['properties']:  # judged with the closest motifs shown side by side: reuse one that fits
            shown = [line.split('. ', 1)[1].split(' (')[0] for line in prompt.splitlines() if line[:1].isdigit()]
            return {'reason': '', 'fits': [shown.index(name) + 1] if name in shown else []}
        if 'new' in schema['properties']:  # none fits: asked whether it tells a story to name
            return {'reason': '', 'new': [name]}
        return {'reason': '', 'pick': 'new'}

    monkeypatch.setattr(llm, 'complete_json', complete_json)
    from app import narratives
    vec = {'the ruler is senile': [1, 0], 'the realignment that keeps not coming': [0, 1]}
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array([vec.get(t.split('.')[0], [.7, .7]) for t in texts], float))
    index = mi.file_claims([{'claim': c, 'source': 'narrative'} for c in names])
    entries = sorted(mi.live(index), key=lambda e: e['id'])
    assert [(e['id'], e['name'], len(e['claims'])) for e in entries] == [
        ('M001', 'the ruler is senile', 2), ('M002', 'the realignment that keeps not coming', 1)]
    assert mi.entry_of(index, 'Trump is losing his mind')['id'] == 'M001'


def test_curation_merge_rename_move_delete(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001'], mi.key('b'): ['M002'], mi.key('c'): ['M003', 'M001']},
             'entries': {
        eid: {'id': eid, 'name': name, 'claims': [{'claim': claim, 'source': 'narrative'}], 'phrases': [name]}
        for eid, name, claim in (('M001', 'x', 'a'), ('M002', 'y', 'b'), ('M003', 'z', 'c'))}})
    mi.load()['entries']['M001']['claims'].append({'claim': 'c', 'source': 'narrative'})
    mi.merge('M002', 'M001')
    index = mi.load()
    assert len(index['entries']['M001']['claims']) == 2 and mi.entry_of(index, 'b')['id'] == 'M001'
    assert index['entries']['M002']['merged_into'] == 'M001'  # the old number still resolves
    mi.rename('M001', 'the ruler is / isn’t fit 结果')
    assert mi.load()['entries']['M001'] | {} and mi.load()['entries']['M001']['name'] == 'the ruler is / isn’t fit'
    assert mi.load()['entries']['M001']['curated']
    mi.move('b', 'M001', 'M003')
    assert mi.entry_of(mi.load(), 'b')['id'] == 'M003' and len(mi.load()['entries']['M001']['claims']) == 1
    mi.delete('M003')
    index = mi.load()
    assert 'M003' not in index['entries'] and index['claims'][mi.key('b')] == []  # filed, motif dropped: not again
    assert [e['id'] for e in mi.entries_of(index, 'c')] == ['M001']  # its other motif stays
    mi.not_same('M001', 'M002')
    assert ['M001', 'M002'] in mi.load()['not_same']


def test_naming_prompt_has_no_example_names_to_copy():
    # The model copied prompt examples before ("the false flag", "the hidden ruler"); quoted examples invite it
    import re
    quoted = re.findall(r'"([^"{}]+)"', mi.NAME_PROMPT)
    # ...but the naming rules' two bad names, shown as what not to do, may stay (Oct 10)
    assert all(q in ('a claim that', 'is accused of', 'X of Y via Z', "Trump's influence on candidates")
               for q in quoted), quoted  # even a template got copied ("X is Y")


def test_a_sentence_is_not_a_motif_name(monkeypatch, tmp_path):
    """The model once gave a claim's own sentence as its motif (an LAX kidnapping, Oct 5)"""
    fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    claim = 'A woman was kidnapped at LAX Airport by men in plain clothes'
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, schema, **k: {'motifs': [claim, 'no warrant shown']})
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.ones((len(texts), 2)))
    index = mi.file_claims([{'claim': claim, 'source': 'narrative'}])
    assert [e['name'] for e in mi.live(index)] == ['no warrant shown']


def test_which_folklore_claims_are_filed():
    news = 'news report or shared reaction'
    assert mi.fits({'genre': news, 'politics': True})  # news that confirms a story people tell
    assert not mi.fits({'genre': news, 'politics': False, 'family': 'celebrities'})  # a quarterback's bad game
    assert not mi.fits({'genre': 'prophecy or prediction', 'politics': False, 'family': 'none'})  # a sports pick
    assert mi.fits({'genre': 'contemporary legend', 'politics': False, 'family': 'contamination, health and medicine'})
    assert not mi.fits({'genre': 'none: a shared topic, not a retold narrative', 'politics': True})



def test_a_name_already_in_the_index_is_reused_word_for_word(monkeypatch, tmp_path):
    """'Blame shifting' was coined four times as four entries (Oct 5)"""
    fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, schema, **k:
                        {'motifs': ['Blame shifting']} if 'motifs' in schema['properties']
                        else {'reason': '', 'fits': []} if 'fits' in schema['properties']
                        else {'reason': '', 'new': ['Blame-shifting.']} if 'new' in schema['properties']
                        else {'reason': '', 'pick': 'new'})  # the model says new; the name says otherwise
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.ones((len(texts), 2)) / np.sqrt(2))
    index = mi.file_claims([{'claim': 'Trump blames Iowans', 'source': 'Snopes'},
                            {'claim': 'Cooper blamed for rape kits', 'source': 'FactCheck.org'}])
    assert [(e['name'], len(e['claims'])) for e in mi.live(index)] == [('Blame shifting', 2)]


def test_a_no_on_the_motif_check_takes_the_claim_out_for_good(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    index = {'next': 3, 'claims': {mi.key('a'): ['M001', 'M002'], mi.key('b'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'blame shifting', 'claims': [{'claim': 'a', 'source': 'x'}, {'claim': 'b', 'source': 'x'}]},
        'M002': {'id': 'M002', 'name': 'hope for unity', 'claims': [{'claim': 'a', 'source': 'x'}]}}}
    mi.save(index)
    assert [q['id'] for q in mi.to_check()] == ['M001', 'M001', 'M002']  # the most-used motif first
    mi.check('b', 'M001', 'yes')
    mi.check('a', 'M002', 'no')  # its only claim: the motif goes
    index = mi.load()
    assert 'M002' not in index['entries'] and index['claims'][mi.key('a')] == ['M001']
    mi.check('a', 'M001', 'no')  # its last motif: it has none now, and isn't filed again (no shoehorning)
    index = mi.load()
    assert index['claims'][mi.key('a')] == [] and mi.key('a') in index['entries']['M001']['not_claims']
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: (_ for _ in ()).throw(AssertionError('asked again')))
    mi.file_claims([{'claim': 'a', 'source': 'x'}])  # left alone: not asked about again
    assert [q['claim'] for q in mi.to_check()] == []  # b checked, a out
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.ones((len(texts), 2)) / np.sqrt(2))
    assert mi.closest(index, 'a') == [] and mi.match(index, 'blame shifting', 'a') is None


def test_moving_a_claim_to_a_new_motif_doesnt_wait_on_itself(monkeypatch, tmp_path):
    """move() makes the new entry while holding the index lock; it mustn't ask for the lock again"""
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {mi.key('a'): ['M001']},
             'entries': {'M001': {'id': 'M001', 'name': 'x', 'claims': [{'claim': 'a', 'source': 's'}]}}})
    mi.move('a', 'M001', 'new')
    assert mi.load()['claims'][mi.key('a')] == ['M002']


def test_done_marks_hide_a_motif_until_a_new_claim_comes_in(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {mi.key('a'): ['M001']},
             'entries': {'M001': {'id': 'M001', 'name': 'x', 'claims': [{'claim': 'a', 'source': 's'}]}}})
    mi.mark_done('M001')
    assert mi.board()['entries'][0]['done'] == 'done'
    index = mi.load()
    index['entries']['M001']['claims'].append({'claim': 'b', 'source': 's'})
    mi.save(index)
    assert mi.board()['entries'][0]['done'] == 'new'  # back, flagged
    mi.reset_done()
    assert mi.board()['entries'][0]['done'] is None


def test_a_seed_marked_done_stays_done_when_claims_come(monkeypatch, tmp_path):
    """A seed marked done has no claims seen yet (an empty list): it's still done and public (Oct 9: 8 seeds weren't)"""
    from app.analysis import filing_confidence as fc
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'Lucretia', 'claims': []}}})
    mi.mark_done('M001')
    e = mi.load()['entries']['M001']
    assert e['done'] == [] and mi.public(e) and fc.yours(e)
    e['claims'].append({'claim': 'a', 'source': 's'})
    assert mi.is_done(e) == 'new' and mi.public(e) and not mi.public_claims(e)  # the new claim waits for a check


def test_more_like_this_ranks_other_claims_and_remembers_not_this(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 3, 'claims': {mi.key(t): [i] for t, i in (('a', 'M001'), ('b', 'M002'), ('c', 'M002'))},
             'entries': {'M001': {'id': 'M001', 'name': 'x', 'claims': [claim('a')]},
                         'M002': {'id': 'M002', 'name': 'y', 'claims': [claim('b'), claim('c')]}}})
    vec = {'x. a': [1, 0], 'b': [0.9, 0.1], 'c': [0, 1]}
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array([vec[t] for t in texts], float))
    assert [i['claim'] for i in mi.similar('M001')] == ['b', 'c']  # closest first, its own claim left out
    mi.reject('b', 'M001')
    assert [i['claim'] for i in mi.similar('M001')] == ['c']


def test_a_motif_can_be_a_kind_of_several_others(monkeypatch, tmp_path):
    """Fake news is a kind of misinformation and of disinformation: several parents, never a loop"""
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 5, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Misinformation spread', 'claims': [claim('a')]},
        'M002': {'id': 'M002', 'name': 'Disinformation campaign', 'claims': [claim('b')]},
        'M003': {'id': 'M003', 'name': 'Fake news fabrication', 'claims': [claim('c')]},
        'M004': {'id': 'M004', 'name': 'Old', 'parent': 'M001', 'claims': [claim('d')]}}})  # saved the old way
    mi.set_parent('M003', 'M001')
    mi.set_parent('M003', 'M002')
    parents = {e['id']: e['parents'] for e in mi.board()['entries']}
    assert parents == {'M001': [], 'M002': [], 'M003': ['M001', 'M002'], 'M004': ['M001']}
    assert ['M001', 'M003'] in mi.load()['not_same']  # related: not suggested as a merge again
    with pytest.raises(ValueError):
        mi.set_parent('M002', 'M003')  # no loops
    mi.merge('M001', 'M004')  # a parent merged away: its kinds follow; a motif is never its own kind
    assert mi.load()['entries']['M003']['parents'] == ['M004', 'M002']
    mi.set_parent('M003', 'M002', on=False)
    assert mi.load()['entries']['M003']['parents'] == ['M004']


def test_motifs_filed_together_on_two_claims_are_paired(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001', 'M002'], mi.key('b'): ['M001', 'M002'], mi.key('c'): ['M001', 'M003'],
                                   mi.key('d'): ['M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Nazi comparisons', 'claims': [claim('a'), claim('b'), claim('c')]},
        'M002': {'id': 'M002', 'name': 'Oppressive policies', 'claims': [claim('a'), claim('b'), claim('d')]},
        'M003': {'id': 'M003', 'name': 'x', 'claims': [claim('c')]}}})
    [p] = mi.shared_pairs()
    assert (p['a'], p['b'], sorted(p['shared']), p['only_a'], p['only_b']) == ('M001', 'M002', ['a', 'b'], ['c'], ['d'])
    mi.set_parent('M002', 'M001')
    assert mi.shared_pairs() == []  # linked as kinds: not a candidate any more


def test_two_motifs_can_be_related_without_being_one(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001', 'M002'], mi.key('b'): ['M001', 'M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Rape accusation against men', 'claims': [claim('a'), claim('b')]},
        'M002': {'id': 'M002', 'name': 'Campus sexual assault controversy', 'claims': [claim('a'), claim('b')]},
        'M003': {'id': 'M003', 'name': 'x', 'claims': [claim('c')]}}})
    assert len(mi.shared_pairs()) == 1
    mi.relate('M002', 'M001')
    related = {e['id']: e['related'] for e in mi.board()['entries']}
    assert related == {'M001': ['M002'], 'M002': ['M001'], 'M003': []}  # both ways
    assert mi.shared_pairs() == []  # not suggested as one motif any more
    mi.merge('M002', 'M003')  # a link follows a merged motif
    assert {e['id']: e['related'] for e in mi.board()['entries']} == {'M001': ['M003'], 'M003': ['M001']}
    mi.relate('M001', 'M003', False)
    assert all(not e['related'] for e in mi.board()['entries'])


def test_a_related_link_keeps_its_reason_until_the_link_goes(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 4, 'claims': {}, 'entries': {eid: {'id': eid, 'name': eid, 'claims': [claim(eid)]}
                                                 for eid in ('M001', 'M002', 'M003')}})
    mi.relate('M002', 'M001', note='  a case of it,   not a sibling ')
    board = {e['id']: e for e in mi.board()['entries']}
    assert board['M001']['related_notes'] == {'M002': 'a case of it, not a sibling'}
    assert board['M002']['related_notes'] == {'M001': 'a case of it, not a sibling'}
    mi.relate('M001', 'M002')  # relating again without a note keeps the reason
    assert mi.related_note(mi.load(), 'M001', 'M002') == 'a case of it, not a sibling'
    mi.merge('M002', 'M003')  # the reason follows a merged motif
    assert mi.related_note(mi.load(), 'M003', 'M001') == 'a case of it, not a sibling'
    mi.relate('M001', 'M003', False)  # and goes with the link
    assert mi.load().get('related_notes') == {}


def test_what_a_motif_is_not_reaches_the_filing_model(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'Graft', 'note': 'officials enrich themselves',
                                                          'claims': [{'claim': 'the mayor took bribes', 'source': 's'}]}}})
    mi.set_not_this('M001', ' a cover-up of the graft, which is its own motif ')
    e = mi.load()['entries']['M001']
    assert e['not_this'] == 'a cover-up of the graft, which is its own motif'
    assert mi.board()['entries'][0]['not_this'] == e['not_this']
    seen = {}
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, *a, **k: seen.setdefault('prompt', prompt) and {'reason': '', 'fits': [1]})
    assert mi.name_claim('the senator sold his vote', [e])['existing'][0]['id'] == 'M001'
    assert '1. Graft (officials enrich themselves)\n   Not this: a cover-up of the graft' in seen['prompt']
    assert mi.described(e) == 'Graft (officials enrich themselves)'  # likeness stays on what it is
    mi.set_not_this('M001', '')
    assert 'not_this' not in mi.load()['entries']['M001'] and mi.not_this(mi.load()['entries']['M001']) == ''


def test_a_corrected_summary_replaces_the_models_everywhere(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    old = 'A video shows a large group of Muslims chanting in Dublin in September 2026.'
    new = 'Old footage of German football hooligans is passed off as Muslims taking over Dublin.'
    mi.save({'next': 3, 'claims': {mi.key(old): ['M001', 'M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Misattributed video', 'claims': [{'claim': old, 'source': 'Lead Stories'}],
                 'done': [mi.key(old)]},
        'M002': {'id': 'M002', 'name': 'x', 'claims': [{'claim': old, 'source': 'Lead Stories'}]}}})
    mi.correct_claim(old, new)
    index = mi.load()
    assert [c['claim'] for e in mi.live(index) for c in e['claims']] == [new, new]
    assert index['claims'] == {mi.key(new): ['M001', 'M002']} and mi.is_done(index['entries']['M001']) == 'done'
    assert mi.corrected(old, index) == new and mi.originals(new, index) == {old, new}
    mi.correct_claim(new, 'Hooligan video relabeled as Muslims in Dublin')  # corrected again: the model's words follow
    assert mi.corrected(old) == 'Hooligan video relabeled as Muslims in Dublin'


def test_a_claim_not_yet_filed_can_be_filed_by_hand(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'Gaming the system', 'claims': [],
                                                           'curated': True, 'not_claims': [mi.key('a')]}}})
    mi.file_by_hand({'claim': 'a', 'source': 'Snopes', 'ref': 'https://x'}, 'M001')
    index = mi.load()
    assert index['claims'] == {mi.key('a'): ['M001']} and index['entries']['M001']['claims'][0]['source'] == 'Snopes'
    assert index['entries']['M001']['not_claims'] == []  # filed by hand: a person's earlier 'not this' is overruled


def test_single_claim_motifs_get_the_closest_motifs_to_join(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 4, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Miracle cure', 'claims': [claim('radium water cures all')]},
        'M002': {'id': 'M002', 'name': 'Folk remedy', 'claims': [claim('a'), claim('b')]},
        'M003': {'id': 'M003', 'name': 'Rigged election', 'claims': [claim('c'), claim('d')]}}})
    vec = {'radium water cures all': [1, 0]}
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array(
        [vec.get(t, [0.9, 0.1] if t.startswith('Folk') else [0, 1]) for t in texts], float))
    [s] = mi.single_suggestions()
    assert s['id'] == 'M001' and [m['name'] for m in s['suggest']] == ['Folk remedy', 'Rigged election']
    mi.set_parent('M001', 'M002')  # put under a broader motif: placed, off the list
    assert mi.single_suggestions() == []
    mi.set_parent('M001', 'M002', False)
    mi.set_parent('M002', 'M001')  # or with a kind of its own
    assert mi.single_suggestions() == []
    mi.set_parent('M002', 'M001', False)  # a pair settled once (kinds, related, kept apart) isn't suggested again
    [s] = mi.single_suggestions()
    assert [m['name'] for m in s['suggest']] == ['Rigged election']
    mi.stands_alone('M001')
    assert mi.single_suggestions() == []


def test_a_scope_note_is_read_with_the_name_when_matching(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'Leviathan',
                                                           'claims': [{'claim': 'a', 'source': 's'}]}}})
    mi.set_note('M001', '  a giant   sea creature menaces a ship ')
    entry = mi.load()['entries']['M001']
    assert mi.described(entry) == 'Leviathan (a giant sea creature menaces a ship)'
    assert mi.board()['entries'][0]['note'] == 'a giant sea creature menaces a ship'
    mi.set_note('M001', '')
    assert 'note' not in mi.load()['entries']['M001']


def test_the_model_drafts_notes_a_person_keeps_or_replaces(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 4, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Punchable face', 'claims': [{'claim': 'his smirk proves he is evil', 'source': 's'},
                                                                    {'claim': 'her sneer shows she lies', 'source': 's'},
                                                                    {'claim': 'look at his eyes', 'source': 's'}]},
        'M004': {'id': 'M004', 'name': 'Too small', 'claims': [{'claim': 'c', 'source': 's'}]},
        'M002': {'id': 'M002', 'name': 'Mine', 'note': 'what a person wrote', 'claims': [{'claim': 'b', 'source': 's'}]},
        'M003': {'id': 'M003', 'name': 'Empty', 'claims': []}}})
    monkeypatch.setattr(mi.llm, 'complete_json', lambda prompt, *a, **k: {'common': 'looks', 'note': " A public figure's looks  are taken as proof of bad character. "}
                        if 'Punchable face' in prompt and 'smirk' in prompt else None)
    assert mi.gloss_missing() == 1  # a person's note is never replaced; motifs under GLOSS_MIN claims wait
    index = mi.load()
    m1, m2 = index['entries']['M001'], index['entries']['M002']
    assert m1['note'] == "A public figure's looks are taken as proof of bad character." and m1['note_by'] == 'model'
    assert 'proof of bad character' in mi.described(m1)  # matching uses the draft at once
    assert mi.public_note(m1) == '' and mi.public_note(m2) == 'what a person wrote'  # the site, only a person's
    assert mi.public_note({'note': 'backfilled', 'note_by': 'claude'}) == ''  # the Oct 5 backfill is a draft too
    assert not mi.needs_gloss({'note': 'backfilled', 'note_by': 'claude', 'claims': [{}] * 9, 'note_claims': 1})
    assert not mi.needs_gloss(m1)  # drafted at 3 claims: redrafted at 6
    assert mi.needs_gloss({**m1, 'claims': m1['claims'] * 2})
    mi.keep_note('M001')
    assert not mi.needs_gloss({**mi.load()['entries']['M001'], 'claims': m1['claims'] * 2})  # kept: never redrafted
    assert mi.public_note(mi.load()['entries']['M001']).startswith("A public figure's")
    mi.set_note('M001', 'looks as proof of character')
    assert mi.load()['entries']['M001']['note_by'] == 'person'


def test_a_draft_that_judges_or_names_is_asked_for_again(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    answers = iter([{'common': 'x', 'note': 'Politicians are falsely accused of taking bribes.'},
                    {'common': 'x', 'note': 'Senator Smith takes bribes from donors.'},
                    {'common': 'x', 'note': 'Politicians take bribes from wealthy donors.'}])
    monkeypatch.setattr(mi.llm, 'complete_json', lambda *a, **k: next(answers))
    entry = {'id': 'M1', 'name': 'Political bribes', 'claims': [{'claim': 'a'}]}
    assert mi.gloss(entry) == 'Politicians take bribes from wealthy donors.'
    # A named narrative keeps its own names; a note about the task itself is never kept
    answers = iter([{'common': 'x', 'note': 'The user wants a scope note.'}, {'common': 'x', 'note': 'Texas turns blue and'},
                    {'common': 'x', 'note': 'Texas turns blue.'}])
    assert mi.gloss({'id': 'M2', 'name': 'Blue Texas', 'claims': [{'claim': 'b'}]}) == 'Texas turns blue.'


def test_a_person_can_say_a_claim_tells_no_story(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 3, 'claims': {mi.key('a'): ['M001', 'M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Blame shifting', 'curated': True, 'claims': [{'claim': 'a', 'source': 'x'}]},
        'M002': {'id': 'M002', 'name': 'model made', 'claims': [{'claim': 'a', 'source': 'x'}, {'claim': 'b', 'source': 'x'}]}}})
    mi.no_motif('a')
    index = mi.load()
    assert index['claims'][mi.key('a')] == [] and index['entries']['M001']['claims'] == []  # a person's motif stays
    assert [c['claim'] for c in index['entries']['M002']['claims']] == ['b']
    assert mi.key('a') in index['entries']['M002']['not_claims']


def test_the_model_may_file_a_claim_under_no_motif(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(mi, 'closest', lambda index, claim: [])
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: {'motifs': []})  # a plain report: no story
    index = mi.file_claims([{'claim': 'The Senate passed the budget on Tuesday.', 'source': 'narrative'}])
    assert index['claims'][mi.key('The Senate passed the budget on Tuesday.')] == [] and mi.live(index) == []


def test_a_claim_its_source_took_back_leaves_the_index(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001', 'M002'], mi.key('b'): ['M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Blame shifting', 'curated': True, 'claims': [{'claim': 'a', 'source': 'x'}],
                 'done': [mi.key('a')]},
        'M002': {'id': 'M002', 'name': 'model made', 'claims': [{'claim': 'a', 'source': 'x'}, {'claim': 'b', 'source': 'x'}]},
        'M003': {'id': 'M003', 'name': 'only a', 'claims': [{'claim': 'a', 'source': 'x'}]}}})
    mi.save(dict(mi.load(), claims={mi.key('a'): ['M001', 'M002', 'M003'], mi.key('b'): ['M002']}))
    assert mi.withdraw('a') == ['M001', 'M002', 'M003']
    index = mi.load()
    assert mi.key('a') not in index['claims']
    assert index['entries']['M001']['claims'] == [] and index['entries']['M001']['done'] == []  # a person's motif stays
    assert [c['claim'] for c in index['entries']['M002']['claims']] == ['b']
    assert 'M003' not in index['entries']  # a model's motif left empty goes


def test_only_motifs_a_person_verified_reach_the_site_with_the_claims_they_saw():
    a, b = {'claim': 'a'}, {'claim': 'b'}
    assert not mi.public({'id': 'M1', 'claims': [a]})  # the model's, unchecked
    verified = {'id': 'M2', 'claims': [a, b], 'done': [mi.key('a')]}  # marked done, then b came in
    assert mi.public(verified) and mi.public_claims(verified) == [a]
    assert not mi.public({**verified, 'merged_into': 'M3'})


def test_two_claims_told_two_ways_fold_into_one(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    keep, other = 'Billionaires should pay more taxes', 'The very rich should pay their fair share'
    mi.save({'next': 3, 'claims': {mi.key(keep): ['M001'], mi.key(other): ['M001', 'M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Tax the rich', 'claims': [{'claim': keep, 'source': 'narrative'},
                                                                  {'claim': other, 'source': 'Snopes', 'ref': 'u'}],
                 'done': [mi.key(keep), mi.key(other)]},
        'M002': {'id': 'M002', 'name': 'Class conflict', 'claims': [{'claim': other, 'source': 'Snopes', 'ref': 'u'}]}}})
    mi.same_claim(other, keep)
    index = mi.load()
    assert mi.key(other) not in index['claims'] and index['claims'][mi.key(keep)] == ['M001', 'M002']
    for eid in ('M001', 'M002'):
        [rec] = index['entries'][eid]['claims']
        assert rec['claim'] == keep and rec['variants'] == [{'claim': other, 'source': 'Snopes', 'ref': 'u'}]
    assert index['entries']['M001']['done'] == [mi.key(keep)]
    assert mi.corrected(other, index) == keep  # told again in the same words: filed as the kept claim
    # A claim not filed yet can be filed with a claim
    mi.same_claim('Make billionaires pay', keep)
    assert [v['claim'] for v in mi.load()['entries']['M002']['claims'][0]['variants']] == [other, 'Make billionaires pay']
    with pytest.raises(ValueError):
        mi.same_claim(keep, keep)


def test_a_motif_has_a_genre_from_a_list_a_person_can_grow(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'Elite cabal', 'claims': []}}})
    mi.set_facet('M001', 'genre', 'conspiracy theory')
    mi.add_facet_value('genre', 'origin myth')
    assert mi.load()['entries']['M001']['facets'] == {'genre': 'conspiracy theory'}
    assert 'origin myth' in mi.facet_values()['genre'] and mi.board()['entries'][0]['facets']['genre'] == 'conspiracy theory'
    mi.set_facet('M001', 'genre', None)
    assert 'facets' not in mi.load()['entries']['M001']
    with pytest.raises(ValueError):
        mi.set_facet('M001', 'color', 'blue')


def test_claims_like_a_claim_leave_out_its_own_wordings(monkeypatch, tmp_path):
    import numpy as np
    from app import narratives
    fresh(monkeypatch, tmp_path)
    keep, told, near, far = 'Politicians lie to voters', 'Politicians always lie', 'Politicians say what you want', 'Cats are cute'
    mi.save({'next': 2, 'claims': {mi.key(keep): ['M001'], mi.key(near): ['M001'], mi.key(far): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Empty promises', 'claims': [
            {'claim': keep, 'variants': [{'claim': told}]}, {'claim': near}, {'claim': far}]}}})
    vec = {keep: [1, 0], told: [1, 0], near: [0.9, 0.44], far: [0, 1]}
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array([vec.get(t, [0, 1]) for t in texts], dtype=float))
    monkeypatch.setattr(mi, 'searchable_claims', lambda: [{'claim': t, 'source': '', 'ref': '', 'motifs': []} for t in (told, near, far)])
    found = mi.similar_claims(keep)
    assert [c['claim'] for c in found] == [near, far] and found[0]['score'] > 0.8


def test_a_claim_a_person_files_is_already_checked(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'one', 'claims': [{'claim': 'a', 'source': 'x'}]},
        'M002': {'id': 'M002', 'name': 'two', 'claims': []}, 'M003': {'id': 'M003', 'name': 'three', 'claims': []}}})
    mi.also_file('a', 'M001', 'M002')
    mi.move('a', 'M001', 'M003')
    mi.file_by_hand({'claim': 'b', 'source': 'y'}, 'M002')
    entries = mi.load()['entries']
    assert [c.get('checked') for c in entries['M002']['claims']] == ['yes', 'yes']
    assert entries['M003']['claims'][0]['checked'] == 'yes'


def test_metrics_say_how_the_catalog_is_shaped_and_keep_a_day_by_day_history(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(mi, 'METRICS', str(tmp_path / 'metrics.json'))
    monkeypatch.setattr(mi, 'FILING_LOG', str(tmp_path / 'filing.jsonl'))
    monkeypatch.setattr(mi.Config, 'data', str(tmp_path))
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001', 'M002'], mi.key('b'): ['M002'], mi.key('c'): []}, 'entries': {
        'M001': {'id': 'M001', 'name': 'one', 'first_seen': '2026-10-05', 'claims': [{'claim': 'a', 'checked': 'yes'}],
                 'facets': {'genre': 'rumor'}, 'done': [mi.key('a')]},
        'M002': {'id': 'M002', 'name': 'two', 'first_seen': '2026-10-06', 'claims': [{'claim': 'a'}, {'claim': 'b'}],
                 'parents': ['M001']}}})
    m = mi.metrics()
    assert (m['motifs'], m['claims'], m['filings'], m['no_motif']) == (2, 2, 3, 1)
    assert (m['singles'], m['two_plus'], m['in_tree'], m['with_genre'], m['done']) == (50.0, 50.0, 100.0, 50.0, 50.0)
    mi.snapshot_metrics()
    with open(mi.FILING_LOG, 'w') as f:
        f.write('{"at": "2026-10-06T04:00:00", "matched": 3, "new": 1}\n')
    days = {d['day']: d for d in mi.metrics_history()['days']}
    assert days['2026-10-05']['new_motifs'] == 1 and days['2026-10-06']['filed_matched'] == 3


def test_a_new_motif_gets_the_models_note_genre_and_groups_as_drafts(monkeypatch, tmp_path):
    from app.analysis import motif_proposals as mp
    fresh(monkeypatch, tmp_path)
    c = lambda t: {'claim': t, 'source': 'narrative'}  # noqa: E731
    mine = {f'M{i:03d}': {'id': f'M{i:03d}', 'name': f'Mine {i}', 'curated': True, 'done': [], 'groups': ['G01'],
                          'facets': {'genre': 'Plots' if i % 2 else 'Theories'}, 'claims': [c(f'claim {i}')]}
            for i in range(1, 5)}
    new = {'id': 'M009', 'name': 'Tax cut for the few', 'curated': False, 'claims': [c('The cut helps only the rich')]}
    mi.save({'next': 10, 'claims': {}, 'groups': {'G01': {'name': 'Who rules'}}, 'entries': {**mine, 'M009': new}})
    monkeypatch.setattr(mi, 'gloss', lambda e: 'A party cuts a tax that only the wealthy pay.')
    asked = {}
    monkeypatch.setattr(mp, 'ask_genre', lambda e, ex, notes=None: asked.setdefault('genre', (e['note'], sorted(ex))) and ('Plots', 'why'))
    monkeypatch.setattr(mp, 'ask_groups', lambda e, ix: ['G01'])
    assert mi.draft_missing() == 1
    e = mi.load()['entries']['M009']
    assert asked['genre'] == ('A party cuts a tax that only the wealthy pay.', ['Plots', 'Theories'])  # asked with the note
    assert (e['note_by'], mi.genre_of(e), mi.groups_of(e)) == ('model', 'Plots', ['G01'])
    assert e['by_model'] == {'genre': 'Plots', 'groups': ['G01']}
    assert mi.person_genre(e) is None and mi.person_groups(e) == []  # nothing learns from them yet
    assert mi.draft_missing() == 0  # drafted once
    assert [x['id'] for x in mp.genre_examples(mi.load())['Plots']] == ['M001', 'M003']  # the person's own only
    mi.set_facet('M009', 'genre', 'Plots')  # picked by hand: theirs now
    e = mi.load()['entries']['M009']
    assert mi.person_genre(e) == 'Plots' and e['by_model'] == {'groups': ['G01']}
    mi.mark_done('M009')  # looked over: all of it theirs
    e = mi.load()['entries']['M009']
    assert 'by_model' not in e and mi.person_groups(e) == ['G01']


def test_the_models_drafts_stay_behind_in_a_merge_and_go_with_a_group_change(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    mi.save({'next': 3, 'claims': {}, 'groups': {'G01': {'name': 'A'}, 'G02': {'name': 'B'}}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Kept', 'curated': True, 'claims': [{'claim': 'one', 'source': 'narrative'}]},
        'M002': {'id': 'M002', 'name': 'Made', 'curated': False, 'claims': [{'claim': 'two', 'source': 'narrative'}],
                 'groups': ['G01', 'G02'], 'facets': {'genre': 'Plots'}, 'by_model': {'genre': 'Plots', 'groups': ['G01', 'G02']}}}})
    mi.group_member('M002', 'G02', True)  # put in by hand: that one's theirs
    assert mi.load()['entries']['M002']['by_model'] == {'genre': 'Plots', 'groups': ['G01']}
    mi.merge('M002', 'M001')
    e = mi.load()['entries']['M001']
    assert mi.groups_of(e) == ['G02'] and mi.genre_of(e) is None


def test_a_deleted_motif_takes_its_links_with_it(monkeypatch, tmp_path):
    """Oct 9: three motifs still rested on a deleted M402, and the checker couldn't take them off"""
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 4, 'claims': {}, 'related': [['M001', 'M003']], 'entries': {
        'M001': {'id': 'M001', 'name': 'Horserace', 'claims': [claim('a')]},
        'M002': {'id': 'M002', 'name': 'Exploring a run', 'parents': ['M001'], 'claims': [claim('b')]},
        'M003': {'id': 'M003', 'name': 'Polls are inaccurate', 'claims': [claim('c')]}}})
    mi.delete('M001')
    index = mi.load()
    assert index['entries']['M002']['parents'] == [] and index['related'] == []


def test_model_days_keep_each_days_last_test(tmp_path, monkeypatch):
    from app.analysis import filing_confidence as fc
    from app.analysis import motif_index as mi
    path = tmp_path / 'model_history.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in [
        {'at': '2026-10-09T08:00:00', 'model': 'confidence', 'auc': 0.89, 'sure_at': 0.85},
        {'at': '2026-10-09T23:00:00', 'model': 'confidence', 'auc': 0.895, 'sure_at': 0.85, 'right_when_sure': 0.953},
        {'at': '2026-10-10T11:00:00', 'model': 'shortlist', 'top12': 0.88}]) + '\n')
    monkeypatch.setattr(fc, 'HISTORY', str(path))
    days = mi.model_days()
    assert days == [{'day': '2026-10-09', 'auc': 0.895, 'sure_at': 0.85, 'right_when_sure': 0.953},
                    {'day': '2026-10-10', 'top12': 0.88}]


def test_seeds_reach_the_shortlist_by_name_and_note(monkeypatch):
    from app.analysis import motif_retriever as mr
    index = {'entries': {
        'M1': {'id': 'M1', 'name': 'Weather', 'note': 'talk of the weather', 'claims': [], 'done': '2026-10-09'},
        'M2': {'id': 'M2', 'name': 'Birds', 'note': 'birds', 'claims': [], 'done': '2026-10-09'},
        'M3': {'id': 'M3', 'name': 'Graft', 'note': 'x', 'claims': [{'claim': 'a deal'}], 'done': '2026-10-09'},
        'M4': {'id': 'M4', 'name': 'Drafted', 'note': 'the model made it', 'claims': []}},  # not the person's: not a seed
        'claims': {}}
    vecs = {'Weather (talk of the weather)': [1.0, 0.0], 'Birds (birds)': [0.0, 1.0], 'it rained all day': [0.9, 0.1]}
    monkeypatch.setattr(mi, 'described', lambda e: f"{e['name']} ({e['note']})")
    vec = lambda texts: np.array([vecs.get(t, [0.0, 0.0]) for t in texts])  # noqa: E731
    got = [e['id'] for e in mr.seeds(index, 'it rained all day', vec)]
    assert got == ['M1']  # Birds is too unlike (0.1, under the floor); Graft has claims; Drafted isn't a seed


def test_a_filing_keeps_the_story_its_claim_was_told_about(monkeypatch, tmp_path):
    """Oct 12: 'which motifs is story S told in, in time order' is a join on the filings"""
    fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(mi, 'closest', lambda index, claim: [])
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: {'motifs': ['Rigged count']})
    index = mi.file_claims([{'claim': 'The count was rigged in Maricopa', 'source': 'narrative', 'story': 41,
                             'story_tie': 'same event', 'date': '2026-10-10'},
                            {'claim': 'They rigged it again', 'source': 'shows', 'date': '2026-10-11'}])
    recs = {c['claim']: c for e in mi.live(index) for c in e['claims']}
    assert recs['The count was rigged in Maricopa']['story'] == 41
    assert recs['The count was rigged in Maricopa']['story_tie'] == 'same event'
    assert 'story' not in recs['They rigged it again']  # a show's claim has none
    assert mi.story_of_group({'story': {'label': 'x', 'relation': 'same issue', 'id': 9}}) == {'story': 9, 'story_tie': 'same issue'}
    assert mi.story_of_group({'story': {'label': 'x', 'relation': 'same issue', 'id': None}}) == {}
    assert mi.story_of_group({}) == {}


def test_a_story_lists_its_motifs_in_time_order_through_merges(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    from app.analysis import stories, watch_list
    monkeypatch.setattr(stories, 'merges', lambda: {7: 5})  # story 7 was folded into 5
    monkeypatch.setattr(watch_list, 'STORE', str(tmp_path / 'watch.json'))
    mi.save({'next': 3, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Straight news', 'claims': [
            {'claim': 'Polls closed at eight', 'source': 'narrative', 'date': '2026-10-01', 'story': 5}]},
        'M003': {'id': 'M003', 'name': 'Another sink', 'claims': []},
        'M002': {'id': 'M002', 'name': 'Rigged count', 'claims': [
            {'claim': 'The count was rigged', 'source': 'narrative', 'date': '2026-10-03', 'story': 7, 'checked': 'yes'},
            {'claim': 'Another story', 'source': 'narrative', 'date': '2026-10-02', 'story': 6}]}}})
    assert [r['plain'] for r in mi.story_motifs(5)] == [False, False]  # no motif is watched yet
    mi.set_watch('M001')  # the person marks Straight news as a watch list: its claims are the plain report
    mi.set_watch('M003')
    mi.set_watch('M003', on=False)
    assert mi.watched(mi.load()) == {'M001'}
    rows = mi.story_motifs(5)
    assert [(r['date'], r['motif'], r['plain']) for r in rows] == [('2026-10-01', 'M001', True), ('2026-10-03', 'M002', False)]
    assert mi.story_motifs(7) == rows  # asked by the gone id: the same story


def test_older_filings_get_their_story_from_the_report_they_came_in(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    from app import narratives
    from app.analysis import factchecks
    monkeypatch.setattr(narratives, 'FOLDER', str(tmp_path))
    (tmp_path / 'report-2026-10-05-0817.json').write_text(json.dumps({'made': '2026-10-05T08:17', 'found': [
        {'label': {'narrative': 'The count was rigged'}, 'story': {'label': 'x', 'relation': 'same event', 'id': 12}},
        {'label': {'narrative': 'No story here'}, 'story': None}]}))
    monkeypatch.setattr(factchecks, 'stories_of', lambda: {'https://check/1': 30})
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'x', 'claims': [
        {'claim': 'The count was rigged', 'source': 'narrative', 'ref': '2026-10-05T08:17'},
        {'claim': 'No story here', 'source': 'narrative', 'ref': '2026-10-05T08:17'},
        {'claim': 'A checked rumor', 'source': 'Snopes', 'ref': 'https://check/1'},
        {'claim': 'Kept as it was', 'source': 'Snopes', 'ref': 'https://check/1', 'story': 2}]}}})
    assert mi.backfill_stories() == {'narrative': 1, 'fact-check': 1}
    recs = {c['claim']: c for c in mi.load()['entries']['M001']['claims']}
    assert (recs['The count was rigged']['story'], recs['The count was rigged']['story_tie']) == (12, 'same event')
    assert 'story' not in recs['No story here'] and recs['A checked rumor']['story'] == 30
    assert recs['Kept as it was']['story'] == 2  # never changed


def test_a_hand_filing_and_a_fold_keep_the_claims_story(monkeypatch, tmp_path):
    fresh(monkeypatch, tmp_path)
    c = {'claim': 'the mayor took bribes', 'source': 'narrative', 'ref': '2026-10-05T08:17', 'story': 7,
         'story_tie': 'same event', 'checked': 'yes'}
    mi.save({'next': 3, 'claims': {mi.key(c['claim']): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Graft', 'claims': [c]},
        'M002': {'id': 'M002', 'name': 'Cover-up', 'claims': []}}})
    mi.file_by_hand({'claim': 'the mayor took bribes', 'source': 'narrative', 'ref': '2026-10-05T08:17'}, 'M002')
    assert mi.load()['entries']['M002']['claims'][0]['story'] == 7  # from its other filing
    mi.file_by_hand({'claim': 'a new one', 'source': 'Snopes', 'ref': 'x', 'story': 9}, 'M002')
    assert mi.load()['entries']['M002']['claims'][-1]['story'] == 9  # from the claim given
    index = mi.load()  # a kept claim with no story takes its variant's when they're folded
    index['entries']['M002']['claims'].append({'claim': 'bribes for the mayor', 'source': 'narrative', 'checked': 'yes'})
    index['claims'][mi.key('bribes for the mayor')] = ['M002']
    mi.save(index)
    mi.same_claim('a new one', 'bribes for the mayor')
    kept = next(x for x in mi.load()['entries']['M002']['claims'] if x['claim'] == 'bribes for the mayor')
    assert kept['story'] == 9 and kept['variants'][0]['story'] == 9


def test_carrying_words_are_kept_per_filing_and_gathered_per_motif(monkeypatch, tmp_path):
    """The tellers' own words (Oct 13): a person's, on one filing; the motif's phrase dictionary counts them"""
    fresh(monkeypatch, tmp_path)
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    mi.save({'next': 2, 'claims': {mi.key(t): ['M001'] for t in ('a', 'b')},
             'entries': {'M001': {'id': 'M001', 'name': 'x', 'claims': [claim('a'), claim('b')]}}})
    mi.set_carrying('a', 'M001', ' “Religion of  peace”; mostly peaceful ;')
    mi.set_carrying('b', 'M001', ['religion of peace'])
    e = mi.load()['entries']['M001']
    assert e['claims'][0]['carrying'] == ['Religion of peace', 'mostly peaceful']
    assert mi.carrying(e) == [('Religion of peace', 2), ('mostly peaceful', 1)]
    assert next(c for c in mi.board()['entries'][0]['claims'] if c['claim'] == 'a')['carrying'][0] == 'Religion of peace'
    mi.set_carrying('a', 'M001', '')
    assert 'carrying' not in mi.load()['entries']['M001']['claims'][0]


def test_a_filing_record_keeps_the_telling_a_child_claim_was_split_from():
    rec = mi.record({'claim': 'a child', 'source': 'narrative', 'ref': 'r', 'story': 4, 'split_from': 'the telling'},
                    '2026-10-13')
    assert rec['split_from'] == 'the telling' and rec['story'] == 4
    assert 'split_from' not in mi.record({'claim': 'plain'}, '2026-10-13')
