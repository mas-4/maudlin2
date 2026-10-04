"""Real Motif-Index entries (#145) for folklore narratives and fact-checked claims: Stith Thompson's Motif-Index of
Folk-Literature (revised edition, 1955-58), from Katja Mellmann's table of it (data/motifs/tmi.csv, CC BY 4.0;
Mellmann, "Thompson's Motif-Index as CSV File", OSF 2020, doi:10.17605/OSF.IO/XEB67).

The index is about 46,000 numbered motifs, too many to choose from directly, and a list of categories rather than
examples, so nothing to train a classifier on yet. Instead: every entry's wording is embedded once
(mxbai-embed-large), a claim's CANDIDATES closest entries are found by meaning, and the model picks the one the
claim is an instance of, or "none" (a forced choice, as for satire and fact-checks: app/analysis/ties.py). The index
was built from folktales, myths and legends, so many modern claims honestly have no motif; "none" is an answer.

The labelers used to name a motif in their own words, and copied the examples in their prompt (Oct 4: 34 of 94
fact-checks "the false flag"). An entry from the index can't be invented."""
import hashlib
import json
import os
import re

import numpy as np
import pandas as pd

from app.analysis import llm
from app.utils import Config, get_logger

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'motifs')
TABLE = os.path.join(FOLDER, 'tmi.csv')
VECTORS = os.path.join(FOLDER, 'vectors.npy')
PICKS = os.path.join(FOLDER, 'picks.json')  # (claim, candidates) -> the model's pick, kept for good
CANDIDATES = 12
QUERY = 'Represent this sentence for searching relevant passages: '  # mxbai's prefix for a search query
MAX_TEXT = 160

PROMPT = """A claim people are telling or passing on:
{claim}

Entries from Stith Thompson's Motif-Index of Folk-Literature, a catalog of the recurring elements of folktales, \
myths and legends:
{options}

Is the claim, as its tellers tell it, a modern instance of one of these motifs? Judge the story's shape only: \
not whether it is true, and not whether you agree with it. Pick the entry it plainly is an instance of (the same \
situation or trick, with modern people and things in place of the old ones), or "none" if none of them really \
describes it. Most news claims have no motif: "none" is a good answer."""

_index = None


def table() -> pd.DataFrame:
    """code, chapter letter, the entry's wording (without its number), its section."""
    df = pd.read_csv(TABLE, dtype=str).fillna('')
    df['text'] = df['MOTIF'].str.replace(r'^\S+\.\s*', '', regex=True).str.strip()
    df['letter'] = df['code'].str[0]
    df['section'] = df['section ("tens")'].str.replace(r'^\S+\.\s*', '', regex=True).str.strip()
    return df[df['text'] != ''].drop_duplicates('code').reset_index(drop=True)[['code', 'letter', 'text', 'section']]


def index() -> tuple[pd.DataFrame, np.ndarray]:
    """The table and its entries' unit vectors (embedded once, then read from VECTORS)."""
    global _index
    if _index is None:
        df = table()
        stamp = hashlib.sha1('\n'.join(df['code'] + df['text']).encode()).hexdigest()[:12]
        meta = VECTORS + '.json'
        if os.path.exists(VECTORS) and os.path.exists(meta) and json.load(open(meta)).get('stamp') == stamp:
            v = np.load(VECTORS).astype(np.float32)
        else:
            from app.analysis.clustering import ollama_embed
            texts = [f"{t} ({s})" if s and s.lower() not in t.lower() else t for t, s in zip(df['text'], df['section'])]
            v = ollama_embed(texts, cache=os.path.join(FOLDER, 'embeddings.sqlite'), keep_days=3650)
            np.save(VECTORS, v.astype(np.float16))
            json.dump({'stamp': stamp, 'model': 'mxbai-embed-large', 'entries': len(df)}, open(meta, 'w'))
        _index = (df, v)
    return _index


def candidates(claims: list[str], k: int = CANDIDATES) -> list[list[int]]:
    """For each claim, the rows of its k closest index entries."""
    from app.analysis.clustering import ollama_embed
    df, v = index()
    q = ollama_embed([QUERY + c for c in claims], cache=os.path.join(FOLDER, 'embeddings.sqlite'), keep_days=60)
    sims = q @ v.T
    return [list(np.argsort(-row)[:k]) for row in sims]


def pick(claims: list[str], limit: int = 200) -> list[dict | None]:
    """For each claim, the index entry it's an instance of ({code, letter, text}) or None. At most `limit` new
    model calls."""
    if not claims or llm.backend() is None:
        return [None] * len(claims)
    df, _ = index()
    try:
        cache = json.load(open(PICKS))
    except (OSError, ValueError):
        cache = {}
    out, asked = [], 0
    for claim, rows in zip(claims, candidates(claims)):
        codes = [df['code'][r] for r in rows]
        key = hashlib.sha1(f"{PROMPT}\n{claim}\n{' '.join(codes)}".encode()).hexdigest()[:16]
        if key not in cache and asked < limit and claim.strip():
            asked += 1
            options = '\n'.join(f"{df['code'][r]}: {df['text'][r][:MAX_TEXT]}" for r in rows)
            schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 300},
                                                       "entry": {"type": "string", "enum": codes + ['none']}},
                      "required": ["reason", "entry"]}
            answer = llm.complete_json(PROMPT.format(claim=claim, options=options), schema, max_tokens=200)
            if answer:
                cache[key] = answer.get('entry', 'none')
        code = cache.get(key, 'none')
        row = df[df['code'] == code]
        out.append(None if code == 'none' or row.empty else
                   {'code': code, 'letter': code[0], 'text': row['text'].iloc[0][:MAX_TEXT]})
    os.makedirs(FOLDER, exist_ok=True)
    with open(PICKS, 'w') as f:
        json.dump(cache, f)
    logger.info("Motifs: %d of %d claims are instances of an index entry (%d new model calls)",
                sum(1 for o in out if o), len(claims), asked)
    return out
