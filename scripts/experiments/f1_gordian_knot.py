"""F1 the Gordian Knot: can the machine see where a motif holds two tellings? (Oct 11, the person: "if we can reduce
the corrections i have to do it would be great: if we can incorporate this splitter result".) From Oct 8 to 11 the
person carved 225 new motifs out of claims, 252 of those claims taken out of a motif they had been filed in: the machine
had forced them into the nearest motif because the right one didn't exist yet. Atropos found the seams inside a story
with a normalized cut on its headlines' TF-IDF likeness (cuts under 0.6 were two events 18 of 18 times). Replayed here
on motifs, each as it stood just before the person carved from it (the motif index's saved versions):

    odd one out   for every claim carved out of a motif of 3+ claims: is it the claim least like the rest (mean TF-IDF
                  likeness to the motif's other claims)? Chance is 1 in the motif's size
    seams         the motifs carved from (6+ claims) against motifs of 6+ claims never carved from, as they stand now:
                  does a low cut score pick out the carved ones (AUC)? And where 2+ claims left one motif together, does
                  the best cut put them on one side?

TF-IDF only, on the CPU (the claims' embeddings are cached for four days only; an embeddings arm would need the GPU).

    f1_gordian_knot.py          the replay, into the log and the catalog"""
import json
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import curation_db as cdb  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'f1_gordian_knot.json')
SINCE = '2026-10-08'
MIN_ODD = 3  # claims a motif needs for the odd one out to mean anything
MIN_CUT = 6  # claims a motif needs to be cut; each side keeps CUT_SIDE or more
CUT_SIDE = 2
LINES = (0.6, 0.7, 0.8)  # Atropos's lines


def carvings() -> list[dict]:
    """Every new motif the person made from claims that were in another motif: (at, source motif, its claims moved)"""
    con = sqlite3.connect(f'file:{cdb.DB}?mode=ro', uri=True)
    out = []
    for at, raw in con.execute("select at, action from curation where reverted = 0 and at >= ? order by at", (SINCE,)):
        try:
            a = json.loads(raw)
        except ValueError:
            continue
        for s in a.get('steps', [a]):
            if s.get('action') != 'new_with':
                continue
            by = defaultdict(list)
            for c in s.get('claims', []):
                if c.get('source', '').startswith('M'):
                    by[c['source']].append(c['claim'])
            out += [{'at': at, 'source': src, 'moved': claims, 'name': s.get('name', '')} for src, claims in by.items()]
    return out


class Versions:
    """The motif index as it stood at a time: the latest saved version before it"""

    def __init__(self):
        self.con = sqlite3.connect(f'file:{cdb.DB}?mode=ro', uri=True)
        self.rows = self.con.execute('select id, at from versions order by at').fetchall()
        self.cache = {}

    def before(self, at: str) -> dict | None:
        ids = [i for i, t in self.rows if t < at]
        if not ids:
            return None
        vid = ids[-1]
        if vid not in self.cache:
            blob = self.con.execute('select data from versions where id = ?', (vid,)).fetchone()[0]
            self.cache = {vid: json.loads(cdb._unpack(blob))}  # one at a time: each is a whole index
        return self.cache[vid]


def likeness(texts: list[str], vectorizer) -> np.ndarray:
    X = vectorizer.transform(texts)
    W = (X @ X.T).toarray()
    np.fill_diagonal(W, 0)
    return W


def best_cut(W: np.ndarray) -> tuple[float, np.ndarray] | None:
    """Atropos's normalized cut (s4_story_seams.best_cut), each side CUT_SIDE claims or more"""
    d = W.sum(1) + 1e-9
    L = np.eye(len(W)) - W / np.sqrt(np.outer(d, d))
    _, vecs = np.linalg.eigh(L)
    f = vecs[:, 1] / np.sqrt(d)
    best = None
    for cut in np.unique(np.quantile(f, np.linspace(0.05, 0.95, 37))):
        A = f <= cut
        if A.sum() < CUT_SIDE or (~A).sum() < CUT_SIDE:
            continue
        c = W[np.ix_(A, ~A)].sum()
        ncut = c / (W[A].sum() + 1e-9) + c / (W[~A].sum() + 1e-9)
        if best is None or ncut < best[0]:
            best = (float(ncut), A)
    return best


