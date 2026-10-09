"""P1 Nimble on proposals (Oct 9): the 💡 proposals of a related or rests-on link are scored by Gemma 26B, 0 to 10
(motif_proposals.JUDGE_PROMPT: how likely the person accepts it), and best fit weighs that score with how alike the two
motifs are and the like (FIT_FACTS) to give each open proposal its chance of approval. Here Nimble 9B (the J1 winner,
a decision model: a probability in one pass) answers the same question as a yes or no, on every link proposal the
person has decided (approved or rejected). Measured: each judge alone (AUC: how often it ranks an approved proposal
above a rejected one), and best fit with each (held out, five folds), plus seconds a proposal. Resumable."""
import json
import os
import sys
import time

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402

OUT = os.path.join(harness.EXP, 'p1_nimble_proposals.json')
MODEL = 'nimble:9b'


def nimble(state: str, question: str) -> float:
    r = rq.post(f'{llm.OLLAMA_URL}/v1/systemone', timeout=300, json={
        'model': MODEL, 'state': state, 'questions': {'accept': {'type': 'noul', 'instructions': question}}})
    r.raise_for_status()
    a = r.json()['answers']['accept']
    return float(a.get('noul', a.get('probability')) if isinstance(a, dict) else a)


def asks(index, decided):
    out = {}
    for p in decided:
        x, y = mp.pair(p)
        a, b = index['entries'][x], index['entries'][y]
        link = (f'"{a["name"]}" and "{b["name"]}" are related' if p['kind'] == 'relate'
                else f'"{a["name"]}" rests on "{b["name"]}"')
        state = f"Motif A. {mp.shown(a, b)}\n\nMotif B. {mp.shown(b, a)}\n\nThe suggested link: {link}"
        question = (f'Would the person who curates this index of recurring rumor and narrative shapes accept this link? '
                    f'A good link: {mp.JUDGE_TESTS[p["kind"]]}. A weak one: the two only share a topic, a mood, a cause '
                    f'and effect, or the same people or events.')
        out[p['id']] = (state, question)
    return out


def main():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    index, store = mi.load(), mp.load()
    decided = [p for p in store.values() if p['kind'] in mp.JUDGED and p['status'] in ('approved', 'rejected')
               and mp._live_pair(p, index) and 'judge' in p]
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {'answers': {}, 'seconds': [0.0, 0]}
    todo = [(pid, sq) for pid, sq in asks(index, decided).items() if pid not in saved['answers']]
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        t = time.time()
        got = llm.parallel(lambda x: nimble(*x[1]), part)
        saved['seconds'][0] += time.time() - t
        saved['seconds'][1] += len(part)
        saved['answers'].update({pid: round(v, 5) for (pid, _), v in zip(part, got) if v is not None})
        json.dump(saved, open(OUT, 'w'))
        print(f'P1 {len(saved["answers"])}/{len(decided)}', flush=True)
    decided = [p for p in decided if p['id'] in saved['answers']]
    y = np.array([p['status'] == 'approved' for p in decided])
    gemma = np.array([p['judge']['score'] for p in decided], dtype=float)
    nim = np.array([saved['answers'][p['id']] for p in decided])
    X = mp.fit_facts(decided, index)  # its last column is Gemma's score
    j = mp.FIT_FACTS.index('judge')

    def held_out(M):
        p = np.zeros(len(y))
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=3).split(M, y):
            mu, sd = M[tr].mean(0), M[tr].std(0) + 1e-9
            p[te] = LogisticRegression(max_iter=1000).fit((M[tr] - mu) / sd, y[tr]).predict_proba((M[te] - mu) / sd)[:, 1]
        return roc_auc_score(y, p)
    logit = np.log(np.clip(nim, 1e-4, 1 - 1e-4) / np.clip(1 - nim, 1e-4, 1))
    lines = [f'P1 Nimble on proposals, {len(y)} decided links ({int(y.sum())} approved), '
             f'{saved["seconds"][0] / max(saved["seconds"][1], 1):.2f} s a proposal four at once:',
             f'  Gemma 26B score alone: AUC {roc_auc_score(y, gemma):.3f}',
             f'  Nimble 9B alone: AUC {roc_auc_score(y, nim):.3f}',
             f'  best fit without a judge: {held_out(np.delete(X, j, 1)):.3f}',
             f'  best fit with Gemma (today): {held_out(X):.3f}',
             f'  best fit with Nimble instead: {held_out(np.column_stack([np.delete(X, j, 1), logit])):.3f}',
             f'  best fit with both: {held_out(np.column_stack([X, logit])):.3f}']
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
