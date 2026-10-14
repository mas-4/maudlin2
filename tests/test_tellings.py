"""app/analysis/tellings.py: a flabby motif's tellings (Pandora's drafts) made motifs of their own, resting on it, the
claims moved there without teaching the confidence model "not this motif"."""
import json

from app.analysis import filing_confidence as fc
from app.analysis import motif_index as mi
from app.analysis import tellings


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(tellings, 'PANDORA', str(tmp_path / 'pandora.json'))
    claims = ['a video shows strikes', 'a video shows a missile', 'a photo shows the crowd']
    mi.save({'next': 5, 'claims': {mi.key(c): ['M001'] for c in claims},
             'entries': {'M001': {'id': 'M001', 'name': 'Caught on camera', 'curated': True,
                                  'claims': [{'claim': c, 'source': 'factcheck', 'fit': 0.4} for c in claims]}}})
    (tmp_path / 'pandora.json').write_text(json.dumps({'verdicts': {}, 'motifs': {'M001': {'name': 'Caught on camera', 'groups': [
        {'name': 'The unseen war', 'note': 'footage of secret strikes', 'claims': claims[:2]},
        {'name': 'Packed rallies', 'note': 'crowds as proof', 'claims': claims[2:]}]}}}))
    return claims


def test_a_telling_made_a_motif_narrows_the_broader_one(monkeypatch, tmp_path):
    claims = setup(monkeypatch, tmp_path)
    assert [t['name'] for m in tellings.drafted() for t in m['tellings']] == ['The unseen war', 'Packed rallies']
    eid = tellings.make('M001', 'The unseen war', claims[:1], 'Footage of secret strikes.', key='M001|The unseen war')
    index = mi.load()
    child, parent = index['entries'][eid], index['entries']['M001']
    assert mi.parents_of(child) == ['M001'] and child['note'] == 'Footage of secret strikes.'
    assert [c['claim'] for c in child['claims']] == claims[:1] and child['claims'][0]['checked'] == 'yes'
    assert claims[0] not in [c['claim'] for c in parent['claims']] and mi.key(claims[0]) not in parent.get('not_claims', [])
    assert index['claims'][mi.key(claims[0])] == [eid]
    assert [t['name'] for m in tellings.drafted() for t in m['tellings']] == ['Packed rallies']  # decided: off the list
    out = {}
    fc._decided({'action': 'telling', 'id': eid, 'parent': 'M001', 'claims': claims[:1]}, out)
    assert out == {}  # no verdict on the broader motif
    fc._decided({'action': 'telling', 'id': eid, 'parent': 'M001', 'claims': claims[:1]}, out, hand=True)
    assert out == {(mi.key(claims[0]), eid): True}


def test_kept_in_both_and_turned_down(monkeypatch, tmp_path):
    claims = setup(monkeypatch, tmp_path)
    eid = tellings.make('M001', 'Packed rallies', claims[2:], move=False)
    assert mi.load()['claims'][mi.key(claims[2])] == ['M001', eid]
    tellings.reject('M001|The unseen war')
    assert json.loads((tmp_path / 'pandora.json').read_text())['verdicts'] == {'M001|The unseen war': 'not'}
