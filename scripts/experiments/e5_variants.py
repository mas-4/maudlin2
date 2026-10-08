"""E5 variants: which links carry it (rests-on, related), max or mean of the neighbours, one or two hops; and a leak
check: only links whose motifs both existed before the claim was filed under any of them (dates in the index)"""
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from e3_e5_bundles_graph import data, ids, at, index, mi  # noqa: E402

rests, related = defaultdict(set), defaultdict(set)
for e in data['entries'].values():
    for p in mi.parents_of(e):
        rests[e['id']].add(p)
        rests[p].add(e['id'])
for a, b in index.get('related', []):
    related[a].add(b)
    related[b].add(a)
both = defaultdict(set)
for g in (rests, related):
    for m, ns in g.items():
        both[m] |= ns


def spread(neighbours, how='max', hops=1):
    def fn(d, k):
        s = d['claims'][k]['signals']['today']
        z = (s - s.mean()) / (s.std() + 1e-9)
        out = np.full(len(ids), -3.0)
        for m in ids:
            ns = set(neighbours.get(m, ()))
            if hops == 2:
                ns |= {x for n in list(ns) for x in neighbours.get(n, ())} - {m}
            vals = [z[at[n]] for n in ns if n in at]
            if vals:
                out[at[m]] = max(vals) if how == 'max' else float(np.mean(vals))
        return out
    return fn


# leak check: drop a link for claim k when the claim was filed in both of its motifs (the link might have come from it)
def spread_no_shared(neighbours):
    def fn(d, k):
        s = d['claims'][k]['signals']['today']
        z = (s - s.mean()) / (s.std() + 1e-9)
        mine = d['claims'][k]['truth']
        out = np.full(len(ids), -3.0)
        for m in ids:
            vals = [z[at[n]] for n in neighbours.get(m, ()) if n in at and not (m in mine and n in mine)]
            if vals:
                out[at[m]] = max(vals)
        return out
    return fn


if __name__ == '__main__':
    for label, ex in [('rests-on only', spread(rests)), ('related only', spread(related)), ('both, mean', spread(both, 'mean')),
                      ('both, two hops', spread(both, hops=2)), ('both, max (E5)', spread(both)),
                      ('LEAK CHECK: both, ignoring links between two of the claim\'s own motifs', spread_no_shared(both))]:
        harness.evaluate(data, {'x': ex}, label=label)
    print('DONE', flush=True)
