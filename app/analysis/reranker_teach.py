"""The reranker taught the person's taste (experiment E9, Oct 8: on their decisions held out by claim, AUC 0.765 ->
0.796 alone; in the filing confidence model 0.887 -> 0.890). Qwen3-Reranker-0.6B's top TOP_LAYERS layers trained on
what they decided: their kept and removed filings, the motifs of their confirmed claims, and for those claims the
motifs the shortlist ranks highest that aren't theirs (hard negatives).

Two products, both kept in FOLDER:
  - the layers it changed, trained on everything (taught.pt, about 190 MB at half precision), which motif_signals loads
    over the base model to score new filings;
  - each decision's score from a model that never saw that claim (held_out.json, FOLDS folds by claim), for training
    the confidence model: scores from a reranker that learned those very decisions would look better than they are,
    and the confidence model would trust them too much.
On the CPU (the card is the filing model's) at low priority, weekly (due()), started from the hourly run at night as a
process of its own: about two and a half hours.

    python -m app.analysis.reranker_teach        # teach now"""
import json
import os
import random
from datetime import datetime as dt, timedelta as td

import numpy as np

from app.analysis import filing_confidence as fc
from app.analysis import motif_index as mi
from app.analysis import motif_retriever as mr
from app.analysis import motif_signals as ms
from app.utils import get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

FOLDER = os.path.join(ms.FOLDER, 'reranker')
TAUGHT = os.path.join(FOLDER, 'taught.pt')
META = os.path.join(FOLDER, 'taught.json')  # {'at', 'examples', 'decisions'}
HELD_OUT = os.path.join(FOLDER, 'held_out.json')  # 'claim key|motif id' -> P(yes) from a model that never saw the claim
TOP_LAYERS = 6
EPOCHS = 2
BATCH = 8
LR = 1e-5
HARD = 3  # hard negatives per confirmed claim
FOLDS = 3
EVERY = td(days=7)
MIN_NEW = 50  # decisions made since the last teaching, before teaching again is worth it


def tag() -> str:
    """Which reranker scores come from: 'base', or the taught one's date (scores are cached per reranker)"""
    meta = read_json(META, {})
    return meta.get('at', 'base') if os.path.exists(TAUGHT) else 'base'


def examples(index: dict) -> list[tuple[str, str, bool, str]]:
    """(claim, motif id, label, kind): the person's decisions, then their confirmed claims' motifs and hard negatives"""
    out = {}
    for claim, eid, _, ok in fc.labeled(index):
        out[(mi.key(claim), eid)] = (claim, eid, bool(ok), 'decision')
    entries = [e for e in mi.live(index) if e['claims']]
    w = mr.weights()
    coef = np.array([w['weights'][f] for f in mr.FACTS]) if w else None
    vec = mr.Vectors()
    truth = {}
    for e in entries:
        if fc.yours(e):
            for c in e['claims']:
                if c.get('checked') == 'yes':
                    truth.setdefault(c['claim'], set()).add(e['id'])
    for claim, ids in truth.items():
        k = mi.key(claim)
        for eid in ids:
            out.setdefault((k, eid), (claim, eid, True, 'truth'))
        if coef is None:
            continue
        score = mr.facts(entries, claim, vec, leave_out=True) @ coef
        hard = [entries[i]['id'] for i in np.argsort(-score)[:20] if entries[i]['id'] not in ids][:HARD]
        for eid in hard:
            out.setdefault((k, eid), (claim, eid, False, 'truth'))
    return list(out.values())


def _model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(ms.RERANKER, padding_side='left')
    model = AutoModelForCausalLM.from_pretrained(ms.RERANKER, dtype=torch.float32)
    n = model.config.num_hidden_layers
    top = {f'layers.{i}.' for i in range(n - TOP_LAYERS, n)}
    for name, p in model.named_parameters():
        p.requires_grad = any(t in name for t in top) or name.endswith('model.norm.weight')
    return tok, model


