"""C1 a cascade (Oct 8, the person: "run entirely through something smaller like qwen, and then low confidence scores
get bumped to a gemma round?"). The filing pick (motif_index.REUSE_PROMPT: which of these 12 motifs, none to three)
asked of a small model that fits the card whole and of today's Gemma 4 26B, on a sample of the person's confirmed
claims with the same shortlist (the plain shortlist, as E0.4); then, with no model asked, how a cascade would do:

- each model alone: the person's motifs found (of those in the shortlist) and the share of picks not theirs;
- the small model first, its pick bumped to Gemma when the confidence model's fit for it is under a line (the fit
  from the filing confidence model, trained on the person's decisions about other claims only: two folds by claim;
  its reranker and filing-model signals left out, as both learned or come from the models compared here);
- the small model first, bumped when it picks nothing, or when the two small models disagree;

each with its share bumped and seconds a claim (the models' timings here, four requests at once, one model at a time
as a cascade would run them). Resumable: answers cached in OUT."""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from notes_test import truth_sets  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'c1_cascade.json')
SAMPLE, SEED = 240, 5
BIG = 'gemma4:26b'
SMALL = ['qwen3.5:9b', 'gemma4:12b']
MODELS = SMALL + [BIG]
ROUND = 8  # claims asked per save


def sample(index):
    entries, truth, text = truth_sets(index)
    keys = sorted(truth)
    rng = np.random.default_rng(SEED)
    return entries, truth, text, [keys[i] for i in rng.permutation(len(keys))[:SAMPLE]]


def shortlist(entries, claim, vec, w):
    F = mr.facts(entries, claim, vec, leave_out=True)
    s = F @ np.array([w['weights'][f] for f in mr.FACTS]) + w['bias']
    return [int(i) for i in np.argsort(-s)[:12]]


def prompt_of(entries, k, claim, shown, today):
    parts = []
    for n, m in enumerate(shown, 1):
        own = [c['claim'] for c in entries[m]['claims'] if mi.key(c['claim']) != k]
        parts.append(f'{n}. {mi.described(entries[m])}\n' + '\n'.join(f'   - {c[:160]}' for c in own[-3:]))
    return mi.REUSE_PROMPT.format(today=today, claim=claim, options='\n'.join(parts))


