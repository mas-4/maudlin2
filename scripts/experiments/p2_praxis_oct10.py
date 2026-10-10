"""P2 the Oct 10 praxis (docs/motif-praxis.md), before it goes into production:
- 'ours to name': rule 7 refined, "the motif is ours to name; the shape has to be in what's told": tellers rarely name
  the motif, and needn't; file the motif the told event is itself a case of, in its details, framing or the reactions
  it draws, once what the audience brings is taken away. The judge (Nimble 9B, with elements) asked with today's
  question and with that rule added, on every decided filing; AUC overall and on the Oct 10 decisions, made under it.
- 'naming': the new rules for naming a proposed motif (say it the way people say it, a known story whose plot is the
  shape, no abstract nominalizations or topic labels, the shape not the case, one to five words). For each motif the
  model named and the person renamed (the curation log's renames), Gemma 26B names it again from the same claims,
  with today's instruction and with the rules. Measured: likeness by meaning to the person's name (and the model's
  original name's, for scale), abstract nominalizations (" of ", " via ", -tion/-ment/-ity/-ness words), words. The
  rules' examples are the person's own names, so motifs whose name appears in the rules aren't scored.
Resumable; caches in EXP."""
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import d1_definition_swap as d1  # noqa: E402
import d2_past_verdicts as d2  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'p2_praxis_oct10.json')
OURS_TO_NAME = ('The tellers needn\'t name the motif: the told event can itself be a case of it, in the details told, '
                'the framing or the reactions it draws. But the shape must be in what is told, not brought by the '
                'audience or a critic.')
OLD_NAMING = ('three to seven words, terse like a folklorist\'s label: a subject and what it does or is; no names of '
              'people, places or dates unless the story is about that one figure')
NEW_NAMING = """one to five words that make sense alone on a chip:
- say it the way people say it: an idiom, a catchphrase or the tellers' own words (They're pouring in!, Shocked, \
shocked!, I could shoot someone on Fifth Avenue, The hospitals will close, Wealth without well-being, Gaslit);
- or a well-known story whose plot is the shape, when the reference lands (Camp of the Saints, Five O'Clock Follies, \
Hoist by his own petard, Sholay, Human centipede, No second acts, Bread and circuses); not Latin for its own sake;
- no abstract nominalizations ("X of Y via Z"), no academic labels, no topic labels ("Trump's influence on \
candidates" became Dead weight president);
- name the shape, not the case: general enough for the next story (Driven off the land, not the settlers); a kind of \
person is an Archetype and sounds like one (RINO, Champagne socialist, Culture warrior, Equivocator)"""
NAME_PROMPT = """These claims are instances of one motif in our index of recurring story shapes in what people tell \
about politics and public life:
{claims}

Name the motif: {rules}."""
NAME_SCHEMA = {"type": "object", "properties": {"name": {"type": "string", "maxLength": 80}}, "required": ["name"]}
ABSTRACT = re.compile(r"\b(of|via)\b|\b\w{3,}(tion|ment|ity|ness|ism)s?\b", re.I)


def renames() -> list[dict]:
    """[{id, model, person, claims}] for each motif the model named and the person renamed: the person's name is the
    motif's name now (or its last rename, if gone)"""
    index = mi.load()
    out, last = {}, {}
    for r in fc.log_rows():
        a, before = r.get('action') or {}, (r.get('before') or {}).get('id') or {}
        if not (isinstance(a, dict) and a.get('action') == 'rename'):
            continue
        last[a.get('id')] = a.get('name')
        if before.get('by') == 'model' and a.get('id') not in out and before.get('claims'):
            out[a['id']] = {'id': a['id'], 'model': before['name'], 'claims': before['claims'][:3],
                          'at': str(r.get('at', ''))}
    for k, v in out.items():
        e = index['entries'].get(k)
        v['person'] = e['name'] if e and not e.get('merged_into') else last[k]
    return list(out.values())


