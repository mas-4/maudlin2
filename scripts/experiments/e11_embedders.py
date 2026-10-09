"""E11 Every embedder we can run (Oct 8, the person: "try as many models as we reasonably can! Gotta collect 'em all!").
Filing is a search: the claim the query, the motifs the documents. Each embedding model from Ollama's library gives two
signals, as mxbai's do in the shortlist: the claim against each motif's name and note, and against the motif's nearest
claim (the claim held out). Each model's own query and document prefixes, as its card says. Scored by the harness (the
learned weighting's top 8 / 12 / 40 of the person's motifs, grouped folds): each embedder alone (its two signals, no
others), and added to every signal we have. On the CPU (num_gpu 0, at low priority), so it runs beside the hourly run;
each model's vectors cached in OUT_DIR, so a rerun only embeds what's new."""
import os
import sys

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis.llm import OLLAMA_URL  # noqa: E402

OUT_DIR = os.path.join(harness.EXP, 'embedders')
TASK = 'Given a claim people tell about politics or public life, find the recurring story motif it is an instance of'
# model -> (query prefix, document prefix)
MODELS = {
    'mxbai-embed-large': ('Represent this sentence for searching relevant passages: ', ''),
    'nomic-embed-text': ('search_query: ', 'search_document: '),
    'nomic-embed-text-v2-moe': ('search_query: ', 'search_document: '),
    'embeddinggemma:300m': ('task: search result | query: ', 'title: none | text: '),
    'embeddinggemma-2': ('task: search result | query: ', 'title: none | text: '),
    'qwen3-embedding:0.6b': (f'Instruct: {TASK}\nQuery: ', ''),
    'qwen3-embedding:4b': (f'Instruct: {TASK}\nQuery: ', ''),
    'qwen3-embedding:8b': (f'Instruct: {TASK}\nQuery: ', ''),
    'bge-m3': ('', ''),
    'bge-large': ('Represent this sentence for searching relevant passages: ', ''),
    'snowflake-arctic-embed2': ('query: ', ''),
    'granite-embedding:278m': ('', ''),
}
ONLY = [m for m in os.environ.get('ONLY', '').split(',') if m]


def embed(model: str, texts: list[str]) -> np.ndarray:
    """Unit vectors, cached per model and text"""
    path = os.path.join(OUT_DIR, model.replace(':', '_').replace('/', '_') + '.npz')
    cache = dict(np.load(path, allow_pickle=True)['c'].item()) if os.path.exists(path) else {}
    todo = [t for t in dict.fromkeys(texts) if t not in cache]
    for i in range(0, len(todo), 32):
        part = todo[i:i + 32]
        r = rq.post(f'{OLLAMA_URL}/api/embed', timeout=1800, json={
            'model': model, 'input': part, 'truncate': True, 'options': {'num_gpu': 0}, 'keep_alive': '2m'})
        r.raise_for_status()
        for t, v in zip(part, r.json()['embeddings']):
            v = np.asarray(v, dtype=np.float32)
            cache[t] = v / (np.linalg.norm(v) + 1e-9)
        if (i // 32) % 20 == 0:
            os.makedirs(OUT_DIR, exist_ok=True)
            np.savez(path, c=np.array(cache, dtype=object))
            print(f'  {model}: {len(cache)} texts', flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    np.savez(path, c=np.array(cache, dtype=object))
    return np.stack([cache[t] for t in texts])


def signals(model, data):
    qp, dp = MODELS[model]
    ids, entries = data['ids'], data['entries']
    notes = embed(model, [dp + f"{entries[m]['name']}: {entries[m].get('note') or ''}" for m in ids])
    member = {m: [c['claim'] for c in entries[m]['claims']] for m in ids}
    allc = list(dict.fromkeys(c for cs in member.values() for c in cs))
    C = dict(zip(allc, embed(model, [dp + c for c in allc])))
    keys = sorted(data['claims'])
    Q = dict(zip(keys, embed(model, [qp + data['claims'][k]['claim'] for k in keys])))
    M = {m: np.stack([C[c] for c in member[m]]) for m in ids if member[m]}
    own_of = {m: member[m] for m in ids}

    def note(data, k):
        return notes @ Q[k]

    def near(data, k):
        own = data['claims'][k]['claim']
        out = np.zeros(len(ids))
        for i, m in enumerate(ids):
            if m in M:
                s = M[m] @ Q[k]
                keep = [j for j, c in enumerate(own_of[m]) if c != own]
                out[i] = s[keep].max() if keep else 0.0
        return out
    return {f'{model} note': note, f'{model} near': near}


if __name__ == '__main__':
    data = harness.load()
    have = {m['name'] for m in rq.get(f'{OLLAMA_URL}/api/tags', timeout=30).json()['models']}
    for model in ONLY or MODELS:
        if model not in have and f'{model}:latest' not in have:
            print(f'E11 {model}: not pulled, skipped', flush=True)
            continue
        try:
            extra = signals(model, data)
        except Exception as e:  # noqa: BLE001 - the next model
            print(f'E11 {model}: failed ({type(e).__name__}: {e})'[:300], flush=True)
            continue
        r = harness.recall(data, harness.ranks(data, extra, feats=[]))
        line = f'E11 {model} alone: top-8 {r[8]:.1%}, top-12 {r[12]:.1%}, top-40 {r[40]:.1%}'
        print(line, flush=True)
        harness.note(line)
        harness.evaluate(data, extra, label=f'E11 {model} added to every signal')
    print('DONE', flush=True)
