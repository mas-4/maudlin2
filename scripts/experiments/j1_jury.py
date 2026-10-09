"""J1 a jury of models (Oct 8, the person: "having multiple models evaluate and work through our claim motif stack").
Every filing the person decided on (kept or taken out: the confidence model's own data) judged by each juror: is this
claim an instance of this motif? Each juror's answer is a probability:

- decision models (Ollama's /v1/systemone, the Jev interface: a calibrated probability in one pass, no text): Together
  AI's Tev1 4B and 0.8B (Qwen3.5), Bespoke Labs' Nimble 9B (Qwen3.5 9B);
- language models asked the filing model's yes-or-no question (motif_signals.JUDGE_PROMPT), P(yes) from the
  log-probabilities of the first word: Qwen3.5 9B, Gemma 4 12B, Ministral 3 14B; Gemma 4 26B is today's juror (the
  confidence model's 'judge' signal), from its cache.

Measured: each juror alone (AUC: how often it ranks a filing the person kept above one they took out), seconds a pair
(four at once, one model at a time), and the confidence model's held-out AUC (filing_confidence.evaluate, folds by
claim) with each juror added as a signal, and with all of them. Resumable: answers cached in OUT."""
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'j1_jury.json')
DECIDERS = [m for m in os.environ.get('DECIDERS', 'tev1:4b,tev1:0.8b,nimble:9b').split(',') if m]
ASKED = [m for m in os.environ.get('ASKED', 'qwen3.5:9b,gemma4:12b,ministral-3:14b').split(',') if m]
GEV = [m for m in os.environ.get('GEV', '').split(',') if m]  # AutoTrust's GEV-26B-Decide, built for Ollama (gev_build.py)
QUESTION = ('Is the new claim an instance of this motif: the same shape of story, as its tellers tell it, as the claims '
            'filed under it, not just the same topic, person or word?')
ROUND = 32


def pairs_and_texts():
    """[(key, claim, motif id, source, kept)], with each pair's judge prompt and decision-model state"""
    index = mi.load()
    sig = ms.Signals(index, mr.Vectors())
    out = []
    for claim, eid, source, kept in fc.labeled(index):
        n = sig.at[eid]
        e = sig.entries[n]
        ex = sig.nearest_claims(claim, n, True, 3)
        prompt = ms.JUDGE_PROMPT.format(name=e['name'], note=e.get('note') or '(no note yet)',
                                        examples='\n'.join(f'- {c}' for c in ex) or '(none yet)', claim=claim)
        state = (f"Motif: {e['name']}\nWhat it covers: {e.get('note') or '(no note yet)'}\nClaims filed under it:\n"
                 + '\n'.join(f'- {c[:300]}' for c in ex) + f'\n\nNew claim: {claim}')
        out.append({'key': f'{mi.key(claim)}|{eid}', 'claim': claim, 'eid': eid, 'source': source, 'kept': kept,
                    'prompt': prompt, 'state': state, 'judge_hash': ms.pair_hash(prompt)})
    return out


def decide(model, p):
    r = rq.post(f'{llm.OLLAMA_URL}/v1/systemone', timeout=300, json={
        'model': model, 'state': p['state'], 'questions': {'fits': {'type': 'noul', 'instructions': QUESTION}}})
    r.raise_for_status()
    a = r.json()['answers']['fits']
    v = a.get('noul', a.get('probability')) if isinstance(a, dict) else a
    return float(v)


def ask(model, p):
    r = rq.post(f'{llm.OLLAMA_URL}/api/chat', timeout=300, json={
        'model': model, 'messages': [{'role': 'user', 'content': p['prompt']}], 'think': False, 'stream': False,
        'logprobs': True, 'top_logprobs': 10, 'options': {'temperature': 0, 'num_predict': 1}})
    r.raise_for_status()
    y = no = -np.inf
    for t in ((r.json().get('logprobs') or [{}])[0].get('top_logprobs') or []):
        w = t['token'].strip().lower()
        if w.startswith('yes'):
            y = max(y, t['logprob'])
        elif w.startswith('no'):
            no = max(no, t['logprob'])
    if y == no == -np.inf:
        return 0.5
    return 1.0 if no == -np.inf else 0.0 if y == -np.inf else float(1 / (1 + np.exp(no - y)))


def gev(model, p):
    """GEV's own System 1 read-out (its serve_decide.py, kind noul): its bare prompt, then the next word's
    log-probabilities for its two answer words, 'false' and 'true' (the decision head's rows)"""
    prompt = f"[kind] noul\n[state] {p['state']}\n[question] {QUESTION}\n[options]\nfalse\ntrue\n[decision]:"
    r = rq.post(f'{llm.OLLAMA_URL}/api/generate', timeout=300, json={
        'model': model, 'prompt': prompt, 'raw': True, 'stream': False, 'logprobs': True, 'top_logprobs': 20,
        'options': {'temperature': 0, 'num_predict': 1}})
    r.raise_for_status()
    lp = {t['token']: t['logprob'] for t in ((r.json().get('logprobs') or [{}])[0].get('top_logprobs') or [])}
    y, no = lp.get('true', -np.inf), lp.get('false', -np.inf)
    if y == no == -np.inf:
        raise ValueError(f"neither answer word among the top: {list(lp)[:8]}")
    return 1.0 if no == -np.inf else 0.0 if y == -np.inf else float(1 / (1 + np.exp(no - y)))