def _train(rows: list, texts: dict, seed: int):
    import torch
    tok, model = _model()
    yes, no = tok.convert_tokens_to_ids('yes'), tok.convert_tokens_to_ids('no')
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=0.01)
    model.train()
    rows = list(rows)
    rng = random.Random(seed)
    for epoch in range(EPOCHS):
        rng.shuffle(rows)
        for i in range(0, len(rows), BATCH):
            part = rows[i:i + BATCH]
            batch = tok([texts[(mi.key(c), e)] for c, e, _, _ in part], padding=True, truncation=True, max_length=768,
                        return_tensors='pt')
            logits = model(**batch).logits[:, -1, :]
            pair = torch.stack([logits[:, no], logits[:, yes]], 1).float()
            loss = torch.nn.functional.cross_entropy(pair, torch.tensor([int(y) for _, _, y, _ in part]))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        logger.info("Reranker teaching: pass %d of %d done (seed %d)", epoch + 1, EPOCHS, seed)
    model.eval()
    return tok, model, yes, no


def _score(tok, model, yes, no, rows, texts) -> dict:
    import torch
    out = {}
    with torch.no_grad():
        for i in range(0, len(rows), BATCH):
            part = rows[i:i + BATCH]
            batch = tok([texts[(mi.key(c), e)] for c, e, _, _ in part], padding=True, truncation=True, max_length=768,
                        return_tensors='pt')
            logits = model(**batch).logits[:, -1, :]
            p = torch.stack([logits[:, no], logits[:, yes]], 1).float().log_softmax(1)[:, 1].exp().tolist()
            out.update({f'{mi.key(c)}|{e}': round(v, 5) for (c, e, _, _), v in zip(part, p)})
    return out


def teach():
    """Held-out scores for every decision (FOLDS models), then the taught layers from all of them"""
    import torch
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 4))
    index = mi.load()
    sig = ms.Signals(index)
    rows = [r for r in examples(index) if r[1] in sig.at]
    texts = {(mi.key(c), e): ms.rerank_text(c, sig._document(sig.at[e], sig.nearest_claims(c, sig.at[e], True, 2)))
             for c, e, _, _ in rows}
    claims = sorted({mi.key(r[0]) for r in rows})
    random.Random(9).shuffle(claims)
    fold = {k: i % FOLDS for i, k in enumerate(claims)}
    held = {}
    for f in range(FOLDS):
        test = [r for r in rows if fold[mi.key(r[0])] == f and r[3] == 'decision']
        held.update(_score(*_train([r for r in rows if fold[mi.key(r[0])] != f], texts, f), test, texts))
    tok, model, _, _ = _train(rows, texts, FOLDS)
    os.makedirs(FOLDER, exist_ok=True)
    kept = {n: p.detach().half() for n, p in model.named_parameters() if p.requires_grad}
    torch.save(kept, TAUGHT + '.tmp')
    os.replace(TAUGHT + '.tmp', TAUGHT)
    write_json(HELD_OUT, held)
    decisions = sum(r[3] == 'decision' for r in rows)
    write_json(META, {'at': dt.now().isoformat(timespec='seconds'), 'examples': len(rows), 'decisions': decisions})
    logger.info("Reranker taught on %d examples (%d decisions); held-out scores for %d", len(rows), decisions, len(held))


def load_into(model):
    """The taught layers over a base reranker loaded by motif_signals (nothing if none yet)"""
    import torch
    if os.path.exists(TAUGHT):
        state = torch.load(TAUGHT, map_location='cpu')
        model.load_state_dict({k: v.to(next(model.parameters()).dtype) for k, v in state.items()}, strict=False)
    return model


def held_out() -> dict:
    return read_json(HELD_OUT, {})


def due() -> bool:
    """A week since the last teaching (or never) and enough new decisions to learn from"""
    meta = read_json(META, {})
    if not meta:
        return True
    if dt.now() - dt.fromisoformat(meta['at']) < EVERY:
        return False
    return len(fc.decisions()) - meta.get('decisions', 0) >= MIN_NEW


if __name__ == '__main__':
    os.nice(19)
    teach()
    print(json.dumps(read_json(META, {})))
