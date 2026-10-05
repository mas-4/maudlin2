import numpy as np

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
        if 'motifs' in schema['properties']:
            return {'motifs': [next(v for k, v in names.items() if k in prompt) + '.']}
        return {'reason': '', 'pick': '1'}  # same as the closest entry, when one is offered

    monkeypatch.setattr(llm, 'complete_json', complete_json)
    from app import narratives
    vec = {'the ruler is senile': [1, 0], 'the realignment that keeps not coming': [0, 1]}
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array([vec[t.split('.')[0]] for t in texts], float))
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
