"""F7 Procrustes: can the machine tell when nothing fits? (Oct 11.) Procrustes stretched or cut every guest to fit his
bed; the filing does the same when the right motif doesn't exist yet: it files the claim in the nearest one, and the
person takes it out and makes the motif it needed (or leaves the claim with none). A claim left unfiled and proposed costs
one look; a forced filing costs a removal, a search and a new motif. The person's decisions sort the machine's claims:

    fits            a filing of it the person kept
    wrong motif     every filing of it removed, and the person put it in a motif that already existed (move, also, file)
    nothing fit     every filing of it removed, and it went into a motif the person made from it, or into none

For each claim, the confidence model's chance the person keeps each motif in its shortlist (the motif it was filed in and
the CANDIDATES best others), from a model that never saw the claim (grouped folds, as the confidence model is tested):
does the best of them, or its margin over the second, pick out "nothing fit" (AUC), and where would a line sending
claims to the proposals instead catch them, at what cost in claims that fit?

    f7_procrustes.py        under the GPU lease (the judge's yes or no for new pairs; lease 'procrustes-replay')"""
import json
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import curation_db as cdb  # noqa: E402
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f7_procrustes.json')
LINES = (0.2, 0.3, 0.4, 0.5, 0.6)


def carved() -> set[str]:
    """Claims the person made a new motif from"""
    con = sqlite3.connect(f'file:{cdb.DB}?mode=ro', uri=True)
    out = set()
    for (raw,) in con.execute('select action from curation where reverted = 0'):
        try:
            a = json.loads(raw)
        except ValueError:
            continue
        for s in a.get('steps', [a]):
            if s.get('action') == 'new_with':
                out |= {mi.key(c['claim']) for c in s.get('claims', []) if isinstance(c, dict) and c.get('claim')}
    return out


def sorted_claims(index: dict) -> dict[str, str]:
    """claim key -> 'fits', 'wrong motif' or 'nothing fit'"""
    machine = fc.decisions()
    by_hand = {p: v for p, v in fc.decisions(hand=True).items() if p not in machine and v}
    kept, removed, placed = defaultdict(bool), set(), {k for k, _ in by_hand}
    for (k, _), v in machine.items():
        kept[k] |= v
        if not v:
            removed.add(k)
    now = {mi.key(c['claim']) for e in mi.live(index) for c in e['claims']}
    made = carved()
    out = {}
    for k in set(kept) | removed:
        if kept[k]:
            out[k] = 'fits'
        elif k in placed and k not in made:
            out[k] = 'wrong motif'
        elif k in made or k not in now:
            out[k] = 'nothing fit'
    return out


def auc(pos, neg) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score([1] * len(pos) + [0] * len(neg), list(pos) + list(neg))) if pos and neg else float('nan')


def main():
    index = mi.load()
    w = mr.weights()
    pairs = fc.labeled(index)
    kinds = sorted_claims(index)
    scorer = fc.Scorer(index, w)
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    claims = [cs for cs in by_claim if mi.key(cs[0]) in kinds]
    scorer.signals.prepare([c for c, _ in claims])
    X, y, groups = [], [], []
    for (claim, source), items in by_claim.items():
        X.extend(scorer.rows(claim, [eid for eid, _ in items], source))
        y.extend(ok for _, ok in items)
        groups.extend([mi.key(claim)] * len(items))
    X, y = np.array(X), np.array(y, dtype=bool)
    from app.analysis import reranker_teach
    if scorer.signals.rerank_tag != 'base':  # as fc.train: the taught reranker's scores on claims it never learned from
        held, col = reranker_teach.held_out(), fc.FEATURES.index('rerank')
        keys = [f'{mi.key(c)}|{e}' for (c, _), items in by_claim.items() for e, _ in items]
        for i, k in enumerate(keys):
            if k in held:
                X[i, col] = fc.logit(np.array([held[k]]))[0]
    from sklearn.model_selection import GroupKFold
    fold_of = {}
    for f, (_, te) in enumerate(GroupKFold(5).split(X, y, groups)):
        for i in te:
            fold_of[groups[i]] = f
    best, margin = {}, {}
    for f in range(5):
        tr = np.array([fold_of[g] != f for g in groups])
        model, mu, sd = fc._fit(X[tr], y[tr])
        mine = [(c, s) for c, s in claims if fold_of.get(mi.key(c)) == f]
        for n, (claim, source) in enumerate(mine):
            ids = list(dict.fromkeys([eid for eid, _ in by_claim[(claim, source)]] + scorer.candidates(claim)))
            p = np.sort(model.predict_proba((scorer.rows(claim, ids, source) - mu) / sd)[:, 1])[::-1]
            best[mi.key(claim)] = float(p[0])
            margin[mi.key(claim)] = float(p[0] - (p[1] if len(p) > 1 else 0))
            if n % 50 == 0:
                print(f'fold {f}: {n}/{len(mine)}', flush=True)
        scorer.signals.save()
    groups_of = defaultdict(list)
    for k, kind in kinds.items():
        if k in best:
            groups_of[kind].append(k)
    fit_best = [best[k] for k in groups_of['fits']]
    none_best = [best[k] for k in groups_of['nothing fit']]
    wrong_best = [best[k] for k in groups_of['wrong motif']]
    rows = [{'line': t, 'nothing fit caught': round(float(np.mean([b < t for b in none_best])), 3) if none_best else None,
             'wrong motif caught': round(float(np.mean([b < t for b in wrong_best])), 3) if wrong_best else None,
             'fits sent to proposals': round(float(np.mean([b < t for b in fit_best])), 3)} for t in LINES]
    out = {'n': {k: len(v) for k, v in groups_of.items()},
           'auc best': round(1 - auc(none_best, fit_best), 3),  # a low best means nothing fits
           'auc margin': round(1 - auc([margin[k] for k in groups_of['nothing fit']], [margin[k] for k in groups_of['fits']]), 3),
           'lines': rows}
    json.dump(out | {'best': best, 'margin': margin, 'kinds': kinds}, open(OUT, 'w'))
    n = out['n']
    line = (f"F7 Procrustes: {n.get('fits', 0)} claims that fit, {n.get('nothing fit', 0)} where nothing fit, "
            f"{n.get('wrong motif', 0)} in the wrong motif; the best fit in a claim's shortlist (held out) picks out "
            f"'nothing fit' at AUC {out['auc best']:.2f} (its margin over the second {out['auc margin']:.2f}); "
            + '; '.join(f"under {r['line']}: catches {r['nothing fit caught']:.0%} of nothing-fit and "
                        f"{r['wrong motif caught'] or 0:.0%} of wrong-motif, sends {r['fits sent to proposals']:.0%} "
                        f"of fitting claims to the proposals" for r in rows))
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
    print('DONE', flush=True)
