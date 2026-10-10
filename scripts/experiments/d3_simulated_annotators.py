"""D3 simulated annotators (Oct 10; after "Trust or Escalate", ICLR 2025, arXiv 2407.18370: a judge's agreement with
itself across varied prompts tells when it can be trusted, and lets a threshold be set with a guaranteed error rate).
The judge (Nimble 9B) is asked K more times on each decided filing, each time shown a different random three of the
claims filed under the motif (today's ask shows the nearest three: D1's 'true'). Measured:
- AUC of today's ask, of the mean of all K+1, and of the lowest of them;
- in the confidence model (held out, folds by claim): the judge's column as today, as the mean, and the mean plus the
  spread among the asks (how far the simulated annotators disagree) as a signal of its own;
- coverage at 95% precision: the share of the filings the person kept that the model would file without asking, at
  the lowest threshold where at least 95% of what passes was kept, and the same when a filing must also have every ask
  saying yes (above 0.5). That share is curator time saved.
The report reads the reranker for the confidence model's rows, so it runs with Ollama unloaded. Resumable; caches
in EXP."""
import json
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import d1_definition_swap as d1  # noqa: E402
import d2_past_verdicts as d2  # noqa: E402
import harness  # noqa: E402
import j1_jury  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'd3_simulated_annotators.json')
K = 4  # asks beside today's
PRECISION = 0.95


def state(sig, p, k: int) -> str | None:
    """Today's ask with a random three (seed k) of the motif's other claims in place of the nearest three; None for a
    motif with three or fewer others (every draw would be the same claims)"""
    _, text = sig.judge_ask(p['claim'], sig.at[p['eid']], leave_out=True)
    own = [x['claim'] for x in sig.entries[sig.at[p['eid']]]['claims'] if x['claim'] != p['claim']]
    if len(own) <= 3:
        return None
    pick = random.Random(f"{p['key']}|{k}").sample(own, 3)
    head, _, rest = text.partition('Claims filed under it:\n')
    _, _, claim = rest.partition('\n\nNew claim: ')
    return f'{head}Claims filed under it:\n' + '\n'.join(f'- {c[:300]}' for c in pick) + f'\n\nNew claim: {claim}'


def coverage(p: np.ndarray, y: np.ndarray, gate: np.ndarray | None = None) -> tuple[float, float | None]:
    """(share of kept filings passed, threshold) at the lowest threshold where at least PRECISION of what passes was
    kept (and at least 20 pass)"""
    gate = np.ones(len(y), dtype=bool) if gate is None else gate
    for t in np.arange(0.5, 1.0, 0.01):
        passed = (p >= t) & gate
        if passed.sum() >= 20 and y[passed].mean() >= PRECISION:
            return float(passed[y].mean()), round(float(t), 2)
    return 0.0, None


def main():
    from sklearn.metrics import roc_auc_score
    sig, pairs, _ = d2.setup()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    asks = {(p['key'], k): state(sig, p, k) for p in pairs for k in range(K)}
    varied = [p for p in pairs if asks[(p['key'], 0)]]
    print(f'{len(pairs)} decided filings, {len(varied)} on motifs with more than three other claims', flush=True)
    if 'report' not in sys.argv:
        for k in range(K):
            got = saved.setdefault(str(k), {})
            todo = [(p['key'], asks[(p['key'], k)]) for p in varied if p['key'] not in got]
            for start in range(0, len(todo), d1.ROUND):
                part = todo[start:start + d1.ROUND]

                def one(x, k=k):
                    try:
                        return d1.nimble(x[1], ms.ELEMENT_QUESTION)
                    except Exception as e:  # noqa: BLE001 - asked again on a rerun
                        print(f'{k}: {type(e).__name__} {e}'[:200], flush=True)
                        return None
                for (key, _), v in zip(part, llm.parallel(one, part)):
                    if v is not None:
                        got[key] = v
                json.dump(saved, open(OUT, 'w'))
                print(f'ask {k}: {len(got)}/{len(varied)}', flush=True)
        import r1_bigger_reranker
        r1_bigger_reranker.unload_ollama()

    today = json.load(open(d1.OUT)).get('true', {})
    ps = [p for p in varied if p['key'] in today and all(p['key'] in saved.get(str(k), {}) for k in range(K))]
    y = np.array([p['kept'] for p in ps], dtype=bool)
    A = np.array([[today[p['key']]] + [saved[str(k)][p['key']] for k in range(K)] for p in ps])
    mean, low, spread = A.mean(1), A.min(1), A.std(1)
    lines = [f'D3 simulated annotators, {len(ps)} decided filings ({int(y.sum())} kept), today\'s ask and {K} more '
             f'with a random three of the motif\'s claims:',
             f'  alone: today AUC {roc_auc_score(y, A[:, 0]):.3f}, the mean {roc_auc_score(y, mean):.3f}, the lowest '
             f'{roc_auc_score(y, low):.3f}; the spread among asks, kept {spread[y].mean():.3f}, taken out {spread[~y].mean():.3f}']
    rows = [{'key': p['key'], 'claim': p['claim'], 'source': p['source'], 'eid': p['eid']} for p in ps]
    X = j1_jury.base_matrix(rows)
    jcol = fc.FEATURES.index('judge')
    lg = lambda v: fc.logit(np.clip(np.asarray(v, dtype=float), 1e-4, 1 - 1e-4))  # noqa: E731
    groups = [p['key'].split('|')[0] for p in ps]
    unanimous = (A > 0.5).all(1)
    for name, M in (('today', X),
                    ('the mean in the judge\'s place', np.column_stack([np.delete(X, jcol, 1), lg(mean)])),
                    ('the mean + the spread', np.column_stack([np.delete(X, jcol, 1), lg(mean), spread]))):
        r = fc.evaluate(M, y, groups)
        cov, t = coverage(r['p'], y)
        gcov, gt = coverage(r['p'], y, unanimous)
        lines.append(f'  confidence model, {name}: AUC {r["auc"]:.3f}; files {cov:.0%} of the kept ones unasked at '
                     f'{PRECISION:.0%} precision (from {t}), {gcov:.0%} when every ask must also say yes (from {gt})')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
