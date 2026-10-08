"""Train the many-signal combiner on the person's decisions (with and without their own hand-made filings, judged
only on the model's filings), then keep a fit on every unchecked filing in their motifs"""
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

index = mi.load()
scorer = fc.Scorer(index, mr.weights())
model_pairs = {(mi.key(c), e) for c, e, s, ok in fc.labeled(index)}
pairs = fc.labeled(index, hand=True)
by = defaultdict(list)
for c, e, s, ok in pairs:
    by[(c, s)].append((e, ok))
X, y, g, is_model = [], [], [], []
for i, ((c, s), items) in enumerate(by.items()):
    X.extend(scorer.rows(c, [e for e, _ in items], s))
    y.extend(ok for _, ok in items)
    g.extend([mi.key(c)] * len(items))
    is_model.extend((mi.key(c), e) in model_pairs for e, _ in items)
    if i % 50 == 0:
        scorer.signals.save()
        print(f'features {i}/{len(by)}', flush=True)
scorer.signals.save()
X, y, g, is_model = np.array(X), np.array(y, bool), np.array(g), np.array(is_model)
for label, use in (('model filings only', is_model), ('with hand-made', np.ones(len(y), bool))):
    p = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        tr = tr[use[tr]]
        m, mu, sd = fc._fit(X[tr], y[tr])
        p[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
    yy, pp = y[is_model], p[is_model]
    ok = [t for t in np.linspace(0.5, 0.99, 50) if (pp >= t).sum() >= 20 and yy[pp >= t].mean() >= 0.95]
    t = ok[0] if ok else None  # the lowest line that holds 95% precision on the model's filings
    print(f'{label}: AUC on model filings {roc_auc_score(yy, pp):.3f}; at 95% precision passes '
          f'{(pp[yy] >= t).mean() if t else 0:.0%} of kept (line {t and round(t, 2)})', flush=True)
# Logistic regression vs boosted trees (they learn when to trust which signal), each on a growing share of the
# person's decisions (claims held out by group; scored on the model's own filings): is more data still helping?
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
rng = np.random.default_rng(7)
claims = np.unique(g)


def recall95(yy, pp):
    o = np.argsort(-pp)
    ys = yy[o]
    ok = [k for k in range(20, len(ys) + 1) if ys[:k].mean() >= 0.95]
    return ys[:max(ok)].sum() / yy.sum() if ok else 0.0


for name, make in (('logistic', None),
                   ('boosted trees', lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                                            l2_regularization=1.0, min_samples_leaf=20))):
    for frac in (0.25, 0.5, 0.75, 1.0):
        aucs, recs = [], []
        for rep in range(4):
            perm = rng.permutation(claims)
            test = set(perm[:len(perm) // 5])
            rest = perm[len(perm) // 5:]
            train = set(rest[:int(len(rest) * frac)])
            tr = np.array([c in train for c in g])
            te = np.array([c in test for c in g]) & is_model
            if make is None:
                m_, mu, sd = fc._fit(X[tr], y[tr])
                p_ = m_.predict_proba((X[te] - mu) / sd)[:, 1]
            else:
                p_ = make().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
            aucs.append(roc_auc_score(y[te], p_))
            recs.append(recall95(y[te], p_))
        print(f'{name} on {frac:.0%} ({int(tr.sum())} decisions): AUC {np.mean(aucs):.3f}, '
              f'kept passable at 95% precision {np.mean(recs):.0%}', flush=True)
m = fc.train()
print('trained', m and {k: m['test'][k] for k in ('auc', 'filings', 'kept', 'sure_at')}, flush=True)
print('thresholds', m and m['test']['thresholds'], flush=True)
print('scored', fc.refresh(), flush=True)
print('DONE', flush=True)
