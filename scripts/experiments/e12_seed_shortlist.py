"""E12 the shortlist and seed motifs (Oct 11, from A1: on folktales, over ATU types with no tales filed yet, the
shortlist's weights put the right type in the top 8 for 34% of tales against plain likeness's 64%). Do our own seeds
(motifs made with a name and note and no claims, so the filing can find them) start buried the same way?

For each claim the person confirmed (in their done motifs), its motif emptied of every claim (and the phrases drawn from
them), as a seed would be, every other motif as it is; where does the motif land in the claim's shortlist?
    as it is     the motif with its other claims (the claim itself left out): the usual case
    weights      the production shortlist's weights (motif_retriever.weights, FACTS) on the seed
    plain        plain likeness to the motif's text or name, the better of the two
    filled in    the weights, a motif with no claims given its name's likeness where its claims' would be (near,
                 center), so it isn't scored as if no claim were like the claim (the fix to try)
Recall at 8, 12 and 40. Under the GPU lease (the seeds' texts are embedded anew).

    e12_seed_shortlist.py [n claims, default all]"""
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'e12_seed_shortlist.json')
KS = (8, 12, 40)
NAME, NEAR, CENTER, SIZE = (mr.FACTS.index(f) for f in ('name and note', 'nearest claim', 'center of claims', 'size'))


def main():
    index = mi.load()
    entries = mi.live(index)
    at = {e['id']: n for n, e in enumerate(entries)}
    w = mr.weights()
    weights, bias = np.array([w['weights'][f] for f in mr.FACTS]), w['bias']
    pairs = [(c['claim'], e['id']) for e in entries if e.get('done') for c in e['claims'] if c.get('checked') == 'yes']
    random.Random(12).shuffle(pairs)
    if len(sys.argv) > 1:
        pairs = pairs[:int(sys.argv[1])]
    vec = mr.Vectors()
    ranks = {arm: [] for arm in ('as it is', 'weights', 'plain', 'filled in')}
    for i, (claim, eid) in enumerate(pairs):
        n = at[eid]
        as_is = mr.facts(entries, claim, vec, leave_out=True)
        seed = dict(entries[n], claims=[], phrases=[])
        F = as_is.copy()
        F[n] = mr.facts([seed], claim, vec)[0]  # the motif as a seed; the others as they are
        scores = {'as it is': as_is @ weights + bias, 'weights': F @ weights + bias, 'plain': F[:, :2].max(1)}
        G = F.copy()
        empty = G[:, SIZE] == 0
        G[empty, NEAR] = G[empty, NAME]
        G[empty, CENTER] = G[empty, NAME]
        scores['filled in'] = G @ weights + bias
        for arm, s in scores.items():
            ranks[arm].append(int((s > s[n]).sum()))
        if i % 100 == 0:
            print(f'{i}/{len(pairs)}', flush=True)
    out = {arm: {K: round(float(np.mean(np.array(r) < K)), 3) for K in KS} for arm, r in ranks.items()}
    json.dump({'pairs': len(pairs), 'recall': out}, open(OUT, 'w'), indent=1)
    line = (f'E12 seeds in the shortlist, {len(pairs)} confirmed filings, the motif emptied of its claims; right motif in '
            f'the top 8/12/40: ' + '; '.join(f"{arm} {r[8]:.0%}/{r[12]:.0%}/{r[40]:.0%}" for arm, r in out.items()))
    print(line, flush=True)
    harness.note(line)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
