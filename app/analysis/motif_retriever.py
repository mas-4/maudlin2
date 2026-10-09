"""The motif shortlist for filing a claim (Oct 7): which motifs the filing judge (motif_index.name_claim) gets to choose
from. Until then the closest 8 by one embedding of each motif's text (motif_index.closest); a motif the person would
have filed the claim under was often not among them, so they added it by hand.

Each motif is weighed against the claim by a few plain measures (FACTS): how alike its text is (as closest() reads
it), its name and note alone, its nearest claim, the center of its claims, its size, and the best of those for the
motifs next to it by rests-on links. A logistic regression trained on the person's confirmed filings weighs them
(train(), daily, seconds); the top SHOWN, then what they rest on and what rests on them (up to TREE_MORE more), are shown.

Tested on the person's 766 confirmed filings, each claim held out of training and of its motifs' examples: the
shortlist held 74% of their motifs (today's 8: 60%) and 61% of those they had added by hand (40%), at about 12
motifs instead of 8. Without the weights (too few filings, a failed embedding) filing falls back to closest().

The learned shortlist (Oct 8, from the filing experiments, docs/filing-experiments.md): the same weighing over every
signal of motif_signals.py too (keywords, the note alone, the claim's bare shape, its nearest filed claims' votes, a
second embedder, the person's groups, the news taken out, the claim's layers), trained daily the same way on the
person's confirmed claims (train_learned). Held out, the weighted signals put 82.3% of the person's motifs in the top
12 before the news and the layers were added, against 79.6% for the plain weights. It's used only while its own held-out
test beats theirs; else the plain weights."""
import json
from collections import defaultdict
from datetime import datetime as dt
from datetime import timedelta as td

import numpy as np

from app.analysis import motif_index as mi
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

WEIGHTS = f'{Config.data}/motif_retriever.json'
FACTS = ['text', 'name and note', 'nearest claim', 'center of claims', 'size', 'tree']
SHOWN = 8  # motifs by score
TREE_MORE = 6  # ...and up to this many of what they rest on and what rests on them
RETRAIN = td(days=1)
MIN_FILINGS = 100  # confirmed filings needed to train
EMBED_DIM = 1024  # mxbai-embed-large; the static fallback model's vectors aren't what the weights were trained on


def _text(e: dict, leave_out: str | None = None) -> str:
    """A motif as closest() embeds it (its name, note, phrases and two claims), without one claim if asked"""
    own = [x['claim'] for x in e['claims'] if mi.key(x['claim']) != leave_out][-2:]
    return mi.described(e) + '. ' + '; '.join(e.get('phrases', [])[:5]) + '. ' + '; '.join(c[:120] for c in own)


class Vectors:
    """Embeddings for a run, each text embedded once (the embedder's own cache keeps them between runs)"""

    def __init__(self):
        self.seen = {}

    def __call__(self, texts: list[str]) -> np.ndarray:
        from app.narratives import embed
        todo = [t for t in dict.fromkeys(texts) if t not in self.seen]
        if todo:
            got = embed(todo)
            if self.seen and got.shape[1] != len(next(iter(self.seen.values()))):
                # embed() falls back to a smaller static model when Ollama fails: never mix the two in one run
                raise RuntimeError('embeddings from two different models in one run (Ollama failed meanwhile?)')
            for t, v in zip(todo, got):
                self.seen[t] = v
        return np.array([self.seen[t] for t in texts])


def facts(entries: list[dict], claim: str, vec: Vectors, leave_out: bool = False) -> np.ndarray:
    """FACTS for each motif against the claim (one row each). leave_out: the claim isn't counted as one of its motifs'
    own (training on claims already filed)"""
    k = mi.key(claim)
    q = vec([claim])[0]
    texts = [_text(e, k if leave_out else None) for e in entries]
    text = vec(texts) @ q
    name = vec([mi.described(e) for e in entries]) @ q
    near, center, size = np.full(len(entries), -1.0), np.zeros(len(entries)), np.zeros(len(entries))
    for n, e in enumerate(entries):
        own = list(dict.fromkeys(c['claim'] for c in e['claims'] if not (leave_out and mi.key(c['claim']) == k)))
        size[n] = np.log1p(len(own))
        if own:
            v = vec(own)
            near[n] = float((v @ q).max())
            c = v.mean(0)
            center[n] = float(c @ q / (np.linalg.norm(c) + 1e-9))
    best = np.maximum(name, near)
    at = {e['id']: n for n, e in enumerate(entries)}
    tree = _tree(entries, at)
    treeb = np.array([max([best[x] for x in tree[n]], default=-1.0) for n in range(len(entries))])
    return np.stack([text, name, near, center, size, treeb], 1)


