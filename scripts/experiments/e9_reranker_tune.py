"""E9 The reranker taught the person's taste (docs/filing-experiments.md). Qwen3-Reranker-0.6B reads a claim and a
motif (its note, nickname and two nearest claims) and says yes or no; out of the box it knows nothing of how the person
files. Here its top layers are trained on what they decided: their kept and removed filings (the confidence model's
data), the motifs of their confirmed claims, and for those claims the motifs today's shortlist ranks highest that
aren't theirs (hard negatives). Three folds by claim, each tested on the decisions of claims it never saw; then the
reranker's AUC alone on those decisions, before and after, and the confidence model's with the taught one in its
place (pairs.npz from E4, if built).

On the CPU (the GPU is Gemma's), at low priority; a fold at a time, resumable. Hours, so overnight."""
import json
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'e9_tuned.json')  # 'claim key|motif id' -> the taught reranker's P(yes), out of fold
FOLDS = 3
TOP_LAYERS = 6
EPOCHS = 2
BATCH = 8
LR = 1e-5
HARD = 3  # hard negatives per confirmed claim


def examples():
    """(claim, motif id, label, kind): the person's decisions ('decision'), and their confirmed claims' motifs with the
    hard negatives ('truth')"""
    index = mi.load()
    out = {}
    for claim, eid, _, ok in fc.labeled(index):
        out[(mi.key(claim), eid)] = (claim, eid, bool(ok), 'decision')
    data = harness.load()
    for k, c in data['claims'].items():
        for m in c['truth']:
            out.setdefault((k, m), (c['claim'], m, True, 'truth'))
        order = np.argsort(-c['signals']['today'])
        hard = [data['ids'][i] for i in order[:20] if data['ids'][i] not in c['truth']][:HARD]
        for m in hard:
            out.setdefault((k, m), (c['claim'], m, False, 'truth'))
    return list(out.values())


def main():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    os.nice(19)
    torch.set_num_threads(16)
    index = mi.load()
    sig = ms.Signals(index)
    rows = [r for r in examples() if r[1] in sig.at]
    docs = {}
    for claim, eid, _, _ in rows:
        docs[(mi.key(claim), eid)] = sig._document(sig.at[eid], sig.nearest_claims(claim, sig.at[eid], True, 2))
    base = {}
    by_claim = defaultdict(list)
    for claim, eid, _, kind in rows:
        if kind == 'decision':
            by_claim[claim].append(eid)
    for claim, eids in by_claim.items():  # today's reranker on the decisions (cached from training, mostly)
        for eid, p in zip(eids, sig.rerank(claim, [sig.at[e] for e in eids], leave_out=True)):
            base[f'{mi.key(claim)}|{eid}'] = float(p)
    sig.save()
    try:
        with open(OUT) as f:
            tuned = json.load(f)
    except (OSError, ValueError):
        tuned = {}
    claims = sorted({mi.key(r[0]) for r in rows})
    random.Random(9).shuffle(claims)
    fold_of = {k: i % FOLDS for i, k in enumerate(claims)}
    tok = AutoTokenizer.from_pretrained(ms.RERANKER, padding_side='left')
    yes, no = tok.convert_tokens_to_ids('yes'), tok.convert_tokens_to_ids('no')

    def text(claim, eid):
        return ms.rerank_text(claim, docs[(mi.key(claim), eid)])

    for f in range(FOLDS):
        test = [r for r in rows if fold_of[mi.key(r[0])] == f and r[3] == 'decision']
        if all(f'{mi.key(c)}|{e}' in tuned for c, e, _, _ in test):
            continue
        train = [r for r in rows if fold_of[mi.key(r[0])] != f]
        model = AutoModelForCausalLM.from_pretrained(ms.RERANKER, dtype=torch.float32)
        n_layers = model.config.num_hidden_layers
        top = {f'layers.{i}.' for i in range(n_layers - TOP_LAYERS, n_layers)}
        for name, p in model.named_parameters():
            p.requires_grad = any(t in name for t in top) or name.endswith('model.norm.weight')
        opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=0.01)
        model.train()
        rng = random.Random(f)
        for epoch in range(EPOCHS):
            rng.shuffle(train)
            total = 0.0
            for i in range(0, len(train), BATCH):
                part = train[i:i + BATCH]
                batch = tok([text(c, e) for c, e, _, _ in part], padding=True, truncation=True, max_length=768,
                            return_tensors='pt')
                logits = model(**batch).logits[:, -1, :]
                pair = torch.stack([logits[:, no], logits[:, yes]], 1).float()
                loss = torch.nn.functional.cross_entropy(pair, torch.tensor([int(y) for _, _, y, _ in part]))
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                total += float(loss) * len(part)
                if (i // BATCH) % 50 == 0:
                    print(f'E9 fold {f} epoch {epoch} {i}/{len(train)} loss {float(loss):.3f}', flush=True)
            print(f'E9 fold {f} epoch {epoch} mean loss {total / len(train):.3f}', flush=True)
        model.eval()
        with torch.no_grad():
            for i in range(0, len(test), BATCH):
                part = test[i:i + BATCH]
                batch = tok([text(c, e) for c, e, _, _ in part], padding=True, truncation=True, max_length=768,
                            return_tensors='pt')
                logits = model(**batch).logits[:, -1, :]
                p = torch.stack([logits[:, no], logits[:, yes]], 1).float().log_softmax(1)[:, 1].exp().tolist()
                for (c, e, _, _), v in zip(part, p):
                    tuned[f'{mi.key(c)}|{e}'] = round(v, 5)
        with open(OUT + '.tmp', 'w') as fh:
            json.dump(tuned, fh)
        os.replace(OUT + '.tmp', OUT)
        del model, opt
    report(rows, base, tuned)


def report(rows, base, tuned):
    from sklearn.metrics import roc_auc_score
    dec = [(f'{mi.key(c)}|{e}', y) for c, e, y, k in rows if k == 'decision' and f'{mi.key(c)}|{e}' in tuned]
    y = np.array([v for _, v in dec])
    line = (f"E9 reranker alone on {len(dec)} decisions held out by claim: AUC {roc_auc_score(y, [base[k] for k, _ in dec]):.3f}"
            f" -> {roc_auc_score(y, [tuned[k] for k, _ in dec]):.3f} taught")
    print(line, flush=True)
    harness.note(line)
    pairs = os.path.join(harness.EXP, 'pairs.npz')
    if os.path.exists(pairs):
        d = np.load(pairs)
        X = d['X'].copy()
        col = fc.FEATURES.index('rerank') if X.shape[1] == len(fc.FEATURES) else None
        keys = [f'{mi.key(str(c))}|{m}' for c, m in zip(d['claims'], d['motifs'])]
        if col is not None and all(k in tuned for k in keys):
            t = fc.evaluate(d['X'], d['y'], list(d['g']))
            X[:, col] = fc.logit(np.array([tuned[k] for k in keys]))
            u = fc.evaluate(X, d['y'], list(d['g']))
            line = f"E9 confidence model with the taught reranker: AUC {t['auc']} -> {u['auc']}"
        else:
            line = 'E9 confidence model: pairs.npz built on other features or claims; not compared'
        print(line, flush=True)
        harness.note(line)


if __name__ == '__main__':
    main()
    print('DONE', flush=True)
