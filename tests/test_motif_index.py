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
        assert model == mi.MODEL  # the bigger model does the hard calls
        claim = prompt.splitlines()[1]  # the claim's own line: the shown motifs' example claims come later
        name = next(v for k, v in names.items() if k in claim)
        if 'motifs' in schema['properties']:  # the first claim, with nothing in the index to show
            return {'motifs': [name + '.']}
        if 'existing' in schema['properties']:  # named with the closest motifs shown: reuse one that fits
            shown = [line.split('. ', 1)[1].split(' (e.g.')[0] for line in prompt.splitlines() if line[:1].isdigit()]
            return {'reason': '', 'existing': [str(shown.index(name) + 1)] if name in shown else [], 'new': [] if name in shown else [name]}
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
    assert all(q in ('a claim that', 'is accused of') for q in quoted), quoted  # even a template got copied ("X is Y")


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
                        else {'reason': '', 'existing': [], 'new': ['Blame-shifting.']} if 'existing' in schema['properties']
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
    mi.check('a', 'M001', 'no')  # its last motif: filed again next run, but never under M001
    index = mi.load()
    assert mi.key('a') not in index['claims'] and mi.key('a') in index['entries']['M001']['not_claims']
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
    answers = iter([{'common': 'x', 'note': 'The user wants a scope note.'}, {'common': 'x', 'note': 'Texas turns blue.'}])
    assert mi.gloss({'id': 'M2', 'name': 'Blue Texas', 'claims': [{'claim': 'b'}]}) == 'Texas turns blue.'
