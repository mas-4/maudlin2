"""D2 the curator's past verdicts as examples (Oct 10; after the few-shot results in the Arabian Nights motif-indexing
work, arXiv 2603.19283, and CIPHER, NeurIPS 2024: show a model the corrections it has had). The judge (Nimble 9B) sees
the claims filed under a motif, but never the ones the person took out of it, which are the nearest thing we have to a
line drawn. Here each decided filing is judged again with the claims the person took out of that motif BEFORE this
filing was decided (no peeking at later rulings), the three nearest it by meaning:
- 'taken out': "Taken out of it by the curator:" and those claims;
- 'taken out, why': the same with a reason for each where one was drafted (J2's, by Gemma 26B, from the claim, its
  tellings and the motif; only for removals J2 saw).
Against D1's 'true' (today's judge, the same state without them). Measured: AUC on all of them and on the filings
whose motif had a removal to show, and the yes on kept against taken out. Resumable; caches in EXP."""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import d1_definition_swap as d1  # noqa: E402
import harness  # noqa: E402
import j2_judge_variants as j2  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'd2_past_verdicts.json')
ARMS = ('taken out', 'taken out, why')
SHOWN = 3


def decided_at() -> dict[str, str]:
    """'claim key|motif id' -> when the person last decided it (the log's time)"""
    out = {}
    for r in fc.log_rows():
        a = r.get('action')
        for s in ([a] + (a.get('steps') or [])) if isinstance(a, dict) else []:
            if isinstance(s, dict):
                got = {}
                fc._decided(s, got)
                for (k, eid) in got:
                    out[f'{k}|{eid}'] = str(r.get('at', ''))
    return out


def setup():
    """(sig, pairs [{key, claim, eid, kept, at}], need) for the decided filings on motifs with a current element"""
    index = mi.load()
    sig = ms.Signals(index, mr.Vectors())
    need = {e['id']: sig.element_of(e) for e in sig.entries}
    need = {k: v for k, v in need.items() if v}
    when = decided_at()
    pairs = []
    for c, eid, source, kept in fc.labeled(index):
        if eid in need:
            k = f'{mi.key(c)}|{eid}'
            pairs.append({'key': k, 'claim': c, 'eid': eid, 'source': source, 'kept': kept, 'at': when.get(k, '')})
    return sig, pairs, need


def removed_before(sig, pairs, p) -> list[dict]:
    """The SHOWN removals from p's motif decided before p, nearest p's claim"""
    past = [q for q in pairs if q['eid'] == p['eid'] and not q['kept'] and q['at'] < p['at'] and q['claim'] != p['claim']]
    if not past:
        return []
    sims = sig.vec([q['claim'] for q in past]) @ sig.vec([p['claim']])[0]
    return [past[i] for i in np.argsort(-sims)[:SHOWN]]


def state(sig, p, shown, reasons, why: bool) -> str | None:
    _, text = sig.judge_ask(p['claim'], sig.at[p['eid']], leave_out=True)
    if not shown:
        return None
    lines = []
    for q in shown:
        r = (reasons.get(q['key']) or {}).get('reason') if why else None
        lines.append(f"- {q['claim'][:300]}" + (f' (why: {r})' if r else ''))
    head, _, claim = text.rpartition('\n\nNew claim: ')
    return f'{head}\nTaken out of it by the curator, as not this motif:\n' + '\n'.join(lines) + f'\n\nNew claim: {claim}'


def main():
    from sklearn.metrics import roc_auc_score
    sig, pairs, _ = setup()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    reasons = json.load(open(j2.OUT)).get('reasons', {}) if os.path.exists(j2.OUT) else {}
    shown = {p['key']: removed_before(sig, pairs, p) for p in pairs}
    with_past = [p for p in pairs if shown[p['key']]]
    print(f'{len(pairs)} decided filings, {len(with_past)} on a motif with an earlier removal to show; reasons for '
          f'{sum(q["key"] in reasons for p in with_past for q in shown[p["key"]])} of '
          f'{sum(len(shown[p["key"]]) for p in with_past)} shown', flush=True)
    for arm in ARMS:
        got = saved.setdefault(arm, {})
        todo = [(p['key'], state(sig, p, shown[p['key']], reasons, arm.endswith('why'))) for p in with_past]
        todo = [(k, s) for k, s in todo if s and k not in got]
        for start in range(0, len(todo), d1.ROUND):
            part = todo[start:start + d1.ROUND]

            def one(x, arm=arm):
                try:
                    return d1.nimble(x[1], ms.ELEMENT_QUESTION)
                except Exception as e:  # noqa: BLE001 - asked again on a rerun
                    print(f'{arm}: {type(e).__name__} {e}'[:200], flush=True)
                    return None
            for (k, _), v in zip(part, llm.parallel(one, part)):
                if v is not None:
                    got[k] = v
            json.dump(saved, open(OUT, 'w'))
            print(f'{arm}: {len(got)}/{len(with_past)}', flush=True)

    base = json.load(open(d1.OUT)).get('true', {}) if os.path.exists(d1.OUT) else {}
    ps = [p for p in with_past if p['key'] in base and all(p['key'] in saved[a] for a in ARMS)]
    y = np.array([p['kept'] for p in ps], dtype=bool)
    late = np.array([p['at'] >= sorted(q['at'] for q in ps)[len(ps) // 2] for p in ps])
    lines = [f'D2 past verdicts as examples: {len(ps)} decided filings ({int(y.sum())} kept) on a motif with an earlier '
             f'removal to show (of {len(pairs)}):']
    for name, got in (('today (D1 true)', base), *((a, saved[a]) for a in ARMS)):
        v = np.array([got[p['key']] for p in ps])
        lines.append(f'  {name}: AUC {roc_auc_score(y, v):.3f}, the later half {roc_auc_score(y[late], v[late]):.3f}; '
                     f'mean yes on kept {v[y].mean():.3f}, on taken out {v[~y].mean():.3f}')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