def ask_all(saved):
    index = mi.load()
    entries, truth, text, keys = sample(index)
    vec, w = mr.Vectors(), mr.weights()
    today = datetime.now().strftime('%B %-d, %Y')
    claims = saved.setdefault('claims', {})
    for k in keys:
        if k not in claims:
            shown = shortlist(entries, text[k], vec, w)
            claims[k] = {'claim': text[k], 'shown': [entries[m]['id'] for m in shown],
                         'truth': sorted(entries[m]['id'] for m in truth[k]), 'prompt': prompt_of(entries, k, text[k], shown, today)}
    json.dump(saved, open(OUT, 'w'))
    for model in MODELS:  # one model at a time, as a cascade would run
        got = saved.setdefault('answers', {}).setdefault(model, {})
        took = saved.setdefault('seconds', {}).setdefault(model, [0.0, 0])
        todo = [k for k in keys if k not in got]
        for start in range(0, len(todo), ROUND):
            part = todo[start:start + ROUND]

            def one(k, model=model):
                c = claims[k]
                schema = {"type": "object", "properties": {
                    "reason": {"type": "string", "maxLength": 1000},
                    "fits": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": len(c['shown'])}}},
                    "required": ["reason", "fits"]}
                a = llm.complete_json(c['prompt'], schema, max_tokens=900, model=model)
                if a is None:
                    return None
                return [c['shown'][n - 1] for n in dict.fromkeys(a.get('fits', [])) if isinstance(n, int) and 1 <= n <= len(c['shown'])]
            t = time.time()
            answers = llm.parallel(one, part)
            took[0] += time.time() - t
            took[1] += len(part)
            for k, a in zip(part, answers):
                if a is not None:
                    got[k] = a
            json.dump(saved, open(OUT, 'w'))
            print(f'{model}: {len(got)}/{len(keys)}', flush=True)
    return keys


def fits(saved, keys):
    """(model, claim key) -> the confidence model's fit for each of the model's picks, held out by claim (two folds)"""
    index = mi.load()
    w = mr.weights()
    scorer = fc.Scorer(index, w)
    neutral = lambda claim, ns, leave_out=False: np.full(len(ns), 0.5)  # noqa: E731 - reranker and judge left out
    scorer.signals.rerank = neutral
    scorer.signals.judge = neutral
    pairs = fc.labeled(index)
    rows = {}
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    for (claim, source), items in by_claim.items():
        rows[mi.key(claim)] = (scorer.rows(claim, [e for e, _ in items], source), [ok for _, ok in items])
    source_of = {mi.key(c['claim']): c.get('source', '') for e in mi.live(index) for c in e['claims']}
    live = set(scorer.at)
    out = {}
    folds = [set(keys[0::2]), set(keys[1::2])]
    for fold in folds:
        X = np.vstack([r for k, (r, _) in rows.items() if k not in fold])
        y = np.array([ok for k, (_, oks) in rows.items() if k not in fold for ok in oks], dtype=bool)
        model, mu, sd = fc._fit(X, y)
        for k in fold:
            claim = saved['claims'][k]['claim']
            for name in MODELS:
                picks = [p for p in saved['answers'][name].get(k, []) if p in live]
                if not picks:
                    out[(name, k)] = []
                    continue
                p = model.predict_proba((scorer.rows(claim, picks, source_of.get(k, '')) - mu) / sd)[:, 1]
                out[(name, k)] = [round(float(v), 3) for v in p]
    return out


def score(rows):
    """found of reach, wrong of picks"""
    found = sum(len(set(p) & set(t)) for p, t, s in rows)
    reach = sum(len(set(t) & set(s)) for p, t, s in rows)
    picks = sum(len(p) for p, t, s in rows)
    return found / max(reach, 1), (picks - found) / max(picks, 1)


def report(saved, keys, fit):
    C, A = saved['claims'], saved['answers']
    keys = [k for k in keys if all(k in A[m] for m in MODELS)]
    sec = {m: saved['seconds'][m][0] / max(saved['seconds'][m][1], 1) for m in MODELS}
    lines = [f'C1 cascade, {len(keys)} of the person\'s confirmed claims, four requests at once:']

    def line(label, picks, bumped, small):
        f, wrong = score([(picks[k], C[k]['truth'], C[k]['shown']) for k in keys])
        cost = sec[small] + bumped * sec[BIG] if small else sec[BIG]
        lines.append(f'  {label}: found {f:.0%} of their motifs in the shortlist, {wrong:.0%} of picks not theirs; '
                     f'{bumped:.0%} bumped to Gemma 26B; {cost:.1f} s a claim')
    for m in MODELS:
        line(f'{m} alone', {k: A[m][k] for k in keys}, 0.0 if m != BIG else 1.0, m if m != BIG else None)
    for small in SMALL:
        top = {k: max(fit.get((small, k)) or [0.0]) for k in keys}
        for t in (0.3, 0.5, 0.7, 0.85):
            bump = {k for k in keys if top[k] < t}
            line(f'{small}, bumped under a fit of {t}', {k: A[BIG][k] if k in bump else A[small][k] for k in keys},
                 len(bump) / len(keys), small)
        bump = {k for k in keys if not A[small][k]}
        line(f'{small}, bumped when it picks nothing', {k: A[BIG][k] if k in bump else A[small][k] for k in keys},
             len(bump) / len(keys), small)
    a, b = SMALL
    bump = {k for k in keys if set(A[a][k]) != set(A[b][k])}
    picks = {k: A[BIG][k] if k in bump else A[a][k] for k in keys}
    f, wrong = score([(picks[k], C[k]['truth'], C[k]['shown']) for k in keys])
    lines.append(f'  both small models, bumped when they disagree: found {f:.0%}, {wrong:.0%} of picks not theirs; '
                 f'{len(bump) / len(keys):.0%} bumped; {sec[a] + sec[b] + len(bump) / len(keys) * sec[BIG]:.1f} s a claim')
    return lines


if __name__ == '__main__':
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    keys = ask_all(saved)
    print('asked; fits on the CPU', flush=True)
    fit = fits(saved, keys)
    for ln in report(saved, keys, fit):
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)
