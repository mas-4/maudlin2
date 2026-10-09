import numpy as np

from app.analysis import claim_map
from app.analysis import motif_index as mi


def test_motifs_cluster_by_their_claims_alone(monkeypatch, tmp_path):
    """Two pairs of motifs whose claims read alike, one pair also sharing a claim: two clusters, whatever the groups"""
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    claim = lambda t: {'claim': t, 'source': 's'}  # noqa: E731
    entries = {'M001': {'id': 'M001', 'name': 'a', 'claims': [claim('x1'), claim('shared')], 'groups': ['G01']},
               'M002': {'id': 'M002', 'name': 'b', 'claims': [claim('x2'), claim('shared')]},
               'M003': {'id': 'M003', 'name': 'c', 'claims': [claim('y1')], 'groups': ['G01']},
               'M004': {'id': 'M004', 'name': 'd', 'claims': [claim('y2')]}}
    vec = {'x1': [1, 0.1], 'x2': [1, 0.15], 'shared': [1, 0], 'y1': [0.1, 1], 'y2': [0.15, 1]}
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.array([vec[t] for t in texts], float))
    m = claim_map.build({'next': 5, 'claims': {}, 'entries': entries, 'groups': {'G01': {'id': 'G01', 'name': 'g'}}})
    assert m['nodes']['M001'] == m['nodes']['M002'] != m['nodes']['M003'] == m['nodes']['M004']
    assert {'source': 'M001', 'target': 'M002', 'kind': 'shared', 'n': 1, 'w': 1} in m['links']
    assert len(m['clusters']) == 2
