"""E1 Subtract the news (docs/filing-experiments.md): the main directions recent headlines vary along are mostly topic
(Iran, Texas, a storm); taken out of the claim, the motif notes and their claims before comparing, what's left should
be closer to framing. Headlines' embeddings (mxbai) from the last days; their top principal components removed; the
claim against each motif's note and its nearest claim (held out) in what's left. Uses the GPU only to embed."""
import sqlite3
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.utils import Config  # noqa: E402

HEADLINES = 6000

data = harness.load()
ids, at = data['ids'], data['at']
vec = mr.Vectors()
con = sqlite3.connect(f'file:{Config.connection_string.removeprefix("sqlite:///")}?mode=ro', uri=True)
titles = [r[0] for r in con.execute('SELECT DISTINCT title FROM headline WHERE title IS NOT NULL ORDER BY last_accessed DESC '
                                    'LIMIT ?', (HEADLINES,))]
print(f'{len(titles)} headlines', flush=True)
H = vec(titles)
mu = H.mean(0)
_, _, Vt = np.linalg.svd(H - mu, full_matrices=False)
entries = data['entries']
notes = vec([entries[m].get('note') or entries[m]['name'] for m in ids])
member = {m: [c['claim'] for c in entries[m]['claims']] for m in ids}
allc = list(dict.fromkeys(c for cs in member.values() for c in cs))
C = dict(zip(allc, vec(allc)))
Q = {k: vec([c['claim']])[0] for k, c in data['claims'].items()}


def project(V, k):
    if k == 0:
        return V / np.linalg.norm(V, axis=-1, keepdims=True)
    U = Vt[:k]
    W = (V - mu) - ((V - mu) @ U.T) @ U
    return W / np.linalg.norm(W, axis=-1, keepdims=True)


def signals(k):
    N = project(notes, k)
    Cp = {c: project(v, k) for c, v in C.items()}

    def note(d, key):
        return N @ project(Q[key], k)

    def near(d, key):
        q = project(Q[key], k)
        mine = d['claims'][key]['claim']
        return np.array([max((float(Cp[c] @ q) for c in member[m] if mi.key(c) != mi.key(mine)), default=-1.0) for m in ids])
    return note, near


if __name__ == '__main__':
    for k in (5, 10, 20, 40):
        note, near = signals(k)
        harness.evaluate(data, {'note minus news': note, 'nearest minus news': near}, label=f'E1 {k} topic directions out')
    print('DONE', flush=True)
