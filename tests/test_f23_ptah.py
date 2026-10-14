"""scripts/experiments/f23_ptah.py (Ptah, Oct 14): the note-first prompts differ from production's only in the order of
the name and the note, and the measures' small pieces."""
import sys

import numpy as np
import pytest

sys.path.insert(0, 'scripts/experiments')
try:
    import f23_ptah as f  # noqa: E402
except ValueError:  # production's prompts have changed since the experiment: its arms no longer apply
    pytest.skip("the production prompts Ptah rewrites have changed", allow_module_level=True)


def test_the_note_first_proposer_asks_for_the_note_before_the_name_and_nothing_else_moves():
    base, _ = f.PROPOSER['name, then note']
    new, note_first = f.PROPOSER['note, then name']
    assert note_first and new != base
    fields = new[new.index('\nreason:'):]
    assert fields.index('\nnote:') < fields.index('\nname:') < fields.index('\ngenre:')
    assert new.index('first write its scope note') < new.index('then name the motif that note describes {rules}')
    for keep in ('{claims}', '{near}', '{genres}', 'Read them as a folklorist would', 'claims: the numbers'):
        assert keep in new


def test_the_note_first_filing_prompt_adds_a_note_before_the_name():
    new, _ = f.FILING['filing: note, then name']
    fields = new[new.index('\nreason:'):]
    assert fields.index('\nnote:') < fields.index('\nnew:')
    assert '{rules}' in new and '{closest}' in new and "don't force one" in new


def test_the_schemas_put_the_fields_in_the_order_asked():
    assert list(f.proposer_schema(3, False)['properties']) == ['reason', 'new', 'name', 'note', 'genre', 'claims']
    assert list(f.proposer_schema(3, True)['properties']) == ['reason', 'new', 'note', 'name', 'genre', 'claims']
    assert list(f.filing_schema(False)['properties']) == ['reason', 'new']
    assert list(f.filing_schema(True)['properties']) == ['reason', 'note', 'new']
    assert f.expected('note, then name') == ['reason', 'new', 'note', 'name', 'genre', 'claims']


def test_a_passage_production_no_longer_has_is_an_error():
    with pytest.raises(ValueError):
        f.swapped('a prompt with none of it', f.PROPOSER_SWAPS)


def test_names_match_without_case_punctuation_or_a_leading_the():
    assert f.norm('The Stranger in the arena.') == f.norm('stranger in the arena')
    assert f.norm("Who's laughing now?") == 'who s laughing now'
    assert f.norm('Theatre') == 'theatre'


def test_the_paired_gain_and_its_interval():
    a, b = np.zeros(50), np.ones(50)
    assert f.paired(a, b) == (1.0, 1.0, 1.0)
    d, lo, hi = f.paired(np.zeros(200), np.r_[np.ones(100), np.zeros(100)])
    assert d == 0.5 and lo < 0.5 < hi


def test_a_proposal_is_made_as_production_makes_it():
    assert f.proposed({'new': True, 'name': 'Petty tyrant', 'claims': [1, 2]}, 3)
    assert not f.proposed({'new': True, 'name': 'Petty tyrant', 'claims': [1]}, 3)
    assert f.proposed({'new': True, 'name': 'Petty tyrant', 'claims': [1]}, 1)  # a case of one claim
    assert not f.proposed({'new': False, 'name': 'Petty tyrant', 'claims': [1, 2]}, 3)
    assert not f.proposed({'new': True, 'name': '', 'claims': [1, 2]}, 3)


def test_the_blind_set_is_the_same_every_time_and_only_where_the_names_differ():
    a, b = f.PROPOSER
    cases = {f'R:{i}': {'answer': {'name': 'x', 'note': ''}, 'source': 'renamed'} for i in range(30)}
    answers = {a: {k: {'name': f'name {k}'} for k in cases}, b: {k: {'name': f'other {k}'} for k in cases}}
    answers[b]['R:0'] = {'name': 'The name R:0'}  # the same name both ways: nothing to choose between
    state = {'cases': cases, 'answers': answers}
    one, two = f.blind_pairs(state), f.blind_pairs(state)
    assert one == two and len(one) == f.BLIND
    assert 'R:0' not in {p['case'] for p in one}
    assert {p['first'] for p in one} == {a, b}
