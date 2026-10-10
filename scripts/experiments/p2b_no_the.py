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
THE_FOR_ARCHETYPES = mi.NAME_RULES + (';\n- "The" belongs to a kind of person (The carpetbagger, The impostor, The '
                                      'sleeper agent); other names take it only when it\'s part of the idiom (The buck '
                                      'stops here), never as a leading flourish')
ARMS = {'new naming': None, 'new naming, no The': NO_THE, 'production, The for Archetypes': THE_FOR_ARCHETYPES}


def main():
    from app.narratives import embed
    saved = json.load(open(p2.OUT))
    cases = p2.renames()
    for arm, rules in list(ARMS.items())[1:]:
        got = saved.setdefault(arm, {})
        todo = [c for c in cases if c['id'] not in got]
        asks = llm.parallel(lambda c, rules=rules: llm.complete_json(p2.NAME_PROMPT.format(
            claims='\n'.join(f'- {x}' for x in c['claims']), rules=rules), p2.NAME_SCHEMA, max_tokens=100,
            model=ms.JUDGE_MODEL), todo)
        for c, a in zip(todo, asks):
            if a and a.get('name'):
                got[c['id']] = a['name'].strip()
        json.dump(saved, open(p2.OUT, 'w'))
    index = mi.load()
    archetype = {c['id']: c['id'] in index['entries'] and mi.genre_of(index['entries'][c['id']]) == 'Archetypes'
                 for c in cases}
    scored = [c for c in cases if c['person'].lower() not in mi.NAME_RULES.lower() and all(c['id'] in saved[a] for a in ARMS)]
    P = embed([c['person'] for c in scored])
    lines = [f'P2b the naming rules with "no leading The", {len(scored)} motifs the person renamed:']
    for arm in ARMS:
        names = [saved[arm][c['id']] for c in scored]
        sim = (embed(names) * P).sum(1)
        lines.append(f'  {arm}: like the person\'s {sim.mean():.3f}; abstract {np.mean([bool(p2.ABSTRACT.search(n)) for n in names]):.0%}; '
                     f'{np.mean([len(n.split()) for n in names]):.1f} words; start with "The" '
                     f'{np.mean([n.split()[0].lower() == "the" for n in names]):.0%} (Archetypes '
                     f'{np.mean([n.split()[0].lower() == "the" for n, c in zip(names, scored) if archetype[c["id"]]]):.0%} '
                     f'of {sum(archetype[c["id"]] for c in scored)}, others '
                     f'{np.mean([n.split()[0].lower() == "the" for n, c in zip(names, scored) if not archetype[c["id"]]]):.0%})')
    for c in scored[:15]:
        lines.append(f"    {saved['new naming'][c['id']]!r} -> {saved['production, The for Archetypes'][c['id']]!r}"
                     + (' (Archetype)' if archetype[c['id']] else ''))
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
