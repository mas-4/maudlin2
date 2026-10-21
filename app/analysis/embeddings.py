"""Every embedding the app makes, in one place (Oct 21, Fable's architecture review: three embed() functions had grown,
each with its own loading and fallback). Three ways to get vectors:

  ollama(texts, model, cache, keep_days)  a model served by the local Ollama, cached by text and model in a SQLite
                                          file; used for stories (mxbai), narratives and the motif index (mxbai), and
                                          the filing signals (nomic, Qwen3-Embedding 8B, Arctic 2)
  static(texts, name)                     a model2vec static model on the CPU, numpy only: the stories' and news
                                          filter's potion-base-8M, and the narratives' fallback potion-base-32M
  text(texts)                             mxbai for posts, claims and motifs (narratives.embed), tried twice, then the
                                          static model, unit vectors either way

The callers keep their own names (clustering.embed and ollama_embed, narratives.embed), which the tests stand in for.

Caches. Each use keeps its own file, since the same model is kept for different lengths of time by different uses
(mxbai: seven days for stories, four for narratives). Several models may share a file: unused vectors are dropped per
model (until Oct 21 the drop ignored the model, so the narratives' four days also cut the filing signals' thirty, in
the file they share). Deleted rows leave free pages that SQLite fills again; `python -m app.analysis.embeddings
vacuum` gives the space back to the disk when the file is idle."""
import hashlib
import os
import sqlite3
import sys
import time

import numpy as np

from app.utils import get_logger

logger = get_logger(__name__)

STORY_MODEL = 'mxbai-embed-large'
STORY_CACHE_DAYS = 7  # cached vectors unused this long are dropped
TEXT_CACHE_DAYS = 4  # narratives and the motif index
TEXT_FALLBACK = 'minishlab/potion-base-32M'

# Embeddings on the CPU (Oct 8): on the GPU, each embedding model loaded beside the filing model pushed it out of the
# card's memory, and it was loaded again a moment later (in six hours that day, gemma4:26b 242 times, mxbai 236 and
# nomic 130: about nine minutes an hour of loading). On the 24 cores, mxbai embeds 27 texts a second and nomic 61:
# a run's new texts in well under a minute (most are cached anyway). But not a bulk job: on Oct 9 the 4 AM narrative
# report's 101,520 posts would have taken an hour on the CPU, and the run was stopped at its 45-minute limit. A call
# with BULK or more texts to embed uses the GPU (one load of the embedder, then the filing model loads again once).
EMBED_OPTIONS = {'num_gpu': 0}
BULK = 2000


def story_cache_path() -> str:
    from app.utils import Config
    return os.path.join(Config.data, 'story_embeddings.sqlite')


def text_cache_path() -> str:
    from app.utils import Config
    return os.path.join(Config.data, 'narratives', 'embeddings.sqlite')


def cache(path: str | None = None) -> sqlite3.Connection:
    """A cache file's connection (the stories' by default). Several processes embed at once (the hourly run, the
    reranker teaching, experiments): wait for another's write rather than fail, which sent embed() to its fallback
    model mid-run (Oct 8: vectors of two sizes in one run)"""
    path = path or story_cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, timeout=120)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS vec (key TEXT PRIMARY KEY, model TEXT, used REAL, v BLOB)')
    return con


def ollama(texts: list[str], model: str = STORY_MODEL, cache_path: str | None = None,
           keep_days: float = STORY_CACHE_DAYS, bulk: int = BULK) -> np.ndarray:
    """Unit vectors for `texts` from the local Ollama, cached by text and model (in `cache_path`, the stories' file by
    default); this model's vectors unused for `keep_days` are dropped. `bulk` or more texts to embed: on the GPU."""
    import requests as rq
    from app.analysis.llm import OLLAMA_URL  # an experiment's goes through its lease's gate
    keys = [hashlib.sha1(f'{model}\n{t}'.encode()).hexdigest() for t in texts]
    con = cache(cache_path)
    try:
        found = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            rows = con.execute(f"SELECT key, v FROM vec WHERE key IN ({','.join('?' * len(chunk))})", chunk).fetchall()
            found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in rows})
        missing = [i for i, k in enumerate(keys) if k not in found]
        options = EMBED_OPTIONS if len(missing) < bulk else {}
        for start in range(0, len(missing), 256):
            batch = missing[start:start + 256]
            r = rq.post(f'{OLLAMA_URL}/api/embed', json={'model': model, 'input': [texts[i] for i in batch],
                                                          'options': options}, timeout=600)
            r.raise_for_status()
            for i, v in zip(batch, r.json()['embeddings']):
                v = np.asarray(v, dtype=np.float32)
                found[keys[i]] = v / max(float(np.linalg.norm(v)), 1e-12)
        now = time.time()
        con.executemany('INSERT OR REPLACE INTO vec VALUES (?, ?, ?, ?)',
                        [(k, model, now, found[k].tobytes()) for k in dict.fromkeys(keys)])
        con.execute('DELETE FROM vec WHERE model = ? AND used < ?', (model, now - keep_days * 86400))
        con.commit()
        return np.vstack([found[k] for k in keys])  # none asked: ValueError, as callers have always had it
    finally:
        con.close()


_static = {}


def static(texts: list[str], name: str) -> np.ndarray:
    """Static sentence embeddings (model2vec) from `name`, loaded once per process; not normalized"""
    if name not in _static:
        from model2vec import StaticModel
        _static[name] = StaticModel.from_pretrained(name)
    return _static[name].encode(list(texts))


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def text(texts: list[str]) -> np.ndarray:
    """Unit vectors for posts, claims and motifs: mxbai through Ollama, in the narratives' cache for a few days; tried
    again once after a moment's failure (Ollama loading a model, a busy cache), since a fallback mid-run gives one run
    vectors from two models (Oct 8); then the static model"""
    if not len(texts):  # as it has always ended for none (after a wait and a warning): callers check first
        raise ValueError('nothing to embed')
    error = None
    for attempt in range(2):
        try:
            return ollama(list(texts), cache_path=text_cache_path(), keep_days=TEXT_CACHE_DAYS)
        except Exception as e:  # noqa: BLE001 - whatever it was, the static model below
            error = e
            if not attempt:
                logger.info("Embeddings from Ollama failed once (%s: %s); trying again", type(e).__name__, e)
                time.sleep(5)
    logger.warning("Embeddings from Ollama failed (%s: %s); using %s", type(error).__name__, error, TEXT_FALLBACK)
    return unit(static(texts, TEXT_FALLBACK))


def vacuum(path: str) -> tuple[float, float]:
    """Give a cache's free pages back to the disk: (MB before, MB after). Locks the file while it runs (minutes for
    the narratives' 3.7 GB): for an idle hour"""
    before = os.path.getsize(path) / 1e6
    con = sqlite3.connect(path, timeout=600)
    try:
        con.execute('VACUUM')
    finally:
        con.close()
    return before, os.path.getsize(path) / 1e6


if __name__ == '__main__':
    if sys.argv[1:2] == ['vacuum']:
        for p in sys.argv[2:] or [story_cache_path(), text_cache_path()]:
            print(p, '%.0f MB -> %.0f MB' % vacuum(p))
    else:
        print('usage: python -m app.analysis.embeddings vacuum [cache.sqlite ...]')
