"""R1 a bigger reranker (Oct 9). The confidence model's 'rerank' signal is Qwen3-Reranker 0.6B, taught the person's
taste (reranker_teach). Here Qwen3-Reranker 4B, untaught, scores every filing the person decided on (the same input:
the motif's name, note and two nearest claims, the claim held out), against the 0.6B untaught and taught. Measured:
each alone (AUC), and the confidence model held out with each in the reranker's place, plus seconds a pair. Run under
the GPU lease (it unloads Ollama's models first: the 4B needs about 8 GB). Resumable."""
import json
import os
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

OUT = os.path.join(harness.EXP, 'r1_bigger_reranker.json')
MODELS = [m for m in os.environ.get('RERANKERS', 'Qwen/Qwen3-Reranker-0.6B,Qwen/Qwen3-Reranker-4B').split(',') if m]
BATCH = 4


def unload_ollama():
    for m in rq.get(f'{llm.OLLAMA_URL}/api/ps', timeout=30).json().get('models', []):
        rq.post(f'{llm.OLLAMA_URL}/api/generate', json={'model': m['name'], 'keep_alive': 0}, timeout=60)
    time.sleep(5)


def documents(pairs):
    index = mi.load()
    sig = ms.Signals(index, mr.Vectors())
    out = {}
    for p in pairs:
        n = sig.at[p['eid']]
        out[p['key']] = sig._document(n, sig.nearest_claims(p['claim'], n, True, 2))
    return out


def score(model_name, pairs, docs, got, took):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_name, padding_side='left')
    model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float16).to('cuda').eval()
    yes, no = tok.convert_tokens_to_ids('yes'), tok.convert_tokens_to_ids('no')
    todo = [p for p in pairs if p['key'] not in got]
    for i in range(0, len(todo), BATCH):
        part = todo[i:i + BATCH]
        t = time.time()
        texts = [ms.rerank_text(p['claim'], docs[p['key']]) for p in part]
        batch = tok(texts, padding=True, truncation=True, max_length=1024, return_tensors='pt').to('cuda')
        with torch.no_grad():
            logits = model(**batch).logits[:, -1, :]
        pr = torch.stack([logits[:, no], logits[:, yes]], 1).float().log_softmax(1)[:, 1].exp().tolist()
        took[0] += time.time() - t
        took[1] += len(part)
        for p, v in zip(part, pr):
            got[p['key']] = round(v, 5)
        if i % (BATCH * 25) == 0:
            print(f'{model_name}: {len(got)}/{len(pairs)}', flush=True)
    del model
    torch.cuda.empty_cache()


def report(saved, pairs):
    from sklearn.metrics import roc_auc_score
    y = np.array([p['kept'] for p in pairs], dtype=bool)
    groups = [p['key'].split('|')[0] for p in pairs]
    X = j1_jury.base_matrix(pairs)
    col = fc.FEATURES.index('rerank')
    sec = {m: s / max(n, 1) for m, (s, n) in saved['seconds'].items()}
    lines = [f'R1 a bigger reranker, {len(pairs)} filings the person decided on ({int(y.sum())} kept):',
             f'  0.6B taught (today) alone: AUC {roc_auc_score(y, X[:, col]):.3f}',
             f'  confidence model with 0.6B taught (today): {fc.evaluate(X, y, groups)["auc"]:.3f}',
             f'  confidence model with no reranker: {fc.evaluate(np.delete(X, col, 1), y, groups)["auc"]:.3f}']
    for m, got in saved['answers'].items():
        c = fc.logit(np.array([got.get(p['key'], 0.5) for p in pairs]))
        Xm = X.copy()
        Xm[:, col] = c
        lines += [f'  {m} untaught alone: AUC {roc_auc_score(y, c):.3f}, {sec[m]:.2f} s a pair',
                  f'  confidence model with {m} in its place: {fc.evaluate(Xm, y, groups)["auc"]:.3f}',
                  f'  confidence model with {m} as well: {fc.evaluate(np.column_stack([X, c]), y, groups)["auc"]:.3f}']
    return lines


if __name__ == '__main__':
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {'answers': {}, 'seconds': {}}
    pairs = j1_jury.pairs_and_texts()
    print(f'{len(pairs)} pairs', flush=True)
    if 'report' not in sys.argv:
        unload_ollama()
        docs = documents(pairs)
        for m in MODELS:
            score(m, pairs, docs, saved['answers'].setdefault(m, {}), saved['seconds'].setdefault(m, [0.0, 0]))
            json.dump(saved, open(OUT, 'w'))
    for ln in report(saved, pairs):
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)