def _tree(entries: list[dict], at: dict) -> list[set]:
    """What each motif rests on and what rests on it, as positions"""
    up = [[at[p] for p in mi.parents_of(e) if p in at] for e in entries]
    down = defaultdict(list)
    for n, ps in enumerate(up):
        for p in ps:
            down[p].append(n)
    return [set(up[n]) | set(down[n]) for n in range(len(entries))]


def train(index: dict | None = None) -> dict | None:
    """The weights, from every claim the person confirmed under a motif (those motifs against the rest); None with too
    few. Saved to WEIGHTS"""
    from sklearn.linear_model import LogisticRegression
    index = index if index is not None else mi.load()
    entries = [e for e in mi.live(index) if e['claims']]
    truth = defaultdict(set)
    text = {}
    for n, e in enumerate(entries):
        for c in e['claims']:
            if c.get('checked') == 'yes':
                truth[mi.key(c['claim'])].add(n)
                text[mi.key(c['claim'])] = c['claim']
    if sum(len(v) for v in truth.values()) < MIN_FILINGS:
        return None
    vec = Vectors()
    vec(list(text.values()))  # in one go
    if next(iter(vec.seen.values())).shape[0] != EMBED_DIM:
        logger.warning("Motif retriever: not trained (embeddings aren't mxbai's)")
        return None
    X = np.concatenate([facts(entries, text[k], vec, leave_out=True) for k in truth])
    y = np.concatenate([[m in truth[k] for m in range(len(entries))] for k in truth])
    mu, sd = X.mean(0), X.std(0) + 1e-9
    model = LogisticRegression(max_iter=2000, class_weight='balanced').fit((X - mu) / sd, y)
    w = model.coef_[0] / sd
    out = {'weights': dict(zip(FACTS, w.round(5).tolist())), 'bias': round(float(model.intercept_[0] - mu @ w), 5),
           'trained_on': int(y.sum()), 'claims': len(truth), 'at': dt.now().isoformat(timespec='seconds')}
    write_json(WEIGHTS, out, indent=1)
    logger.info("Motif retriever trained on %d filings: %s", out['trained_on'], out['weights'])
    return out


def weights() -> dict | None:
    """The current weights, retrained when a day old (or missing)"""
    w = read_json(WEIGHTS, None)
    if not w or dt.now() - dt.fromisoformat(w['at']) > RETRAIN:
        try:
            w = train() or w
        except Exception as e:  # noqa: BLE001 - the old weights (or closest()) will do
            logger.warning("Motif retriever: training failed (%s)", e)
    return w


def shortlist(index: dict, claim: str, vec: Vectors, w: dict) -> list[dict]:
    """The motifs to show the filing judge for a claim: the top SHOWN by the weights, then what they rest on and
    what rests on them (up to TREE_MORE); none below motif_index.SHOWN_FLOOR on every likeness (a claim like nothing filed yet
    gets a new motif, as with closest())"""
    k = mi.key(claim)
    entries = [e for e in mi.live(index) if e['claims'] and k not in e.get('not_claims', [])]
    if not entries:
        return []
    F = facts(entries, claim, vec)
    score = F @ np.array([w['weights'][f] for f in FACTS]) + w['bias']
    alike = F[:, :3].max(1) >= mi.SHOWN_FLOOR
    order = [int(i) for i in np.argsort(-score) if alike[i]]
    top = order[:SHOWN]
    tree = _tree(entries, {e['id']: n for n, e in enumerate(entries)})
    more = sorted({x for m in top for x in tree[m] if x not in top and alike[x]}, key=lambda x: -score[x])[:TREE_MORE]
    return [entries[i] for i in top + more]


LEARNED = f'{Config.data}/motif_shortlist_learned.json'
LEARNED_TOP = 12  # the held-out test's measure: the person's motifs among the top this many
LEARNED_FOLDS = 5


def learned_features() -> list[str]:
    from app.analysis import motif_signals as ms
    return ['today'] + FACTS + ms.CHEAP


