"""E5's honest test: for each claim, only the rests-on and related links made before the claim came in (its earliest
date in the index), so no link can have come from the claim itself. Link times from the curation log (relate,
related, parent, kind_of, proposals approved, merges carry links over: counted at the merge); links with no time found
are left out (strict) or kept (lenient)"""
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from e3_e5_bundles_graph import data, ids, at, index, mi  # noqa: E402
from app.analysis import curation_db  # noqa: E402

made = {}


def walk(a, at):
    """Each link a logged action (or a batch's steps) made, with when"""
    if not isinstance(a, dict):
        return
    act = a.get('action')
    pair = None
    if act in ('relate', 'related') and a.get('a') and a.get('b'):
        pair = (a['a'], a['b'])
    elif act in ('parent', 'kind_of') and a.get('id') and a.get('parent') and a.get('on', True) not in (False, 'False'):
        pair = (a['id'], a['parent'])
    if pair:
        made.setdefault(frozenset(pair), at)
    for s in a.get('steps') or []:
        walk(s, at)


for r in curation_db.actions(include_reverted=True):
    walk(r['action'], r['at'])
links = []
for e in data['entries'].values():
    for p in mi.parents_of(e):
        links.append(frozenset((e['id'], p)))
for a, b in index.get('related', []):
    links.append(frozenset((a, b)))
links = list(dict.fromkeys(links))
print(f'{len(links)} links, {sum(1 for l in links if l in made)} with a time in the log', flush=True)
first = {}
for e in data['entries'].values():
    for c in e['claims']:
        k = mi.key(c['claim'])
        if c.get('date'):
            first[k] = min(first.get(k, '9999'), c['date'])


def spread_before(strict):
    def fn(d, k):
        when = first.get(k, '0000')
        nb = defaultdict(set)
        for l in links:
            t = made.get(l)
            if (t is None and strict) or (t is not None and t[:10] >= when):
                continue
            a, b = tuple(l)
            nb[a].add(b)
            nb[b].add(a)
        s = d['claims'][k]['signals']['today']
        z = (s - s.mean()) / (s.std() + 1e-9)
        return np.array([max((z[at[n]] for n in nb.get(m, ()) if n in at), default=-3.0) for m in ids])
    return fn


if __name__ == '__main__':
    harness.evaluate(data, {'x': spread_before(True)}, label='E5 links made before the claim (strict)')
    harness.evaluate(data, {'x': spread_before(False)}, label='E5 links made before the claim (lenient)')
    print('DONE', flush=True)
