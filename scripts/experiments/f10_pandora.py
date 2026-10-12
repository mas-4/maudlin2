"""F10 Pandora: the tellings inside the person's biggest motifs (Oct 12, the person: "File the experiment for our
biggest motifs"). The Sorcerer's Apprentice raised the Golem's grouping from 0.19 to 0.54 B-cubed precision by having
Gemma split each broad motif into the tellings inside; here the same split, on the person's own done motifs of MIN
claims or more, shown each motif's note, must-have element and the motifs resting on it (not to be repeated). A dry
run: nothing goes into the index or the proposals. The person judges each proposed telling in the experiments page
(scripts/checker: worth a motif, already one, not a telling); the paper is ~/maudlin-data/papers/pandora.md.

    f10_pandora.py open      Gemma, one call a motif (GPU, lease 'pandora-open')
    f10_pandora.py controls  CONTROLS random groups of a motif's claims (sized as Gemma's tellings), each named by Gemma
                             as its tellings are, mixed unlabelled among them for the person's verdicts: the baseline
                             (from Fable's review: splitting raises agreement mechanically, so the verdicts need a control)
    f10_pandora.py report    kept whole against split, groups per split, and the person's verdicts so far"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'f10_pandora.json')
MODEL = 'gemma4:26b'
MIN = 10
PROMPT = """These claims were filed under one motif, "{name}"{note}:
{claims}
{children}
A folklorist would split a broad motif into the distinct tellings inside it: shapes that people retell, each with its
own who-does-what-to-whom (foreign meddling, a trusted figure's betrayal and leaked secrets are three tellings, not one
"enemy within"). Split these claims into the tellings they hold, or keep them as one if they truly are one. Don't repeat
a telling that already has a motif of its own resting on this one. Each group:
name: {rules}
note: one sentence, the shape the group's claims share
claims: the numbers of its claims
Every claim in exactly one group; a group of one claim only if it truly stands alone."""
CONTROLS = 24
NAME_PROMPT = """These claims were filed under one motif, "{name}"{note}:
{claims}