def signal_rows(sig, claim: str, w: dict, leave_out: bool, ask: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """(every signal against each of sig's motifs, the plain FACTS) for a claim"""
    from app.analysis import motif_signals as ms
    F = facts(sig.entries, claim, sig.vec, leave_out=leave_out)
    today = F @ np.array([w['weights'][f] for f in FACTS]) + w['bias']
    cheap = sig.cheap(claim, leave_out=leave_out, ask=ask)
    return np.column_stack([today, F] + [cheap[c] for c in ms.CHEAP]), F


def train_learned(index: dict | None = None) -> dict | None:
    """The learned shortlist's weights from the person's confirmed claims in their motifs, with its held-out test
    against the plain weights; saved to LEARNED"""
    from sklearn.linear_model import LogisticRegression

    from app.analysis import motif_signals as ms
    index = index if index is not None else mi.load()
    w = weights()
    if not w:
        return None
    sig = ms.Signals(index, Vectors())
    truth, text = defaultdict(set), {}
    for n, e in enumerate(sig.entries):
        if 'done' in e:
            for c in e['claims']:
                if c.get('checked') == 'yes':
                    truth[mi.key(c['claim'])].add(n)
                    text[mi.key(c['claim'])] = c['claim']
    if sum(len(v) for v in truth.values()) < MIN_FILINGS:
        return None
    sig.prepare(list(text.values()))
    keys = sorted(truth)
    rows = {k: signal_rows(sig, text[k], w, leave_out=True)[0] for k in keys}
    sig.save()
    labels = {k: np.array([m in truth[k] for m in range(len(sig.entries))]) for k in keys}

    def fit(ks):
        X = np.concatenate([rows[k] for k in ks])
        y = np.concatenate([labels[k] for k in ks])
        mu, sd = X.mean(0), X.std(0) + 1e-9
        return LogisticRegression(max_iter=3000, class_weight='balanced', C=0.5).fit((X - mu) / sd, y), mu, sd

    found = {'plain': 0, 'learned': 0}
    total = sum(len(truth[k]) for k in keys)
    for f in range(LEARNED_FOLDS):
        test = keys[f::LEARNED_FOLDS]
        model, mu, sd = fit([k for k in keys if k not in set(test)])
        for k in test:
            for name, score in (('plain', rows[k][:, 0]), ('learned', model.decision_function((rows[k] - mu) / sd))):
                top = set(np.argsort(-score)[:LEARNED_TOP].tolist())
                found[name] += len(truth[k] & top)
    model, mu, sd = fit(keys)
    out = {'features': learned_features(), 'coef': model.coef_[0].round(6).tolist(), 'bias': float(model.intercept_[0]),
           'mu': mu.round(6).tolist(), 'sd': sd.round(6).tolist(), 'claims': len(keys), 'filings': total,
           'test': {f'plain top {LEARNED_TOP}': round(found['plain'] / total, 3),
                    f'learned top {LEARNED_TOP}': round(found['learned'] / total, 3)},
           'at': dt.now().isoformat(timespec='seconds')}
    write_json(LEARNED, out, indent=1)
    logger.info("Motif shortlist learned on %d claims: held out, %s", len(keys), out['test'])
    from app.analysis import filing_confidence
    filing_confidence.record('shortlist', top12=out['test'].get('learned top 12'), plain_top12=out['test'].get('plain top 12'),
                             claims=len(keys))
    return out


def learned(retrain: bool = False) -> dict | None:
    """The learned shortlist's weights if they're for today's signals and beat the plain weights held out (retrained
    when a day old, only if `retrain`: the hourly run's nightly filing); else None"""
    L = read_json(LEARNED, None)
    if retrain and (not L or dt.now() - dt.fromisoformat(L['at']) > RETRAIN or L.get('features') != learned_features()):
        try:
            L = train_learned() or L
        except Exception as e:  # noqa: BLE001 - the plain weights will do
            logger.warning("Motif shortlist: learning failed (%s)", e)
    if not L or L.get('features') != learned_features():
        return None
    t = L['test']
    return L if t[f'learned top {LEARNED_TOP}'] > t[f'plain top {LEARNED_TOP}'] else None


def learned_shortlist(index: dict, claim: str, sig, w: dict, L: dict) -> list[dict]:
    """shortlist() by the learned weights over every signal (sig: a motif_signals.Signals of this index)"""
    k = mi.key(claim)
    entries = sig.entries
    if not entries:
        return []
    X, F = signal_rows(sig, claim, w, leave_out=False)
    score = ((X - np.array(L['mu'])) / np.array(L['sd'])) @ np.array(L['coef']) + L['bias']
    alike = (F[:, :3].max(1) >= mi.SHOWN_FLOOR) & np.array([k not in e.get('not_claims', []) for e in entries])
    order = [int(i) for i in np.argsort(-score) if alike[i]]
    top = order[:SHOWN]
    tree = _tree(entries, {e['id']: n for n, e in enumerate(entries)})
    more = sorted({x for m in top for x in tree[m] if x not in top and alike[x]}, key=lambda x: -score[x])[:TREE_MORE]
    return [entries[i] for i in top + more]


def describe() -> str:
    w = read_json(WEIGHTS, None)
    return json.dumps(w) if w else 'not trained'
