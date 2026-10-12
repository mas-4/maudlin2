"""F11 the Danaids: how much does the confidence model's leak flatter it? (Oct 12, from Fable's review, finding 3.) The
feature "motifs of the claim" counts the motifs a claim is in as the index stands now, so a filing the person removed
already counts one fewer: the model learns part of the answer from the answer. Three arms, each held out exactly as
production tests the model (filing_confidence.evaluate, folds grouped by claim, the taught reranker's held-out scores):
as production; the feature dropped; the feature as it stood just before each decision (the index's saved versions in
curation.sqlite). The paper: ~/maudlin-data/papers/the-danaids.md.

    f11_danaids.py      under the GPU lease (cached signals; any new pair asked of the judge; lease 'danaids-retrain')"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f1_gordian_knot as f1  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f11_danaids.json')
COL = fc.FEATURES.index('motifs of the claim')


def decided_at() -> dict[tuple[str, str], str]:
    """(claim key, motif) -> when the person last decided it"""
    out = {}
    for r in fc.log_rows():
        if isinstance(r.get('action'), dict):
            d = {}
            fc._decided(r['action'], d)
            for p in d:
                out[p] = r['at']
    return out


def main():
    index = mi.load()
    pairs = fc.labeled(index)
    scorer = fc.Scorer(index, mr.weights())
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    scorer.signals.prepare([c for c, _ in by_claim])
    X, y, groups, keys = [], [], [], []
    for (claim, source), items in by_claim.items():
        X.extend(scorer.rows(claim, [eid for eid, _ in items], source))
        y.extend(ok for _, ok in items)
        groups.extend([mi.key(claim)] * len(items))
        keys.extend((mi.key(claim), eid) for eid, _ in items)
    scorer.signals.save()
    X, y = np.array(X, dtype=float), np.array(y, dtype=bool)
    from app.analysis import reranker_teach
    if scorer.signals.rerank_tag != 'base':  # as fc.train: the taught reranker's scores on claims it never learned from
        taught, col = reranker_teach.held_out(), fc.FEATURES.index('rerank')
        for i, (k, e) in enumerate(keys):
            if f'{k}|{e}' in taught:
                X[i, col] = fc.logit(np.array([taught[f'{k}|{e}']]))[0]
    # The feature as it stood just before each decision
    when, versions = decided_at(), f1.Versions()
    then = np.array(X[:, COL])
    missing = 0
    versioned = np.ones(len(keys), dtype=bool)  # decisions made after the first saved version (Oct 8, 09:38)
    for i in sorted(range(len(keys)), key=lambda i: when.get(keys[i]) or ''):  # in time order: one version loaded at a time
        p = keys[i]
        at = when.get(p)
        v = versions.before(at) if at else None
        if v is None:
            missing += 1
            versioned[i] = False
            continue
        then[i] = len(v.get('claims', {}).get(p[0]) or [])
    arms = {'as production': X, 'dropped': np.delete(X, COL, axis=1), 'at decision time': np.column_stack(
        [X[:, :COL], then, X[:, COL + 1:]])}
    out = {}
    g = np.array(groups)
    for scope, rows in (('all', np.ones(len(y), dtype=bool)), ('versioned', versioned)):
        for name, A in arms.items():
            t = fc.evaluate(A[rows], y[rows], list(g[rows]))
            sure = next((r for r in t['thresholds'] if r['at'] == t.get('sure_at')), {})
            out[f'{name}, {scope}'] = {'auc': t['auc'], 'sure_at': t.get('sure_at'), 'precision': sure.get('precision'),
                                       'of kept': sure.get('of kept'), 'n': int(rows.sum())}
            print(name, scope, out[f'{name}, {scope}'], flush=True)
    kept0 = float(np.mean(X[y, COL] == 0)), float(np.mean(X[~y, COL] == 0))
    then0 = float(np.mean(then[y] == 0)), float(np.mean(then[~y] == 0))
    json.dump({'arms': out, 'filings': int(len(y)), 'kept': int(y.sum()), 'no version': missing,
               'zero motifs now (kept, removed)': kept0, 'zero motifs then (kept, removed)': then0}, open(OUT, 'w'), indent=1)
    line = (f"F11 the Danaids: the confidence model held out on {len(y)} decisions ({int(y.sum())} kept): "
            + '; '.join(f"{n} AUC {r['auc']:.3f}, sure at {r['sure_at']} ({r['precision']}, passing {r['of kept']} of kept)"
                        for n, r in out.items())
            + f"; claims in no motif, kept against removed: now {kept0[0]:.0%} / {kept0[1]:.0%}, "
              f"at decision time {then0[0]:.0%} / {then0[1]:.0%}")
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
    print('DONE', flush=True)
