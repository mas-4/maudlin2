"""D5 actants (Oct 10; after Tangherlini et al., the generative model of legend, 2018, and the Pizzagate/Bridgegate
narrative frameworks, PLOS ONE 2020: a story is its actants, who does what to whom, and a conspiracy theory threads
domains that a plain account keeps apart; a legend sets an inside group against an outside threat). Gemma 26B reads
each claim for:
- who does what to whom: up to three (actor, relation, target), each actor and target a type of role, never a name
  ("a governor", "immigrants", "the press");
- the threat: from inside the teller's own community or institutions, from outside it, both, or none;
- the domains it threads (politics, money, health, religion, crime, war, media, science, technology, family, law,
  sex, race and ethnicity, education, environment, sport, culture).
Measured, on the shortlist harness rebuilt for today's index (the claims the person confirmed in motifs marked done,
each against every live motif, weights learned on other claims):
- 'skeleton': the most alike, by meaning, of the claim's who-does-what-to-whom and each motif's other claims';
- 'threat': the share of each motif's other claims with the claim's kind of threat;
- both; recall at 12 overall and by the genre of the motif it belongs in;
- domains threaded: Theories' claims against Plots' (AUC of the count), a signal for the genre drafter.
Resumable; Gemma's readings cached in EXP."""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'd5_actants.json')
CACHE = os.path.join(harness.EXP, 'signals_d5.pkl')
THREATS = ['inside', 'outside', 'both', 'none']
DOMAINS = ['politics', 'money', 'health', 'religion', 'crime', 'war', 'media', 'science', 'technology', 'family', 'law',
           'sex', 'race and ethnicity', 'education', 'environment', 'sport', 'culture']
PROMPT = """A claim people are telling about politics or public life:
{claim}

1. Who does what to whom in it: up to three (actor, relation, target). Each actor and target is a TYPE of role, never \
a name ("a governor", "immigrants", "the press", "voters"); the relation a short verb phrase ("covers up", "lies to", \
"replaces").
2. The threat or wrongdoing the teller describes: does it come from inside the teller's own community or \
institutions (inside), from outsiders to it (outside), both, or is there none?
3. The domains of life the claim threads together (one or more)."""
SCHEMA = {"type": "object", "properties": {
    "triples": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
        "actor": {"type": "string", "maxLength": 60}, "relation": {"type": "string", "maxLength": 60},
        "target": {"type": "string", "maxLength": 60}}, "required": ["actor", "relation", "target"]}},
    "threat": {"type": "string", "enum": THREATS},
    "domains": {"type": "array", "items": {"type": "string", "enum": DOMAINS}}},
    "required": ["triples", "threat", "domains"]}


def skeleton(r: dict) -> str:
    return '; '.join(f"{t['actor']} {t['relation']} {t['target']}" for t in r.get('triples') or []) or 'nothing'


def main():
    from sklearn.metrics import roc_auc_score
    from app.narratives import embed
    index = mi.load()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    if 'report' not in sys.argv:
        claims = sorted({c['claim'] for e in mi.live(index) for c in e['claims']})
        todo = [c for c in claims if mi.key(c) not in saved]
        print(f'{len(claims)} claims, {len(todo)} to read', flush=True)
        for start in range(0, len(todo), 32):
            part = todo[start:start + 32]
            for c, a in zip(part, llm.parallel(lambda c: llm.complete_json(PROMPT.format(claim=c), SCHEMA, max_tokens=400,
                                                                           model=ms.JUDGE_MODEL), part)):
                if a:
                    saved[mi.key(c)] = a
            json.dump(saved, open(OUT, 'w'))
            print(f'read {len(saved)}/{len(claims)}', flush=True)
    data = harness.load(CACHE)  # built once for today's index; delete it to build again
    entries = data['entries']
    own = {m: [mi.key(c['claim']) for c in entries[m]['claims'] if mi.key(c['claim']) in saved] for m in data['ids']}
    keys = sorted({k for ks in own.values() for k in ks} | set(data['claims']))
    keys = [k for k in keys if k in saved]
    V = embed([skeleton(saved[k]) for k in keys])
    at = {k: i for i, k in enumerate(keys)}

    def skel(data, k):
        if k not in at:
            return np.zeros(len(data['ids']), dtype=np.float32)
        out = np.zeros(len(data['ids']), dtype=np.float32)
        for j, m in enumerate(data['ids']):
            others = [at[x] for x in own[m] if x != k]
            if others:
                out[j] = float((V[others] @ V[at[k]]).max())
        return out

    def threat(data, k):
        mine = (saved.get(k) or {}).get('threat')
        out = np.zeros(len(data['ids']), dtype=np.float32)
        for j, m in enumerate(data['ids']):
            others = [saved[x].get('threat') for x in own[m] if x != k]
            if others and mine:
                out[j] = sum(t == mine for t in others) / len(others)
        return out

    lines = [f'D5 actants (Gemma 26B), {len(saved)} claims read; shortlist harness of {len(data["claims"])} confirmed '
             f'claims against {len(data["ids"])} motifs:']
    base = harness.ranks(data)
    genre = {m: mi.genre_of(index['entries'][m]) if m in index['entries'] else None for m in data['ids']}

    def by_genre(rk):
        hits, total = {}, {}
        for k, r in rk.items():
            for m in data['claims'][k]['truth']:
                g = genre.get(m) or 'no genre'
                total[g] = total.get(g, 0) + 1
                hits[g] = hits.get(g, 0) + (r[data['at'][m]] < 12)
        return {g: (hits[g] / total[g], total[g]) for g in total}
    bg = by_genre(base)
    for name, extra in (('skeleton', {'skeleton': skel}), ('threat', {'threat': threat}),
                        ('skeleton + threat', {'skeleton': skel, 'threat': threat})):
        r = harness.evaluate(data, extra, label=f'D5 {name}')
        ng = by_genre(harness.ranks(data, extra))
        lines.append(f"  {name}: top-12 {r['base'][12]:.1%} -> {r['with'][12]:.1%}, top-40 {r['base'][40]:.1%} -> "
                     f"{r['with'][40]:.1%}; by genre (top-12, n): "
                     + ', '.join(f'{g} {bg[g][0]:.0%}->{ng[g][0]:.0%} ({bg[g][1]})' for g in sorted(bg, key=lambda g: -bg[g][1])))
    th = [(len(set(saved[mi.key(c['claim'])]['domains'])), mi.genre_of(e)) for e in mi.live(index) for c in e['claims']
          if mi.key(c['claim']) in saved and mi.genre_of(e) in ('Theories', 'Plots')]
    if th:
        y = np.array([g == 'Theories' for _, g in th])
        n = np.array([d for d, _ in th])
        lines.append(f'  domains threaded: Theories {n[y].mean():.2f}, Plots {n[~y].mean():.2f} (AUC {roc_auc_score(y, n):.3f}, '
                     f'{int(y.sum())} and {int((~y).sum())} claims); threat by genre: '
                     + '; '.join(f"{g} " + ', '.join(f"{t} {np.mean([saved[mi.key(c['claim'])]['threat'] == t for e in mi.live(index) if mi.genre_of(e) == g for c in e['claims'] if mi.key(c['claim']) in saved]):.0%}" for t in THREATS)
                                   for g in ('Theories', 'Plots', 'Archetypes', 'Arguments')))
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
