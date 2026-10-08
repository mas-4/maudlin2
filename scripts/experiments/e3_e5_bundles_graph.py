"""E3 motifs travel in bundles, E5 spread over the person's links (docs/filing-experiments.md). No model asked: runs
on the harness's cached signals.

E3: the person's filings counted in pairs (how often motif b is filed with motif a), leaving the claim being scored out
of the counts; a claim's anchors are its top 3 motifs by today's shortlist (what the filing model would most likely
file first); each other motif scored by P(b | anchor), summed over the anchors.
E5: each motif scored by its best neighbour's (today's score, standardized per claim) through rests-on and related
links, and separately through the person's groups."""
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402

data = harness.load()
ids, at = data['ids'], data['at']
truths = {k: c['truth'] for k, c in data['claims'].items()}
pair, single = Counter(), Counter()
for t in truths.values():
    for a in t:
        single[a] += 1
        for b in t:
            if a != b:
                pair[(a, b)] += 1


def anchors(k, n=3):
    s = data['claims'][k]['signals']['today']
    return [ids[i] for i in np.argsort(-s)[:n]]


def bundles(d, k):
    own = truths[k]
    out = np.zeros(len(ids))
    for a in anchors(k):
        na = single[a] - (a in own)
        if na <= 0:
            continue
        for b in ids:
            if b == a:
                continue
            c = pair[(a, b)] - (a in own and b in own)
            if c > 0:
                out[at[b]] += c / (na + 1)
    return out


index = mi.load()
links = defaultdict(set)
for e in data['entries'].values():
    for p in mi.parents_of(e):
        links[e['id']].add(p)
        links[p].add(e['id'])
for a, b in index.get('related', []):
    links[a].add(b)
    links[b].add(a)
groups = defaultdict(set)
for e in data['entries'].values():
    for g in mi.groups_of(e):
        groups[g].add(e['id'])
group_mates = defaultdict(set)
for members in groups.values():
    for m in members:
        group_mates[m] |= members - {m}


def spread(neighbours):
    def fn(d, k):
        s = d['claims'][k]['signals']['today']
        z = (s - s.mean()) / (s.std() + 1e-9)
        return np.array([max((z[at[n]] for n in neighbours.get(m, ()) if n in at), default=-3.0) for m in ids])
    return fn


if __name__ == '__main__':
    results = [harness.evaluate(data, {'bundles': bundles}, label='E3 bundles'),
               harness.evaluate(data, {'links': spread(links)}, label='E5 links (rests-on, related)'),
               harness.evaluate(data, {'groups': spread(group_mates)}, label='E5 group mates'),
               harness.evaluate(data, {'bundles': bundles, 'links': spread(links), 'groups': spread(group_mates)},
                                label='E3+E5 together')]
    print('DONE', flush=True)
