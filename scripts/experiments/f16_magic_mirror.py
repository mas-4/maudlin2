"""F16 the Magic Mirror (Oct 12, from Fable's review, "The taught reranker may be hurting"): is the taught reranker
still the fairest? Qwen3-Reranker-0.6B on the CPU, untaught and with the taught layers in use (reranker/taught.pt, Oct
8), on the person's decided filings, each pair's text as the teaching builds it from today's index (mxbai vectors
from the embedder's cache only, never Ollama):

1. Oct 8's teaching's own held-out scores (reranker/held_out.json) against the untaught reranker on the same decisions;
2. forward: the taught reranker in use against the untaught on decisions about claims first decided after that
   teaching.
AUC of each, and a bootstrap over claims for the difference. Paper: maudlin-data/papers/the-magic-mirror.md."""
import json
import os
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = ''  # the CPU only: the card is the filing model's

import numpy as np  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from f14_tyche import Missing, MxbaiCached  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402
from app.analysis import reranker_teach as rt  # noqa: E402
from app.utils.store import read_json  # noqa: E402

OUT = os.path.join(harness.EXP, 'f16_magic_mirror.json')


def first_decided() -> dict:
    """claim key -> when the person first decided anything about it (the curation log, read only)"""
    out = {}
    for r in fc.log_rows():
        if isinstance(r.get('action'), dict):
            got = {}
            fc._decided(r['action'], got, hand=True)
            for k, _ in got:
                out.setdefault(k, r['at'])
    return out


def auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else float('nan')


def compare(rows: list, a: dict, b: dict, boots: int = harness.BOOTS) -> dict:
    """AUC of scores a and b on the decisions in rows, and the bootstrap interval of b - a, claims resampled"""
    keys = [f'{mi.key(c)}|{e}' for c, e, _, _ in rows]
    y = np.array([ok for _, _, ok, _ in rows])
    pa, pb = np.array([a[k] for k in keys]), np.array([b[k] for k in keys])
    claim = np.array([mi.key(c) for c, _, _, _ in rows])
    uniq = np.unique(claim)
    at = {c: np.where(claim == c)[0] for c in uniq}
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(boots):
        idx = np.concatenate([at[c] for c in rng.choice(uniq, len(uniq))])
        diffs.append(auc(y[idx], pb[idx]) - auc(y[idx], pa[idx]))
    lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
    return {'decisions': len(rows), 'claims': len(uniq), 'kept': int(y.sum()), 'a': round(auc(y, pa), 4),
            'b': round(auc(y, pb), 4), 'b - a interval': [round(float(lo), 4), round(float(hi), 4)]}


def main():
    import torch
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 4))
    index = mi.load()
    meta = read_json(rt.META, {})
    held = rt.held_out()
    when = first_decided()
    sig = ms.Signals(index, MxbaiCached())
    rows, texts, missing = [], {}, 0
    for claim, eid, _, kept in fc.labeled(index):
        if eid not in sig.at:
            continue
        try:
            doc = sig._document(sig.at[eid], sig.nearest_claims(claim, sig.at[eid], True, 2))
        except Missing:
            missing += 1
            continue
        rows.append((claim, eid, kept, 'decision'))
        texts[(mi.key(claim), eid)] = ms.rerank_text(claim, doc)
    then = [r for r in rows if f'{mi.key(r[0])}|{r[1]}' in held]
    since = [r for r in rows if f'{mi.key(r[0])}|{r[1]}' not in held and when.get(mi.key(r[0]), '') > meta['at']]
    print(f'{len(rows)} decisions with their text ({missing} without cached vectors, left out); {len(then)} in '
          f"the teaching of {meta['at']}, {len(since)} on claims first decided since", flush=True)
    tok, model = rt._model()
    model.eval()
    yes, no = tok.convert_tokens_to_ids('yes'), tok.convert_tokens_to_ids('no')
    base = rt._score(tok, model, yes, no, then + since, texts)
    print('untaught scored', flush=True)
    tok, model = rt._model()
    model = rt.load_into(model).eval()
    taught = rt._score(tok, model, yes, no, since, texts)
    print('taught scored', flush=True)
    result = {'teaching': meta, 'left out, no cached vectors': missing,
              "the teaching's own decisions: untaught (a) against its held-out scores (b)": compare(then, base, held),
              'forward, claims first decided since: untaught (a) against taught in use (b)': compare(since, base, taught)}
    with open(OUT, 'w') as f:
        json.dump(result, f, indent=1)
    for name, r in list(result.items())[2:]:
        line = (f"F16 {name}: {r['a']:.3f} against {r['b']:.3f} on {r['decisions']} decisions, {r['claims']} claims "
                f"(difference {r['b - a interval'][0]:+.3f} to {r['b - a interval'][1]:+.3f})")
        print(line, flush=True)
        harness.note(line)
    print('DONE', flush=True)


if __name__ == '__main__':
    os.nice(19)
    main()
