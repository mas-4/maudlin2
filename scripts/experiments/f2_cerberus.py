"""F2 Cerberus: the motifs the machine missed (Oct 11). From Oct 8 to 11 the person added a claim to a second motif
312 times ("also"): the machine had filed it in one and missed the other. Was the missed motif in the claim's shortlist,
so that the judge saw it and said no (or was never asked for a second), or did the shortlist lose it? The production
shortlist's weights (motif_retriever.weights, as Anansi measures it), the claim left out of every motif, on the index
as it is now: where do the motif the person added and the one the machine had chosen land, top 8/12/40?

    f2_cerberus.py      under the GPU lease (embeddings; lease 'cerberus-shortlists'), into the log and the catalog"""
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import e13_richer_telling as e13  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import curation_db as cdb  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f2_cerberus.json')
SINCE = '2026-10-08'
KS = (8, 12, 40)


def alsos() -> list[dict]:
    con = sqlite3.connect(f'file:{cdb.DB}?mode=ro', uri=True)
    out = []
    for (raw,) in con.execute("select action from curation where reverted = 0 and at >= ? order by at", (SINCE,)):
        try:
            a = json.loads(raw)
        except ValueError:
            continue
        out += [{'claim': s['claim'], 'source': s.get('source'), 'target': s.get('target')}
                for s in a.get('steps', [a]) if s.get('action') == 'also' and s.get('claim') and s.get('target')]
    return out


def main():
    entries = mi.live(mi.load())
    at = {e['id']: n for n, e in enumerate(entries)}
    w = mr.weights()
    weights, bias = np.array([w['weights'][f] for f in mr.FACTS]), w['bias']
    vec = mr.Vectors()
    cases = [a for a in alsos() if a['target'] in at]
    ranks = {'added': [], 'chosen': []}
    for i, a in enumerate(cases):
        s = e13.facts(entries, a['claim'], a['claim'], vec) @ weights + bias
        ranks['added'].append(int((s > s[at[a['target']]]).sum()))
        if a.get('source') in at:
            ranks['chosen'].append(int((s > s[at[a['source']]]).sum()))
        if i % 50 == 0:
            print(f'{i}/{len(cases)}', flush=True)
    out = {k: {K: round(float(np.mean(np.array(r) < K)), 3) for K in KS} for k, r in ranks.items() if r}
    json.dump({'cases': len(cases), 'recall': out, 'ranks': ranks}, open(OUT, 'w'))
    line = (f"F2 Cerberus: {len(cases)} motifs the person added as a claim's second (\"also\"); in the production shortlist "
            f"(weights) the one they added lands in the top 8/12/40 {out['added'][8]:.0%}/{out['added'][12]:.0%}/"
            f"{out['added'][40]:.0%}, the one the machine had chosen {out['chosen'][8]:.0%}/{out['chosen'][12]:.0%}/"
            f"{out['chosen'][40]:.0%}")
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
    print('DONE', flush=True)