def main():
    from sklearn.metrics import roc_auc_score
    from app.narratives import embed
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    sig, pairs, _ = d2.setup()
    for arm, q in (('today', ms.ELEMENT_QUESTION), ('ours to name', f'{ms.ELEMENT_QUESTION} {OURS_TO_NAME}')):
        got = saved.setdefault(arm, {})
        todo = [(p['key'], sig.judge_ask(p['claim'], sig.at[p['eid']], leave_out=True)[1]) for p in pairs if p['key'] not in got]
        for start in range(0, len(todo), d1.ROUND):
            part = todo[start:start + d1.ROUND]
            for (k, _), v in zip(part, llm.parallel(lambda x, q=q: d1.nimble(x[1], q), part)):
                if v is not None:
                    got[k] = v
            json.dump(saved, open(OUT, 'w'))
            print(f'{arm}: {len(got)}/{len(pairs)}', flush=True)
    cases = renames()
    for arm, rules in (('old naming', OLD_NAMING), ('new naming', NEW_NAMING)):
        got = saved.setdefault(arm, {})
        todo = [c for c in cases if c['id'] not in got]
        asks = llm.parallel(lambda c, rules=rules: llm.complete_json(NAME_PROMPT.format(
            claims='\n'.join(f'- {x}' for x in c['claims']), rules=rules), NAME_SCHEMA, max_tokens=100,
            model=ms.JUDGE_MODEL), todo)
        for c, a in zip(todo, asks):
            if a and a.get('name'):
                got[c['id']] = a['name'].strip()
        json.dump(saved, open(OUT, 'w'))
        print(f'{arm}: {len(got)}/{len(cases)}', flush=True)

    ps = [p for p in pairs if all(p['key'] in saved[a] for a in ('today', 'ours to name'))]
    y = np.array([p['kept'] for p in ps], dtype=bool)
    new = np.array([p['at'].startswith('2026-10-10') for p in ps])
    lines = [f'P2 the Oct 10 praxis: the judge on {len(ps)} decided filings ({int(y.sum())} kept; {int(new.sum())} decided '
             f'Oct 10, {int(y[new].sum())} kept):']
    for arm in ('today', 'ours to name'):
        v = np.array([saved[arm][p['key']] for p in ps])
        lines.append(f'  {arm}: AUC {roc_auc_score(y, v):.3f}, Oct 10 {roc_auc_score(y[new], v[new]):.3f}; '
                     f'yes on kept {v[y].mean():.3f}, on taken out {v[~y].mean():.3f}')
    scored = [c for c in cases if c['person'].lower() not in NEW_NAMING.lower()
              and all(c['id'] in saved[a] for a in ('old naming', 'new naming'))]
    for label, part in (('all', scored), ('renamed Oct 9 or later', [c for c in scored if c['at'] >= '2026-10-09'])):
        if not part:
            continue
        P = embed([c['person'] for c in part])
        lines.append(f'  naming, {label}: {len(part)} motifs the model named and the person renamed (of {len(cases)}):')
        for arm, names in (('the model\'s first name', [c['model'] for c in part]),
                           ('old naming', [saved['old naming'][c['id']] for c in part]),
                           ('new naming', [saved['new naming'][c['id']] for c in part]),
                           ('the person\'s', [c['person'] for c in part])):
            sim = (embed(names) * P).sum(1)
            lines.append(f'    {arm}: like the person\'s {sim.mean():.3f} (0.8 or more for {np.mean(sim >= 0.8):.0%}); '
                         f'abstract {np.mean([bool(ABSTRACT.search(n)) for n in names]):.0%}; '
                         f'{np.mean([len(n.split()) for n in names]):.1f} words')
    for c in scored[:12]:
        lines.append(f"    e.g. {c['model']!r} -> person {c['person']!r}; old {saved['old naming'][c['id']]!r}, "
                     f"new {saved['new naming'][c['id']]!r}")
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
