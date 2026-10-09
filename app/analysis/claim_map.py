"""The motif map's 🧲 claims mode (Oct 9, the person: "claim connections between motifs... clustering ignoring the
structure I've put in"). Motifs placed by their claims alone, none of the person's groups, genres, rests-on or related
links: two motifs are drawn together when they hold the same claims (told together, which isn't the same as related)
or when their claims read alike (each motif the mean of its claims' embeddings, the same ones the narratives use; its
NEAREST closest by that, above FLOOR). Clusters are found in that graph alone (Louvain), each named by its motifs with
the most claims. Worked out again when the index changes."""
import os

import numpy as np

from app.analysis import motif_index as mi

NEAREST = 5  # each motif's closest by its claims' meaning
FLOOR = 0.55  # cosine, below which two motifs' claims aren't alike enough to draw
SHARED_WEIGHT = 0.5  # a shared claim's pull, beside a likeness of 0 to 1
_memo = {}


def build(index: dict | None = None) -> dict:
    """{'nodes': {motif id: cluster}, 'links': [{source, target, kind: 'alike'|'shared', w}], 'clusters': [{id, size,
    label, names}]}, for the live motifs with claims"""
    from app.narratives import embed
    index = index if index is not None else mi.load()
    entries = [e for e in mi.live(index) if e['claims']]
    if len(entries) < 2:
        return {'nodes': {}, 'links': [], 'clusters': []}
    claims = sorted({c['claim'] for e in entries for c in e['claims']})
    at = {c: i for i, c in enumerate(claims)}
    V = embed(claims)
    C = np.array([V[[at[c['claim']] for c in e['claims']]].mean(0) for e in entries])
    C /= np.maximum(np.linalg.norm(C, axis=1, keepdims=True), 1e-12)
    S = C @ C.T
    np.fill_diagonal(S, -1)
    links = {}
    for i in range(len(entries)):
        for j in np.argsort(-S[i])[:NEAREST]:
            if S[i, j] >= FLOOR:
                a, b = sorted((entries[i]['id'], entries[int(j)]['id']))
                links[(a, b)] = {'source': a, 'target': b, 'kind': 'alike', 'w': round(float(S[i, j]), 3)}
    holders = {}
    for e in entries:
        for c in e['claims']:
            holders.setdefault(c['claim'], set()).add(e['id'])
    shared = {}
    for ids in holders.values():
        ids = sorted(ids)
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                shared[(ids[x], ids[y])] = shared.get((ids[x], ids[y]), 0) + 1
    out = list(links.values()) + [{'source': a, 'target': b, 'kind': 'shared', 'n': n, 'w': n} for (a, b), n in shared.items()]
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(e['id'] for e in entries)
    for (a, b), l in links.items():
        g.add_edge(a, b, weight=l['w'])
    for (a, b), n in shared.items():
        g.add_edge(a, b, weight=g.get_edge_data(a, b, {'weight': 0})['weight'] + SHARED_WEIGHT * n)
    groups = sorted(nx.community.louvain_communities(g, weight='weight', seed=1), key=len, reverse=True)
    size = {e['id']: len(e['claims']) for e in entries}
    name = {e['id']: e['name'] for e in entries}
    nodes, clusters = {}, []
    for k, members in enumerate(groups):
        top = sorted(members, key=lambda i: -size[i])
        for i in members:
            nodes[i] = k
        clusters.append({'id': k, 'size': len(members), 'label': ' · '.join(name[i] for i in top[:3]),
                         'names': [name[i] for i in top]})
    return {'nodes': nodes, 'links': out, 'clusters': clusters}


def cached() -> dict:
    """build(), again only when the index has changed since"""
    stamp = os.path.getmtime(mi.INDEX) if os.path.exists(mi.INDEX) else 0
    if _memo.get('stamp') != stamp:
        _memo.update(stamp=stamp, map=build())
    return _memo['map']
