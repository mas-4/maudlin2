"""The reranker on each of the person's decided filings (claim held out of its motif's examples), saved in the
signals' cache; then how well it sorts kept from removed, alone and with the features and Gemma's yes/no"""
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from sklearn.metrics import roc_auc_score  # noqa: E402

from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

S = '/home/mas/maudlin-data/motifs/experiments'
index = mi.load()
sig = ms.Signals(index)
pairs = fc.labeled(index)
by = defaultdict(list)
for c, e, s, ok in pairs:
    by[(c, s)].append((e, ok))
t = time.time()
R = {}
for i, ((c, s), items) in enumerate(by.items()):
    sc = sig.rerank(c, [sig.at[e] for e, _ in items], leave_out=True)
    for (e, _), p in zip(items, sc):
        R[(mi.key(c), e)] = p
    if i % 25 == 0:
        sig.save()
        print(i, len(by), f'{time.time() - t:.0f}s', flush=True)
sig.save()
J = json.load(open(os.path.join(S, 'judge_test.json')))
scorer = fc.Scorer(index, mr.weights(), sig.vec)
X, y, g, P, Q = [], [], [], [], []
for (c, s), items in by.items():
    k = mi.key(c)
    if not all(f'{k}|{e}' in J for e, _ in items):
        continue
    X.extend(scorer.rows(c, [e for e, _ in items], s))
    y.extend(ok for _, ok in items)
    g.extend([k] * len(items))
    P.extend(R[(k, e)] for e, _ in items)
    Q.extend(J[f'{k}|{e}']['p'] for e, _ in items)
X, y = np.array(X), np.array(y, bool)
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))[:, None]  # noqa: E731
P, Q = lg(np.array(P)), lg(np.array(Q))
print('reranker alone AUC', round(roc_auc_score(y, P[:, 0]), 3))
for name, XX in (('features', X), ('features + judge', np.hstack([X, Q])), ('features + reranker', np.hstack([X, P])),
                 ('features + judge + reranker', np.hstack([X, Q, P]))):
    r = fc.evaluate(XX, y, g)
    r.pop('p')
    print(f'{name:28s} AUC {r["auc"]} ', [(x['at'], x['of kept'], x['precision']) for x in r['thresholds'] if x['at'] >= 0.85], flush=True)
