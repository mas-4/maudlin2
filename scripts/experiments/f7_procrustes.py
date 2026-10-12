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

Oct 12, the person's decision on Straight news (c): Straight news and no motif are one "nothing fit" population. A
claim whose only motif now is Straight news, or that has no motif now, counts as nothing fit, and so do the claims with
no motif the machine never filed with a decision (their words from the watch list), scored by the fold model their key
picks; Straight news itself is left out of every claim's candidates (it is the sink, tested by Charybdis, F21). The 112
of the hypotheses are reported as registered, and the larger population beside them.

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


STRAIGHT_NEWS = 'Straight news'


def straight_news(index: dict) -> str | None:
    """The Straight news motif's id, by its name (M742 on Oct 12; looked up, never assumed)"""
    return next((e['id'] for e in mi.live(index) if e['name'].strip().lower() == STRAIGHT_NEWS.lower()), None)


def with_plain_news(index: dict, kinds: dict[str, str]) -> tuple[dict[str, str], dict[str, tuple[str, str]], set[str]]:
    """(c): (kinds with Straight news and no motif counted as nothing fit; the plain claims Procrustes has no decisions
    for, key -> (claim, source); the keys of every plain claim: no motif now, or only in Straight news)"""
    from app.analysis import watch_list
    sn = straight_news(index)
    plain = set()
    for k, ids in index['claims'].items():
        ids = {mi.resolve(index, i) for i in mi._ids(index, k)}
        if not ids or (sn and ids == {sn}):
            plain.add(k)
    out = dict(kinds)
    for k in plain & set(kinds):
        out[k] = 'nothing fit'
    words = {}
    for c in (index['entries'].get(sn) or {}).get('claims', []) if sn else []:
        words[mi.key(c['claim'])] = (c['claim'], c.get('source', ''))
    for k, w in watch_list.sync(index)['claims'].items():
        if w.get('why') == 'no motif' and w.get('claim'):
            words.setdefault(k, (w['claim'], w.get('source', '')))
    extras = {k: words[k] for k in plain - set(kinds) if k in words}
    for k in extras:
        out[k] = 'nothing fit'
    return out, extras, plain


def auc(pos, neg) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score([1] * len(pos) + [0] * len(neg), list(pos) + list(neg))) if pos and neg else float('nan')


def main():
    index = mi.load()
    w = mr.weights()
    pairs = fc.labeled(index)
    registered = sorted_claims(index)
    kinds, extras, plain = with_plain_news(index, registered)
    sn = straight_news(index)
    scorer = fc.Scorer(index, w)
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    claims = [cs for cs in by_claim if mi.key(cs[0]) in kinds] + list(extras.values())
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
    for k in extras:  # in no fold's training: the fold its key picks
        fold_of[k] = int(k, 16) % 5
    best, margin = {}, {}
    for f in range(5):
        tr = np.array([fold_of[g] != f for g in groups])
        model, mu, sd = fc._fit(X[tr], y[tr])
        mine = [(c, s) for c, s in claims if fold_of.get(mi.key(c)) == f]
        for n, (claim, source) in enumerate(mine):
            ids = [i for i in dict.fromkeys([eid for eid, _ in by_claim.get((claim, source), [])] + scorer.candidates(claim))
                   if i != sn and i in scorer.at]  # Straight news is the sink, not a motif a claim fits
            if not ids:
                continue
            p = np.sort(model.predict_proba((scorer.rows(claim, ids, source) - mu) / sd)[:, 1])[::-1]
            best[mi.key(claim)] = float(p[0])
            margin[mi.key(claim)] = float(p[0] - (p[1] if len(p) > 1 else 0))
            if n % 50 == 0:
                print(f'fold {f}: {n}/{len(mine)}', flush=True)
        scorer.signals.save()
    groups_of = defaultdict(list)
    for k, kind in registered.items():
        if k in best:
            groups_of[kind].append(k)
    fit_best = [best[k] for k in groups_of['fits']]
    none_best = [best[k] for k in groups_of['nothing fit']]
    wrong_best = [best[k] for k in groups_of['wrong motif']]
    # (c): Straight news and no motif counted as nothing fit
    ext = defaultdict(list)
    for k, kind in kinds.items():
        if k in best:
            ext[kind].append(k)
    plain_best = [best[k] for k in ext['nothing fit'] if k in plain]
    rows = [{'line': t, 'nothing fit caught': round(float(np.mean([b < t for b in none_best])), 3) if none_best else None,
             'wrong motif caught': round(float(np.mean([b < t for b in wrong_best])), 3) if wrong_best else None,
             'fits sent to proposals': round(float(np.mean([b < t for b in fit_best])), 3)} for t in LINES]
    out = {'n': {k: len(v) for k, v in groups_of.items()},
           'auc best': round(1 - auc(none_best, fit_best), 3),  # a low best means nothing fits
           'auc margin': round(1 - auc([margin[k] for k in groups_of['nothing fit']], [margin[k] for k in groups_of['fits']]), 3),
           'lines': rows,
           'with plain news': {'n': {k: len(v) for k, v in ext.items()}, 'plain': len(plain_best),
                               'auc best': round(1 - auc([best[k] for k in ext['nothing fit']],
                                                         [best[k] for k in ext['fits']]), 3),
                               'auc best, plain alone': round(1 - auc(plain_best, [best[k] for k in ext['fits']]), 3)}}
    json.dump(out | {'best': best, 'margin': margin, 'kinds': registered, 'kinds with plain news': kinds,
                     'plain': sorted(plain)}, open(OUT, 'w'))
    n = out['n']
    line = (f"F7 Procrustes: {n.get('fits', 0)} claims that fit, {n.get('nothing fit', 0)} where nothing fit, "
            f"{n.get('wrong motif', 0)} in the wrong motif; the best fit in a claim's shortlist (held out) picks out "
            f"'nothing fit' at AUC {out['auc best']:.2f} (its margin over the second {out['auc margin']:.2f}); "
            + '; '.join(f"under {r['line']}: catches {r['nothing fit caught']:.0%} of nothing-fit and "
                        f"{r['wrong motif caught'] or 0:.0%} of wrong-motif, sends {r['fits sent to proposals']:.0%} "
                        f"of fitting claims to the proposals" for r in rows))
    p = out['with plain news']
    line += (f"; with Straight news and no motif as nothing fit (c): {p['n'].get('nothing fit', 0)} nothing fit, "
             f"AUC {p['auc best']:.2f}; the {p['plain']} plain claims alone {p['auc best, plain alone']:.2f}")
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
    print('DONE', flush=True)