Name the shape these claims share, as a folklorist names a telling inside a broad motif:
name: {rules}
note: one sentence, the shape the claims share"""
NAME_SCHEMA = {"type": "object", "properties": {"name": {"type": "string", "maxLength": 80},
                                               "note": {"type": "string", "maxLength": 300}}, "required": ["name", "note"]}
SCHEMA = {"type": "object", "properties": {"groups": {"type": "array", "items": {"type": "object", "properties": {
    "name": {"type": "string", "maxLength": 80}, "note": {"type": "string", "maxLength": 300},
    "claims": {"type": "array", "items": {"type": "integer"}}}, "required": ["name", "note", "claims"]}}},
    "required": ["groups"]}


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    state['verdicts'] = {**state.get('verdicts', {}), **saved().get('verdicts', {})}  # the person's, given meanwhile
    json.dump(state, open(OUT + '.tmp', 'w'), indent=1)
    os.replace(OUT + '.tmp', OUT)


def big_motifs(index: dict) -> list[dict]:
    es = [e for e in mi.live(index) if 'done' in e]
    return sorted([e for e in es if len({c['claim'] for c in e['claims']}) >= MIN], key=lambda e: -len(e['claims']))


def children_of(index: dict, eid: str) -> list[str]:
    return [e['name'] for e in mi.live(index) if eid in mi.parents_of(e)]


def open_():
    index = mi.load()
    state = saved()
    got = state.setdefault('motifs', {})
    from app.analysis import motif_signals as ms
    elements = json.load(open(ms.ELEMENTS)) if os.path.exists(ms.ELEMENTS) else {}
    for e in big_motifs(index):
        if e['id'] in got:
            continue
        claims = list(dict.fromkeys(c['claim'] for c in e['claims']))
        kids = children_of(index, e['id'])
        element = (elements.get(e['id']) or {}).get('element') or ''
        note = ' '.join(x for x in (e.get('note') or '', f'Must have: {element}' if element else '') if x)
        r = llm.complete_json(PROMPT.format(
            name=e['name'], note=f' ({note})' if note else '',
            claims='\n'.join(f'{n}. {c}' for n, c in enumerate(claims, 1)),
            children=f"\nMotifs already resting on it: {'; '.join(kids)}.\n" if kids else '',
            rules=mi.NAME_RULES), SCHEMA, max_tokens=2000, model=MODEL)
        if r is None:
            sys.exit('open: no answer; Ollama down? stopping to try again')
        groups = [{'name': g['name'], 'note': g['note'],
                   'claims': [claims[i - 1] for i in dict.fromkeys(g.get('claims') or []) if 1 <= i <= len(claims)]}
                  for g in r.get('groups', [])]
        got[e['id']] = {'name': e['name'], 'note': e.get('note', ''), 'claims': len(claims), 'children': kids,
                        'groups': [g for g in groups if g['claims']]}
        save(state)
        print(f"open: {e['name']}: {len(got[e['id']]['groups'])} tellings", flush=True)


def controls():
    """Random groups of a motif's claims, sized as Gemma's tellings, named by Gemma: mixed among the tellings"""
    import random
    state = saved()
    got = state.setdefault('controls', [])
    index = mi.load()
    motifs = state.get('motifs', {})
    sizes = [len(g['claims']) for m in motifs.values() for g in m['groups']]
    rnd = random.Random(10 + len(got))
    while len(got) < CONTROLS and motifs:
        mid = rnd.choice(sorted(motifs))
        e = index['entries'].get(mid)
        if not e:
            continue
        claims = list(dict.fromkeys(c['claim'] for c in e['claims']))
        k = min(rnd.choice(sizes), len(claims) - 1)
        if k < 1:
            continue
        picked = rnd.sample(claims, k)
        r = llm.complete_json(NAME_PROMPT.format(name=e['name'], note=f" ({e['note']})" if e.get('note') else '',
                                                 claims='\n'.join(f'- {c}' for c in picked), rules=mi.NAME_RULES),
                              NAME_SCHEMA, max_tokens=400, model=MODEL)
        if r is None:
            sys.exit('controls: no answer; Ollama down? stopping to try again')
        got.append({'motif': mid, 'name': r['name'], 'note': r['note'], 'claims': picked})
        save(state)
        print(f"controls: {len(got)}/{CONTROLS}", flush=True)


def report():
    state = saved()
    ms = state.get('motifs', {})
    splits = [len(m['groups']) for m in ms.values()]
    whole = sum(1 for n in splits if n <= 1)
    verdicts = state.get('verdicts', {})  # 'motif id|telling name' -> 'motif' | 'already' | 'not'
    v = [x for k, x in verdicts.items() if not k.startswith('ctl|')]
    c = [x for k, x in verdicts.items() if k.startswith('ctl|')]
    rate = lambda xs: f"{(xs.count('motif') + xs.count('already')) / len(xs):.0%}" if xs else '–'  # noqa: E731
    told = (f"; the person's verdicts on {len(v)} of Gemma's tellings: worth a motif {v.count('motif')}, already one "
            f"{v.count('already')}, not a telling {v.count('not')} (a telling: {rate(v)}); on {len(c)} random groups "
            f"named the same way: a telling {rate(c)}") if v else '; no verdicts from the person yet'
    line = (f"F10 Pandora: {len(ms)} of the person's motifs of {MIN}+ claims opened by Gemma; kept whole {whole}, split "
            f"{len(ms) - whole} (mean {np.mean([n for n in splits if n > 1]) if len(ms) > whole else 0:.1f} tellings each), "
            f"{sum(1 for m in ms.values() for g in m['groups'] if len(g['claims']) == 1)} tellings of one claim" + told)
    print(line, flush=True)
    harness.note(line)


def main():
    {'open': open_, 'controls': controls, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
