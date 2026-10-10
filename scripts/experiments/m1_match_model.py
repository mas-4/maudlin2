"""M1 one model fewer (Oct 10). When the filing model proposes a new motif name, motif_index.match() asks Qwen3 30B
(MATCH_PROMPT) whether an existing motif is the same shape, so a duplicate isn't made. It's the one job left on the 30B,
and each time it runs it trades places with Gemma 26B on the card. Here both models answer the match question on the
person's own verdicts from the curation log: each merge (a motif folded into another: the right answer is the one it
went into) and each "not the same" (the right answer is anything but the other). The options are the right one and the
4 nearest others by meaning, in a shuffled order, as match() shows them. Measured: merges found, "not the same" pairs
joined anyway, seconds a call. Resumable; caches in EXP."""
import json
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'm1_match_model.json')
MODELS = ['qwen3:30b-a3b', 'gemma4:26b']
OTHERS = 4


def cases(index: dict) -> list[dict]:
    """[{'key', 'kind': 'merge'|'not_same', 'phrase', 'claim', 'right': motif id}] from the log's merges and not-sames"""
    live = {e['id']: e for e in mi.live(index)}
    out = []
    for r in fc.log_rows():
        a, before = r.get('action') or {}, r.get('before') or {}
        for s in ([a] + (a.get('steps') or [])) if isinstance(a, dict) else []:
            if not isinstance(s, dict):
                continue
            if s.get('action') == 'merge' and isinstance(before.get('source'), dict) and s.get('target') in live:
                src = before['source']
                if src.get('claims'):
                    out.append({'key': f"merge|{s.get('source')}|{s['target']}", 'kind': 'merge', 'phrase': src['name'],
                                'claim': src['claims'][0], 'right': s['target'], 'away': s.get('source')})
            elif s.get('action') == 'not_same' and s.get('a') in live and s.get('b') in live:
                a_ = live[s['a']]
                if a_['claims']:
                    out.append({'key': f"not_same|{s['a']}|{s['b']}", 'kind': 'not_same', 'phrase': a_['name'],
                                'claim': a_['claims'][0]['claim'], 'right': s['b'], 'away': s['a']})
    return list({c['key']: c for c in out}.values())


def options(index: dict, c: dict, vec) -> tuple[str, list[str]]:
    """match()'s listing: the motif that matters and the nearest others by meaning, shuffled; and the ids in order"""
    live = [e for e in mi.live(index) if e['claims'] and e['id'] not in (c['right'], c.get('away'))]
    V = vec([c['phrase']] + [mi.described(e) for e in live])
    near = [live[int(i)] for i in np.argsort(-(V[1:] @ V[0]))[:OTHERS]]
    shown = near + [index['entries'][c['right']]]
    random.Random(c['key']).shuffle(shown)
    text = '\n'.join(f'{n}. {mi.described(e)} (e.g. ' + '; '.join(f'"{x["claim"][:110]}"' for x in e['claims'][-2:]) + ')'
                     for n, e in enumerate(shown, 1))
    return text, [e['id'] for e in shown]


def ask(model: str, c: dict) -> dict | None:
    schema = {"type": "object", "properties": {
        "reason": {"type": "string", "maxLength": 1000},
        "pick": {"type": "string", "enum": [str(n) for n in range(1, len(c['ids']) + 1)] + ['new']}},
        "required": ["reason", "pick"]}
    t = time.time()
    a = llm.complete_json(mi.MATCH_PROMPT.format(phrase=c['phrase'], claim=c['claim'], options=c['options']), schema,
                          max_tokens=500, model=model)
    if not a:
        return None
    return {'pick': None if a['pick'] == 'new' else c['ids'][int(a['pick']) - 1], 'seconds': round(time.time() - t, 2)}


def main():
    from app.narratives import embed
    index = mi.load()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    every = cases(index)
    for c in every:
        c['options'], c['ids'] = options(index, c, embed)
    print(f"{len(every)} cases: {sum(c['kind'] == 'merge' for c in every)} merges, "
          f"{sum(c['kind'] == 'not_same' for c in every)} not the same", flush=True)
    for model in MODELS:  # one model at a time, so each loads once
        got = saved.setdefault(model, {})
        todo = [c for c in every if c['key'] not in got]
        for s in range(0, len(todo), 32):
            part = todo[s:s + 32]
            for c, a in zip(part, llm.parallel(lambda c, model=model: ask(model, c), part)):
                if a:
                    got[c['key']] = a
            json.dump(saved, open(OUT, 'w'))
            print(f'{model}: {len(got)}/{len(every)}', flush=True)
    lines = [f"M1 the match question, Qwen3 30B against Gemma 26B, on {len(every)} of the person's verdicts:"]
    for model in MODELS:
        got = saved.get(model, {})
        merges = [c for c in every if c['kind'] == 'merge' and c['key'] in got]
        nots = [c for c in every if c['kind'] == 'not_same' and c['key'] in got]
        found = sum(got[c['key']]['pick'] == c['right'] for c in merges)
        new = sum(got[c['key']]['pick'] is None for c in merges)
        joined = sum(got[c['key']]['pick'] == c['right'] for c in nots)
        sec = np.mean([v['seconds'] for v in got.values()]) if got else 0
        lines.append(f'  {model}: merges found {found}/{len(merges)} ({new} called new), "not the same" joined anyway '
                     f'{joined}/{len(nots)}; {sec:.1f} s a call, four at once')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