def run_jurors(saved, pairs):
    for model, fn in [(m, decide) for m in DECIDERS] + [(m, ask) for m in ASKED] + [(m, gev) for m in GEV]:
        got = saved.setdefault('answers', {}).setdefault(model, {})
        took = saved.setdefault('seconds', {}).setdefault(model, [0.0, 0])
        todo = [p for p in pairs if p['key'] not in got]
        errors = {}
        for start in range(0, len(todo), ROUND):
            part = todo[start:start + ROUND]

            def one(p, model=model, fn=fn, errors=errors):
                try:
                    return fn(model, p)
                except Exception as e:  # noqa: BLE001 - counted as unanswered, asked again on a rerun
                    errors[f'{type(e).__name__} {e}'[:300]] = 1
                    return None
            t = time.time()
            answers = llm.parallel(one, part)
            took[0] += time.time() - t
            took[1] += len(part)
            if not any(a is not None for a in answers):  # a model that can't answer: say so once, the next model
                print(f'{model}: no answers, skipped ({"; ".join(errors)})'[:400], flush=True)
                break
            for p, a in zip(part, answers):
                if a is not None:
                    got[p['key']] = round(a, 5)
            json.dump(saved, open(OUT, 'w'))
            print(f'{model}: {len(got)}/{len(pairs)}', flush=True)


def base_matrix(pairs):
    """The confidence model's own rows for the pairs (its reranker column held out as in training)"""
    index = mi.load()
    scorer = fc.Scorer(index, mr.weights())
    by_claim = defaultdict(list)
    for i, p in enumerate(pairs):
        by_claim[(p['claim'], p['source'])].append(i)
    X = np.zeros((len(pairs), len(fc.FEATURES)))
    for (claim, source), idx in by_claim.items():
        X[idx] = scorer.rows(claim, [pairs[i]['eid'] for i in idx], source)
    from app.analysis import reranker_teach
    if scorer.signals.rerank_tag != 'base':
        held, col = reranker_teach.held_out(), fc.FEATURES.index('rerank')
        for i, p in enumerate(pairs):
            if p['key'] in held:
                X[i, col] = fc.logit(np.array([held[p['key']]]))[0]
    return X


def report(saved, pairs):
    from sklearn.metrics import roc_auc_score
    y = np.array([p['kept'] for p in pairs], dtype=bool)
    groups = [p['key'].split('|')[0] for p in pairs]
    X = base_matrix(pairs)
    judge = X[:, fc.FEATURES.index('judge')]
    cols = {'gemma4:26b (today)': judge}  # already a logit
    for m in sorted(saved.get('answers', {})):  # every juror asked so far, this run or an earlier one
        got = saved.get('answers', {}).get(m, {})
        if len(got) < 0.95 * len(pairs):
            continue
        cols[m] = fc.logit(np.array([got.get(p['key'], 0.5) for p in pairs]))
    sec = {m: s / max(n, 1) for m, (s, n) in saved.get('seconds', {}).items()}
    lines = [f'J1 jury, {len(pairs)} filings the person decided on ({int(y.sum())} kept):']
    for m, c in cols.items():
        lines.append(f'  {m} alone: AUC {roc_auc_score(y, c):.3f}' + (f', {sec[m]:.2f} s a pair' if m in sec else ''))
    no_judge = np.delete(X, fc.FEATURES.index('judge'), axis=1)
    lines.append(f'  confidence model without a juror: {fc.evaluate(no_judge, y, groups)["auc"]:.3f}')
    for m, c in cols.items():
        lines.append(f'  confidence model with {m}: {fc.evaluate(np.column_stack([no_judge, c]), y, groups)["auc"]:.3f}')
    every = np.column_stack([no_judge] + list(cols.values()))
    lines.append(f'  confidence model with the whole jury ({len(cols)}): {fc.evaluate(every, y, groups)["auc"]:.3f}')
    small = [c for m, c in cols.items() if m != 'gemma4:26b (today)']
    if small:
        lines.append(f'  confidence model with the jury but Gemma 26B ({len(small)}): '
                     f'{fc.evaluate(np.column_stack([no_judge] + small), y, groups)["auc"]:.3f}')
    return lines


if __name__ == '__main__':
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    pairs = pairs_and_texts()
    print(f'{len(pairs)} pairs', flush=True)
    if 'report' not in sys.argv:
        run_jurors(saved, pairs)
    for ln in report(saved, pairs):
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)
