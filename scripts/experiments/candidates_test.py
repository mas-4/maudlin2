"""Candidate finders, each alone and together: for every claim the person confirmed in their own (done) motifs, held
out of its motifs, how many of its motifs each finder ranks in its top 8 / 12 / 20 / 40. Signals computed once and
saved (resumable: the shape rewrite asks the filing model once per claim)."""
import os
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

HERE = '/home/mas/maudlin-data/motifs/experiments'
CACHE = os.path.join(HERE, 'candidates-2026-10-08.pkl')
KS = (8, 12, 20, 40)


def collect():
    index = mi.load()
    sig = ms.Signals(index)
    w = mr.weights()
    truth, text = defaultdict(set), {}
    for n, e in enumerate(sig.entries):
        if not e.get('done'):
            continue
        for c in e['claims']:
            if c.get('checked') == 'yes':
                truth[mi.key(c['claim'])].add(n)
                text[mi.key(c['claim'])] = c['claim']
    got = pickle.load(open(CACHE, 'rb')) if os.path.exists(CACHE) else {}
    done_motif = np.array([bool(e.get('done')) for e in sig.entries])
    sig.prepare([text[k] for k in truth if k not in got])  # the models' work in batches, a model at a time
    print('prepared', flush=True)
    for i, k in enumerate(truth):
        if k in got:
            continue
        claim = text[k]
        s = sig.cheap(claim, leave_out=True)
        F = mr.facts(sig.entries, claim, sig.vec, leave_out=True)
        s['today'] = F @ np.array([w['weights'][f] for f in mr.FACTS]) + w['bias']
        for j, f in enumerate(mr.FACTS):
            s[f'facts:{f}'] = F[:, j]
        got[k] = {'truth': truth[k], 'signals': s}
        if i % 25 == 0:
            pickle.dump(got, open(CACHE, 'wb'))
            sig.save()
            print(f'{len(got)}/{len(truth)}', flush=True)
    pickle.dump(got, open(CACHE, 'wb'))
    sig.save()
    return got, done_motif


def recall(got, scorer):
    hits = dict.fromkeys(KS, 0)
    total = 0
    for k, r in got.items():
        order = np.argsort(-scorer(r['signals']))
        for K in KS:
            hits[K] += len(r['truth'] & set(order[:K].tolist()))
        total += len(r['truth'])
    return {K: round(hits[K] / total, 3) for K in KS}


def main():
    got, done_motif = collect()
    names = ['today'] + ms.CHEAP
    print('claims', len(got), 'filings', sum(len(r['truth']) for r in got.values()))
    for n in names:
        print(f'{n:12s}', recall(got, lambda s, n=n: s[n]))
    # reciprocal rank fusion of every finder
    def rrf(s, which):
        out = np.zeros(len(s['today']))
        for n in which:
            out += 1 / (60 + np.argsort(np.argsort(-s[n])))
        return out
    print(f"{'RRF all':12s}", recall(got, lambda s: rrf(s, names)))
    print(f"{'RRF cheap':12s}", recall(got, lambda s: rrf(s, ms.CHEAP)))
    # a learned combination (grouped folds by claim), every signal and today's facts
    from sklearn.linear_model import LogisticRegression
    keys = list(got)
    feats = names + [f'facts:{f}' for f in mr.FACTS]
    hits = dict.fromkeys(KS, 0)
    total = 0
    folds = 5
    for f in range(folds):
        test = set(keys[f::folds])
        X = np.concatenate([np.column_stack([got[k]['signals'][n] for n in feats]) for k in keys if k not in test])
        y = np.concatenate([[m in got[k]['truth'] for m in range(len(got[k]['signals']['today']))] for k in keys if k not in test])
        mu, sd = X.mean(0), X.std(0) + 1e-9
        model = LogisticRegression(max_iter=3000, class_weight='balanced', C=0.5).fit((X - mu) / sd, y)
        for k in test:
            Xk = np.column_stack([got[k]['signals'][n] for n in feats])
            order = np.argsort(-model.decision_function((Xk - mu) / sd))
            for K in KS:
                hits[K] += len(got[k]['truth'] & set(order[:K].tolist()))
            total += len(got[k]['truth'])
    print(f"{'learned':12s}", {K: round(hits[K] / total, 3) for K in KS})
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
