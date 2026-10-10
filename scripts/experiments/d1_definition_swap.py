"""D1 the definition swap (Oct 10; after "When Better Codebooks Are Not Enough", arXiv 2606.06781: a model can score
well on a codebook task while ignoring the codebook). Since Oct 9 the judge (Nimble 9B) is shown each motif's must-have
element (motif_signals.JUDGE_ELEMENTS). Does it read it, or judge from the name, note and claims filed under it alone?
On every filing the person decided on, the judge is asked again with the motif's element in place ('true'), with
another motif's element ('swapped', a shuffle of all of them with none left in place) and with another motif's of the
same genre ('swapped in genre', the harder test: the same kind of shape, a different one). If the judge reads the
element, a wrong one should cost AUC, and lower its yes on the filings the person kept more than on those taken out.
Only motifs whose element is drafted from what they say now; nothing is drafted here. Resumable; caches in EXP."""
import json
import os
import random
import sys
import time

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import j1_jury  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'd1_definition_swap.json')
ROUND = 32
ARMS = ('true', 'swapped', 'swapped in genre')


def derange(ids: list[str], seed: int) -> dict[str, str]:
    """Each id to another's, none to its own (a shuffled cycle); {} for fewer than two"""
    if len(ids) < 2:
        return {}
    order = sorted(ids)
    random.Random(seed).shuffle(order)
    return {a: order[(i + 1) % len(order)] for i, a in enumerate(order)}


def nimble(state: str, question: str) -> float:
    r = rq.post(f'{llm.OLLAMA_URL}/v1/systemone', timeout=300, json={
        'model': ms.JUDGE_DECIDER, 'state': state, 'questions': {'q': {'type': 'noul', 'instructions': question}}})
    r.raise_for_status()
    a = r.json()['answers']['q']
    return float(a.get('noul', a.get('probability')) if isinstance(a, dict) else a)


def main():
    from sklearn.metrics import roc_auc_score
    index = mi.load()
    sig = ms.Signals(index, mr.Vectors())
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    need = {e['id']: sig.element_of(e) for e in sig.entries}
    need = {k: v for k, v in need.items() if v}
    pairs = [(c, eid, kept) for c, eid, _, kept in fc.labeled(index) if eid in need]
    genre = {eid: mi.genre_of(index['entries'][eid]) or '' for eid in need}
    swap = {'true': {k: k for k in need}, 'swapped': derange(list(need), 1), 'swapped in genre': {}}
    for g in set(genre.values()):
        swap['swapped in genre'].update(derange([k for k in need if genre[k] == g], 2))
    print(f'{len(pairs)} decided filings on {len({p[1] for p in pairs})} motifs with a current element', flush=True)

    def state(claim, eid, arm):
        _, text = sig.judge_ask(claim, sig.at[eid], leave_out=True)
        other = swap[arm].get(eid)
        return text.replace(f'{ms.ELEMENT_LINE} {need[eid]}\n', f'{ms.ELEMENT_LINE} {need[other]}\n') if other else None

    for arm in ARMS:
        got = saved.setdefault(arm, {})
        todo = [(f'{mi.key(c)}|{eid}', state(c, eid, arm)) for c, eid, _ in pairs]
        todo = [(k, s) for k, s in todo if s and k not in got]
        for start in range(0, len(todo), ROUND):
            part = todo[start:start + ROUND]

            def one(x, arm=arm):
                try:
                    return nimble(x[1], ms.ELEMENT_QUESTION)
                except Exception as e:  # noqa: BLE001 - asked again on a rerun
                    print(f'{arm}: {type(e).__name__} {e}'[:200], flush=True)
                    return None
            for (k, _), v in zip(part, llm.parallel(one, part)):
                if v is not None:
                    got[k] = v
            json.dump(saved, open(OUT, 'w'))
            print(f'{arm}: {len(got)}/{len(pairs)}', flush=True)

    keys = [f'{mi.key(c)}|{eid}' for c, eid, _ in pairs]
    y = np.array([kept for _, _, kept in pairs], dtype=bool)
    j1 = json.load(open(j1_jury.OUT)).get('answers', {}).get('nimble:9b', {}) if os.path.exists(j1_jury.OUT) else {}
    lines = [f'D1 the definition swap, {len(pairs)} decided filings ({int(y.sum())} kept) on '
             f'{len({p[1] for p in pairs})} motifs with a current element:']
    if sum(k in j1 for k in keys) >= 0.9 * len(keys):
        ix = np.array([k in j1 for k in keys])
        lines.append(f'  no element (J1, {int(ix.sum())} of them): AUC {roc_auc_score(y[ix], [j1[k] for k in np.array(keys)[ix]]):.3f}')
    for arm in ARMS:
        ix = np.array([k in saved[arm] for k in keys])
        p = np.array([saved[arm].get(k, np.nan) for k in keys])
        lines.append(f'  {arm} ({int(ix.sum())}): AUC {roc_auc_score(y[ix], p[ix]):.3f}, mean yes on kept '
                     f'{np.nanmean(p[y]):.3f}, on taken out {np.nanmean(p[~y]):.3f}')
    t = np.array([saved['true'].get(k, np.nan) for k in keys])
    for arm in ARMS[1:]:
        s = np.array([saved[arm].get(k, np.nan) for k in keys])
        d = t - s
        ok = ~np.isnan(d)
        lines.append(f'  true minus {arm}: kept {np.mean(d[ok & y]):+.3f}, taken out {np.mean(d[ok & ~y]):+.3f}; '
                     f'the wrong element moved the yes by more than 0.1 on {np.mean(np.abs(d[ok]) > 0.1):.0%}')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
