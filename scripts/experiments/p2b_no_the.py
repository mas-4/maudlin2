"""P2b the naming rules with one line more (Oct 10). With the praxis's naming rules (in production since Oct 10, P2)
64 of Gemma's 101 names began with "The" (The Villainous Turn, The Great Unraveling), which the person's names rarely
do. The same 101 motifs named again with the production rules plus "no leading The unless it is part of the idiom";
measured as P2 measured them (likeness to the person's names, abstract labels, words) and the share starting with "The".
Resumable; caches in P2's file."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import p2_praxis_oct10 as p2  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

NO_THE = mi.NAME_RULES + ';\n- no leading "The" unless it is part of the idiom'
ARMS = {'new naming': None, 'new naming, no The': NO_THE}


def main():
    from app.narratives import embed
    saved = json.load(open(p2.OUT))
    cases = p2.renames()
    got = saved.setdefault('new naming, no The', {})
    todo = [c for c in cases if c['id'] not in got]
    asks = llm.parallel(lambda c: llm.complete_json(p2.NAME_PROMPT.format(
        claims='\n'.join(f'- {x}' for x in c['claims']), rules=NO_THE), p2.NAME_SCHEMA, max_tokens=100,
        model=ms.JUDGE_MODEL), todo)
    for c, a in zip(todo, asks):
        if a and a.get('name'):
            got[c['id']] = a['name'].strip()
    json.dump(saved, open(p2.OUT, 'w'))
    scored = [c for c in cases if c['person'].lower() not in NO_THE.lower() and all(c['id'] in saved[a] for a in ARMS)]
    P = embed([c['person'] for c in scored])
    lines = [f'P2b the naming rules with "no leading The", {len(scored)} motifs the person renamed:']
    for arm in ARMS:
        names = [saved[arm][c['id']] for c in scored]
        sim = (embed(names) * P).sum(1)
        lines.append(f'  {arm}: like the person\'s {sim.mean():.3f}; abstract {np.mean([bool(p2.ABSTRACT.search(n)) for n in names]):.0%}; '
                     f'{np.mean([len(n.split()) for n in names]):.1f} words; start with "The" '
                     f'{np.mean([n.split()[0].lower() == "the" for n in names]):.0%}')
    for c in scored[:15]:
        lines.append(f"    {saved['new naming'][c['id']]!r} -> {saved['new naming, no The'][c['id']]!r}")
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