def auc(pos: list[float], neg: list[float]) -> float:
    """The chance a carved motif's cut scores lower than an uncarved one's"""
    if not pos or not neg:
        return float('nan')
    return float(np.mean([(p < n) + 0.5 * (p == n) for p in pos for n in neg]))


def main():
    from sklearn.feature_extraction.text import TfidfVectorizer
    now = mi.load()
    every = sorted({c['claim'] for e in mi.live(now) for c in e['claims']})
    vectorizer = TfidfVectorizer(stop_words='english', sublinear_tf=True, min_df=1).fit(every)
    cuts, versions = carvings(), Versions()
    odd, ranks, carved, splits = [], [], {}, []
    for k in cuts:
        index = versions.before(k['at'])
        e = (index or {}).get('entries', {}).get(k['source'])
        if not e:
            continue
        texts = list(dict.fromkeys(c['claim'] for c in e['claims']))
        moved = [t for t in k['moved'] if t in texts]
        if len(texts) >= MIN_ODD and moved:
            W = likeness(texts, vectorizer)
            mean = W.sum(1) / (len(texts) - 1)
            order = list(np.argsort(mean))  # least alike first
            for t in moved:
                r = order.index(texts.index(t)) + 1
                odd.append({'motif': k['source'], 'size': len(texts), 'rank': r})
        if len(texts) >= MIN_CUT and k['source'] not in carved:
            got = best_cut(likeness(texts, vectorizer))
            if got:
                carved[k['source']] = got[0]
                if len(moved) >= 2:
                    side = got[1][[texts.index(t) for t in moved]]
                    together = max(side.sum(), (~side).sum()) / len(moved)
                    splits.append({'motif': k['source'], 'moved': len(moved), 'size': len(texts),
                                   'together': round(float(together), 2), 'cut': round(got[0], 3)})
    never = {}
    sources = {k['source'] for k in cuts}
    for e in mi.live(now):
        texts = list(dict.fromkeys(c['claim'] for c in e['claims']))
        if e['id'] not in sources and len(texts) >= MIN_CUT:
            got = best_cut(likeness(texts, vectorizer))
            if got:
                never[e['id']] = got[0]
    ranks = [o['rank'] for o in odd]
    chance = float(np.mean([1 / o['size'] for o in odd])) if odd else 0
    first = float(np.mean([r == 1 for r in ranks])) if odd else 0
    top2 = float(np.mean([r <= 2 for r in ranks])) if odd else 0
    below = {line: (sum(v < line for v in carved.values()), len(carved), sum(v < line for v in never.values()), len(never))
             for line in LINES}
    state = {'odd': odd, 'carved': carved, 'never': never, 'splits': splits, 'carvings': len(cuts)}
    json.dump(state, open(OUT, 'w'))
    line = (f"F1 the Gordian Knot: {len(cuts)} carvings from a motif since Oct 8; the carved claim was its motif's odd one "
            f"out {first:.0%} of {len(odd)} times (chance {chance:.0%}), among the two least alike {top2:.0%}; "
            f"cut scores pick out the {len(carved)} motifs carved from against {len(never)} never carved at AUC "
            f"{auc(list(carved.values()), list(never.values())):.2f}; "
            + '; '.join(f'under {line}: {a}/{b} carved, {c}/{d} never' for line, (a, b, c, d) in below.items())
            + (f"; where 2+ claims left together ({len(splits)} motifs) the best cut kept them on one side "
               f"{np.mean([s['together'] for s in splits]):.0%} of the time" if splits else ''))
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
