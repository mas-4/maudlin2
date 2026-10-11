"""F3 Ma'at: a fixed yardstick for the machine (Oct 11, the person: "are we going to be able to see if/when that 85%
right number climbs over time?"). The day's kept rate moves with what the person chooses to check, and each model's
held-out test with what it was trained on; neither is the same measure week to week. Ma'at weighs every version against
the same feather: SET of the person's decisions on the machine's filings, drawn once (seed fixed, kept in maat_set.json,
never drawn again), whole claims at a time. Each run trains its own copy of the confidence model on every other decision
(production's model is never touched: it keeps learning from all of them) and scores the set:

    AUC             how often a filing they kept scores above one they took out
    right when sure of the set's filings past the run's own sure line (as production picks it), how many they kept
    passed          how many of the kept ones pass as sure: their workload, falling as it climbs

The features are the machine as it stands that day: the index, the shortlist, the reranker and the judge then. Each run
is a line in the log and a row in maat_history.json.

    f3_maat.py      under the GPU lease (the judge's yes or no for new pairs; lease 'maat-weigh')"""
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime as dt

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

SET = os.path.join(harness.EXP, 'maat_set.json')
HISTORY = os.path.join(harness.EXP, 'maat_history.json')
SIZE = 200  # filings, whole claims at a time


def feather(pairs: list[tuple]) -> list[tuple[str, str, bool]]:
    """The set: drawn on the first run, the same ever after"""
    if os.path.exists(SET):
        return [tuple(x) for x in json.load(open(SET))['filings']]
    by = defaultdict(list)
    for claim, eid, _, ok in pairs:
        by[mi.key(claim)].append((mi.key(claim), eid, ok))
    keys = sorted(by)
    random.Random(42).shuffle(keys)
    out = []
    for k in keys:
        if len(out) >= SIZE:
            break
        out += by[k]
    json.dump({'drawn': dt.now().isoformat(timespec='seconds'), 'filings': out}, open(SET, 'w'))
    return out


def main():
    index = mi.load()
    pairs = fc.labeled(index)
    held = feather(pairs)
    held_keys, held_pairs = {k for k, _, _ in held}, {(k, e) for k, e, _ in held}
    scorer = fc.Scorer(index, mr.weights())
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    scorer.signals.prepare([c for c, _ in by_claim])
    X, y, test, out = [], [], [], []
    for (claim, source), items in by_claim.items():
        X.extend(scorer.rows(claim, [eid for eid, _ in items], source))
        y.extend(ok for _, ok in items)
        test.extend((mi.key(claim), eid) in held_pairs for eid, _ in items)  # the set's own filings, the person's latest word
        out.extend([mi.key(claim) in held_keys] * len(items))  # none of the set's claims trained on
    scorer.signals.save()
    X, y, test, out = np.array(X), np.array(y, dtype=bool), np.array(test), np.array(out)
    from app.analysis import reranker_teach
    if scorer.signals.rerank_tag != 'base':  # as fc.train: the taught reranker's scores on claims it never learned from
        taught, col = reranker_teach.held_out(), fc.FEATURES.index('rerank')
        keys = [f'{mi.key(c)}|{e}' for (c, _), items in by_claim.items() for e, _ in items]
        for i, k in enumerate(keys):
            if k in taught:
                X[i, col] = fc.logit(np.array([taught[k]]))[0]
    groups = [mi.key(c) for (c, _), items in by_claim.items() for _ in items]
    train = ~out
    # The sure line as production picks it, from the training decisions' own held-out test
    sure_at = fc.evaluate(X[train], y[train], [g for g, t in zip(groups, train) if t]).get('sure_at') or 0.95
    model, mu, sd = fc._fit(X[train], y[train])
    p = model.predict_proba((X[test] - mu) / sd)[:, 1]
    from sklearn.metrics import roc_auc_score
    yt = y[test]
    passed = p >= sure_at
    row = {'at': dt.now().isoformat(timespec='seconds'), 'filings': int(test.sum()), 'kept': int(yt.sum()),
           'auc': round(float(roc_auc_score(yt, p)), 3), 'sure_at': sure_at,
           'right when sure': round(float(yt[passed].mean()), 3) if passed.any() else None,
           'kept that pass': round(float(passed[yt].mean()), 3) if yt.any() else None,
           'trained on': int(train.sum()), 'judge': ms.judge_tag()}
    history = json.load(open(HISTORY)) if os.path.exists(HISTORY) else []
    history.append(row)
    json.dump(history, open(HISTORY, 'w'), indent=1)
    line = (f"F3 Ma'at: the fixed set of {row['filings']} filings ({row['kept']} kept) against a model trained on the "
            f"other {row['trained on']}: AUC {row['auc']:.3f}; past the sure line ({sure_at:.0%}) "
            f"{row['right when sure'] if row['right when sure'] is None else format(row['right when sure'], '.0%')} right, "
            f"{row['kept that pass']:.0%} of the kept passing as sure")
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
    print('DONE', flush=True)
