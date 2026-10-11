"""E13 does a fuller telling find a claim's motifs better? (Oct 11, from A1: on folktales, summing a tale up in three
sentences instead of one raised the shortlist's right type in the top 8 from 34% to 47%, the pick from 79% to 80% and
the judge from 0.934 to 0.946.) Our claims are one sentence. For the person's confirmed filings whose source is kept
(what's retold on the shows: every show's version and its quote; the Focus Group: the voter's quote and the transcript
around it), Gemma retells what the speakers say in three plain sentences; then where does the right motif land in the
shortlist (the production weights, motif_retriever.weights; and plain likeness), searching with:
    claim          the one-sentence claim, as now
    telling        the three sentences
    both           the claim and the telling together
the claim itself left out of its motifs, as in training. Only the search text changes: the claim as shown and filed
stays one sentence.

    e13_richer_telling.py tellings | report"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'e13_richer_telling.json')
KS = (8, 12, 40)
MODEL = 'gemma4:26b'
PROMPT = """What people said on {where}:
{said}

In three plain sentences, retell what they say: the claim, how they tell it, and what it's about. Their view, not a
judgment of it."""
SCHEMA = {"type": "object", "properties": {"telling": {"type": "string", "maxLength": 700}}, "required": ["telling"]}


def sources() -> dict[str, dict]:
    """Claim -> {'where', 'said'} for the confirmed filings from the shows and the Focus Group"""
    from app.analysis import focus_group as fg
    from app.analysis import show_claims as sc
    out = {}
    for r in sc.kept_retold():
        out[mi.key(r['claim'])] = {'where': 'talk shows and podcasts',
                                   'said': '\n'.join(f'- "{t["quote"][:300]}"' for t in r['told'][:6] if t.get('quote'))}
    for url, ep in fg.load().items():
        for c in ep['claims']:
            ctx = fg.context(url, c.get('quote', ''))
            said = ''.join(ctx[p] for p in ('before', 'quote', 'after')) if ctx else None
            out.setdefault(mi.key(c['claim']), {'where': 'a focus group of voters',
                                                'said': f'"{(said or c.get("quote", ""))[:1200]}"'})
    return out


def confirmed() -> list[tuple[str, str]]:
    return [(c['claim'], e['id']) for e in mi.live(mi.load()) if e.get('done') for c in e['claims']
            if c.get('checked') == 'yes' and c.get('source') in ('shows', 'Focus Group')]


def tellings():
    src = sources()
    pairs = [(c, m) for c, m in confirmed() if mi.key(c) in src and src[mi.key(c)]['said'].strip('"')]
    state = json.load(open(OUT)) if os.path.exists(OUT) else {}
    got = state.setdefault('tellings', {})
    todo = list(dict.fromkeys(c for c, _ in pairs if c not in got))
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        for c, r in zip(part, llm.parallel(lambda c: llm.complete_json(PROMPT.format(**src[mi.key(c)]), SCHEMA,
                                                                       max_tokens=400, model=MODEL), part)):
            if r and r.get('telling'):
                got[c] = r['telling'].strip()
        json.dump(state, open(OUT, 'w'))
        print(f'tellings: {len(got)}/{len({c for c, _ in pairs})}', flush=True)


def facts(entries: list[dict], claim: str, text: str, vec) -> np.ndarray:
    """motif_retriever.facts, searching with `text` but leaving `claim` out of its motifs"""
    k = mi.key(claim)
    q = vec([text])[0]
    t = vec([mr._text(e, k) for e in entries]) @ q
    name = vec([mi.described(e) for e in entries]) @ q
    near, center, size = np.full(len(entries), -1.0), np.zeros(len(entries)), np.zeros(len(entries))
    for n, e in enumerate(entries):
        own = list(dict.fromkeys(c['claim'] for c in e['claims'] if mi.key(c['claim']) != k))
        size[n] = np.log1p(len(own))
        if own:
            v = vec(own)
            near[n] = float((v @ q).max())
            c = v.mean(0)
            center[n] = float(c @ q / (np.linalg.norm(c) + 1e-9))
    best = np.maximum(name, near)
    at = {e['id']: n for n, e in enumerate(entries)}
    tree = mr._tree(entries, at)
    treeb = np.array([max([best[x] for x in tree[n]], default=-1.0) for n in range(len(entries))])
    return np.stack([t, name, near, center, size, treeb], 1)


def report():
    state = json.load(open(OUT))
    got = state['tellings']
    entries = mi.live(mi.load())
    at = {e['id']: n for n, e in enumerate(entries)}
    w = mr.weights()
    weights, bias = np.array([w['weights'][f] for f in mr.FACTS]), w['bias']
    vec = mr.Vectors()
    pairs = [(c, m) for c, m in confirmed() if c in got and m in at]
    ranks = {}
    for i, (c, m) in enumerate(pairs):
        for arm, text in (('claim', c), ('telling', got[c]), ('both', f'{c} {got[c]}')):
            F = facts(entries, c, text, vec)
            for name, s in ((f'{arm}, weights', F @ weights + bias), (f'{arm}, plain', F[:, :2].max(1))):
                ranks.setdefault(name, []).append(int((s > s[at[m]]).sum()))
        if i % 100 == 0:
            print(f'{i}/{len(pairs)}', flush=True)
    out = {arm: {K: round(float(np.mean(np.array(r) < K)), 3) for K in KS} for arm, r in ranks.items()}
    state['recall'] = out
    json.dump(state, open(OUT, 'w'))
    line = (f'E13 a fuller telling, {len(pairs)} confirmed filings from the shows and the Focus Group; right motif in the '
            f'top 8/12/40: ' + '; '.join(f"{arm} {r[8]:.0%}/{r[12]:.0%}/{r[40]:.0%}" for arm, r in out.items()))
    print(line, flush=True)
    harness.note(line)


def main():
    {'tellings': tellings, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
