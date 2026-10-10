"""D4 a Tell-Tale Hat list (Oct 10; after Tangherlini and Abello's Tell-Tale Hat, 2017: a folklore index tends itself
by finding where its categories overlap or come apart). Two lists for the person, from scores already made, no GPU:
- overlap: pairs of motifs whose claims the confidence model thinks fit the other one too (glean.json: each filed
  claim scored against the 12 best motifs it isn't in), so the two may be one shape (merge), one may rest on the
  other, or their notes don't draw the line between them. Not the same as shared claims, which are told together
  (claim_map's 'shared'); here the model can't tell them apart. A pair's score: the claims of each scoring at least FIT
  on the other, over the root of the product of their sizes;
- drift: motifs holding many claims the person kept that the confidence model gives little chance (a filing's fit
  below LOW), so the motif the person means and the one its name and note describe have come apart (rename, a new
  note, or a split).
The person's actions are the measure (the share they act on), so this only writes the lists. A first check on the
overlap list: how many of its top pairs the person has already linked (rests on, related) or ruled apart (not the
same), against pairs drawn at random. Written to EXP as d4_tell_tale_hat.json."""
import json
import math
import os
import random
import sys
from collections import Counter

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

OUT = os.path.join(harness.EXP, 'd4_tell_tale_hat.json')
GLEAN = os.path.join(Config.data, 'motifs', 'glean.json')
FIT = 0.7
LOW = 0.3
TOP = 30


def main():
    index = mi.load()
    live = {e['id']: e for e in mi.live(index)}
    glean = json.load(open(GLEAN))
    home = {}
    for e in live.values():
        for c in e['claims']:
            home.setdefault(mi.key(c['claim']), set()).add(e['id'])
    cross = Counter()
    for r in glean['rows']:
        if r['fit'] >= FIT and r['id'] in live:
            for a in home.get(mi.key(r['claim']), ()):
                if a != r['id']:
                    cross[tuple(sorted((a, r['id'])))] += 1
    size = {m: len(e['claims']) for m, e in live.items()}
    score = {p: n / math.sqrt(size[p[0]] * size[p[1]]) for p, n in cross.items() if n >= 2 and size[p[0]] and size[p[1]]}
    related = {tuple(sorted(p)) for p in index.get('related', [])}
    apart = {tuple(sorted(p)) for p in index.get('not_same', [])}

    def ruled(p):
        if mi.resting(index['entries'], *p):
            return 'rests on'
        return 'related' if p in related else 'not the same' if p in apart else None
    top = sorted(score, key=lambda p: -score[p])[:TOP]
    ids = sorted(live)
    rnd = random.Random(1)
    sample = [tuple(sorted(rnd.sample(ids, 2))) for _ in range(5000)]
    drift = []
    for m, e in live.items():
        kept = [c for c in e['claims'] if c.get('checked') == 'yes' and c.get('fit') is not None]
        low = [c for c in kept if c['fit'] < LOW]
        if len(low) >= 2 and len(low) >= 0.25 * len(kept):
            drift.append({'id': m, 'name': e['name'], 'kept': len(kept), 'low': len(low),
                          'claims': [c['claim'] for c in sorted(low, key=lambda c: c['fit'])[:5]]})
    drift.sort(key=lambda d: -d['low'] / d['kept'])
    out = {'overlap': [{'a': a, 'b': b, 'names': [live[a]['name'], live[b]['name']], 'score': round(score[(a, b)], 3),
                        'claims across': cross[(a, b)], 'already': ruled((a, b))} for a, b in top],
           'drift': drift, 'glean_at': glean.get('at'), 'fit': FIT, 'low': LOW}
    json.dump(out, open(OUT, 'w'), indent=1)
    had = Counter(ruled(p) for p in top)
    base = Counter(ruled(p) for p in sample)
    lines = [f"D4 Tell-Tale Hat lists from the glean's scores ({glean.get('at')}): {len(score)} motif pairs with at least "
             f'2 claims fitting across (fit >= {FIT}); of the top {TOP}, already linked or ruled by the person: '
             + ', '.join(f'{k} {v}' for k, v in had.items() if k) + f', none {had[None]}; of random pairs: '
             + ', '.join(f'{k} {v / len(sample):.1%}' for k, v in base.items() if k),
             f'  drift: {len(drift)} motifs with at least a quarter of their kept claims below fit {LOW}']
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    for o in out['overlap'][:TOP]:
        print(f"  {o['score']:.2f} {o['claims across']:>2} {o['names'][0]} / {o['names'][1]}  [{o['already'] or ''}]")
    for d in drift[:15]:
        print(f"  drift {d['low']}/{d['kept']} {d['name']}")


if __name__ == '__main__':
    main()
