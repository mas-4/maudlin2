"""J2 the judge, as the casebook reasons (Oct 9; docs/motif-praxis.md, docs/motif-casebook.md). The person's rulings
turn on things the confidence model's judge (Nimble 9B, J1) isn't shown or isn't asked:

- the tellers' own words: the judge sees only the claim's one-line summary (the Fox News claim's "threatening to
  retaliate" drew three filings its tellings don't carry). Variant 'tellings': up to three tellings, and the question
  asks by what the tellers say, not why the story might travel;
- what a motif needs: Passing the buck needs something gone wrong that's deflected, Proxy warfare a named patron.
  Variant 'element': each motif's must-have element in one sentence (drafted by Gemma 26B from its name, note and genre,
  not its claims, whose checks are the test's answers), and the question asks whether the telling has it;
- the genre: a Theory needs a teller voicing the hidden cause, an Argument someone making the move, a Plot the events on
  their face. Variant 'genre': the question asked in the motif's genre's terms;
- 'all': the three together.

And three signals for the confidence model: 'story' (Nimble: do the tellers tell a story or reading, or only report
the news? the praxis: straight news gets no motif), 'tellers' (how many distinct posters or shows: the repetition bar)
and 'news share' (of the shows telling it, the share that are news bulletins).

Measured on every filing the person decided on: each variant alone (AUC) and in the confidence model in the judge's
place (held out, folds by claim); the signals added; and the same on two harder sets: the person's Oct 9 rulings
carried out through the MCP (the casebook's), and the removals of each kind, a reason drafted by Gemma 26B for each
✕ (subtext, missing element, other side, just news, another motif, other). Resumable; caches in EXP."""
import json
import os
import sys
import time

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import j1_jury  # noqa: E402
import tellings as tl  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

OUT = os.path.join(harness.EXP, 'j2_judge_variants.json')
DECIDER = 'nimble:9b'
GEMMA = ms.JUDGE_MODEL
ROUND = 32

GENRE_ASK = {
    'Theories': 'Does a teller, in their own words, name or point to the hidden cause, agent or mechanism this motif is?',
    'Beliefs': 'Does a teller reason from this premise, taking it for granted?',
    'Plots': 'Do the events the tellers tell, read on their face, follow this sequence?',
    'Archetypes': 'Does a teller portray someone as this type of person?',
    'Arguments': 'Does a teller make this rhetorical move themselves?',
    'Values': 'Does a teller say this is how things ought to be?',
    'Exhortations': 'Does a teller urge people to do this?',
}
PLAIN_ASK = 'Do the tellers, in their own words, tell this motif?'
TELLINGS_RULE = ('Judge by what the tellers themselves say, not by why the story might be circulating or what a critic '
                 'would read into it; a plain news report of an event is not an instance of a motif no teller voices.')
STORY_ASK = ('Do the tellers tell a story or a reading around it (who is to blame, what it means, a hidden cause, a '
             'portrait of someone, an argument, a warning), rather than only reporting an event or stating a fact?')

ELEMENT_PROMPT = """A motif in our index of recurring story shapes in what people tell about politics and public life:
Name: {name}
Genre: {genre}
What it covers: {note}

In one sentence: what must a telling contain to be an instance of this motif, the part without which it would be a \
different motif or none? Not its topic, people or place: the element itself (for "Passing the buck": something has \
gone wrong and the one responsible deflects the blame onto others)."""
ELEMENT_SCHEMA = {"type": "object", "properties": {"element": {"type": "string", "maxLength": 300}}, "required": ["element"]}

REASONS = ['subtext', 'missing element', 'other side', 'just news', 'another motif', 'other']
REASON_PROMPT = """A person curating an index of recurring story shapes (motifs) took this claim out of this motif.

The motif: {name} ({genre}). {note}

The claim: {claim}
What its tellers said:
{tellings}

Why, most likely? One of:
- subtext: the motif reads into the story something no teller says (why it spreads, a critic's verdict)
- missing element: the tellings lack the part the motif needs (its defining element)
- other side: the tellers argue against the motif or tell the opposite side of that fight
- just news: a plain report of an event, with no story told around it
- another motif: right kind of story, but a different motif is the right one (or should exist)
- other

reason: a sentence
why: one of the six"""
REASON_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 400},
                                                  "why": {"type": "string", "enum": REASONS}}, "required": ["reason", "why"]}


def nimble(state: str, question: str) -> float:
    r = rq.post(f'{llm.OLLAMA_URL}/v1/systemone', timeout=300, json={
        'model': DECIDER, 'state': state, 'questions': {'q': {'type': 'noul', 'instructions': question}}})
    r.raise_for_status()
    a = r.json()['answers']['q']
    return float(a.get('noul', a.get('probability')) if isinstance(a, dict) else a)


def ask_all(saved: dict, name: str, items: list[tuple[str, tuple]], fn, workers: int = llm.PARALLEL):
    """fn(*args) for each (key, args) not answered yet, saved under `name`"""
    got = saved.setdefault(name, {})
    todo = [(k, a) for k, a in items if k not in got]
    for start in range(0, len(todo), ROUND):
        part = todo[start:start + ROUND]

        def one(x):
            try:
                return fn(*x[1])
            except Exception as e:  # noqa: BLE001 - asked again on a rerun
                print(f'{name}: {type(e).__name__} {e}'[:200], flush=True)
                return None
        for (k, _), v in zip(part, llm.parallel(one, part, workers=workers)):
            if v is not None:
                got[k] = v
        json.dump(saved, open(OUT, 'w'))
        print(f'{name}: {len(got)}/{len(items)}', flush=True)


def elements(saved, pairs, index):
    def draft(eid):  # from its name, note and genre only: its checked claims are the test's answers
        e = index['entries'][eid]
        a = llm.complete_json(ELEMENT_PROMPT.format(name=e['name'], genre=mi.genre_of(e) or 'none yet',
                                                    note=e.get('note') or '(no note yet)'),
                              ELEMENT_SCHEMA, max_tokens=200, model=GEMMA)
        return ' '.join(a['element'].split()) if a and a.get('element') else None
    ask_all(saved, 'elements', [(eid, (eid,)) for eid in sorted({p['eid'] for p in pairs})], draft)


def states(p, index, tells, element):
    """The judge's state for a pair in each variant, and its question"""
    e = index['entries'][p['eid']]
    genre = mi.genre_of(e)
    base = p['state']
    told = f"\n\nWhat the new claim's tellers said:\n{tl.block(tells)}"
    need = f'\nWhat a telling must contain to be this motif: {element}' if element else ''
    head, _, tail = base.partition('\nClaims filed under it:')
    with_need = f'{head}{need}\nClaims filed under it:{tail}' if tail else base + need
    gq = GENRE_ASK.get(genre, PLAIN_ASK)
    return {
        'tellings': (base + told, f'{ms.JUDGE_QUESTION} {TELLINGS_RULE}'),
        'element': (with_need, f'Does the new claim, as told, contain what a telling must contain to be this motif? '
                               f'{ms.JUDGE_QUESTION}'),
        'genre': (f'Genre of the motif: {genre or "none yet"}\n{base}', f'{gq} {ms.JUDGE_QUESTION}'),
        'all': (f'Genre of the motif: {genre or "none yet"}\n{with_need}{told}',
                f'{gq} Does the telling contain what this motif must contain? {TELLINGS_RULE}'),
    }


def hard_set() -> set[str]:
    """The pairs the person ruled on through the MCP on Oct 9 (the casebook's rulings)"""
    out = set()
    for r in fc.log_rows():
        if r.get('by') != 'claude' or not str(r.get('at', '')).startswith('2026-10-09'):
            continue
        a = r.get('action') or {}
        for s in ([a] + (a.get('steps') or [])) if isinstance(a, dict) else []:
            if not isinstance(s, dict) or not isinstance(s.get('claim'), str):
                continue
            for eid in {s.get('id'), s.get('source'), s.get('target')} - {None}:
                out.add(f'{mi.key(s["claim"])}|{eid}')
    return out


def report(saved, pairs, index, tells):
    from sklearn.metrics import roc_auc_score
    y = np.array([p['kept'] for p in pairs], dtype=bool)
    groups = [p['key'].split('|')[0] for p in pairs]
    X = j1_jury.base_matrix(pairs)
    jcol = fc.FEATURES.index('judge')
    no_judge = np.delete(X, jcol, 1)
    j1 = json.load(open(j1_jury.OUT))['answers'][DECIDER]
    lg = lambda v: fc.logit(np.array(v, dtype=float))  # noqa: E731
    cols = {'today (summary only)': lg([j1.get(p['key'], 0.5) for p in pairs])}
    for v in ('tellings', 'element', 'genre', 'all'):
        got = saved.get(v, {})
        if len(got) >= 0.95 * len(pairs):
            cols[v] = lg([got.get(p['key'], 0.5) for p in pairs])
    ck = [p['key'].split('|')[0] for p in pairs]
    story = lg([saved.get('story', {}).get(k, 0.5) for k in ck])
    tellers = np.log1p([tells[k]['tellers'] for k in ck])
    news = np.array([tells[k]['news'] for k in ck])
    hard = hard_set()
    hard_ix = np.array([p['key'] in hard for p in pairs])
    reasons = saved.get('reasons', {})
    lines = [f'J2 the judge as the casebook reasons, {len(pairs)} decided filings ({int(y.sum())} kept); '
             f'{int(hard_ix.sum())} of them the Oct 9 rulings ({int(y[hard_ix].sum())} kept); tellings for '
             f'{sum(1 for k in set(ck) if tells[k]["texts"])} of {len(set(ck))} claims:']
    held = {}
    for name, c in cols.items():
        r = fc.evaluate(np.column_stack([no_judge, c]), y, groups)
        held[name] = r['p']
        hard_auc = roc_auc_score(y[hard_ix], c[hard_ix]) if 0 < y[hard_ix].sum() < hard_ix.sum() else float('nan')
        lines.append(f'  {name}: alone AUC {roc_auc_score(y, c):.3f}, Oct 9 rulings {hard_auc:.3f}; '
                     f'in the confidence model {r["auc"]:.3f}')
    base = np.column_stack([no_judge, cols['today (summary only)']])
    for name, extra in (('story', [story]), ('tellers + news share', [tellers, news]),
                        ('story + tellers + news share', [story, tellers, news])):
        if name.startswith('story') and len(saved.get('story', {})) < 0.95 * len(set(ck)):
            continue
        lines.append(f'  confidence model (today) + {name}: {fc.evaluate(np.column_stack([base] + extra), y, groups)["auc"]:.3f}')
    best = max((n for n in cols if n != 'today (summary only)'), key=lambda n: roc_auc_score(y, cols[n]), default=None)
    if best and len(saved.get('story', {})) >= 0.95 * len(set(ck)):
        r = fc.evaluate(np.column_stack([no_judge, cols[best], story, tellers, news]), y, groups)
        held['best + signals'] = r['p']
        lines.append(f'  confidence model with {best} + story + tellers + news share: {r["auc"]:.3f}')
    if len(reasons) >= 0.9 * (~y).sum():  # each kind of removal against the kept ones, held-out fits
        lines.append('  held out, by the kind of removal (AUC against all kept filings; n):')
        for why in REASONS:
            ix = np.array([(not p['kept']) and (reasons.get(p['key']) or {}).get('why') == why for p in pairs])
            if ix.sum() < 5:
                continue
            sel = y | ix
            lines.append(f'    {why} ({int(ix.sum())}): ' + ', '.join(f'{n} {roc_auc_score(y[sel], held[n][sel]):.3f}' for n in held))
    return lines


def main():
    index = mi.load()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    pairs = j1_jury.pairs_and_texts()
    tells = tl.of([p['claim'] for p in pairs])
    print(f'{len(pairs)} pairs', flush=True)
    if 'report' not in sys.argv:
        elements(saved, pairs, index)
        st = {p['key']: states(p, index, tells[mi.key(p['claim'])], saved['elements'].get(p['eid'])) for p in pairs}
        for v in ('tellings', 'element', 'genre', 'all'):
            ask_all(saved, v, [(p['key'], st[p['key']][v]) for p in pairs], nimble)
        claims = {mi.key(p['claim']): p['claim'] for p in pairs}
        ask_all(saved, 'story', [(k, (f'The claim: {c}\nWhat its tellers said:\n{tl.block(tells[k])}', STORY_ASK))
                                 for k, c in claims.items()], nimble)

        def reason(p):
            e = index['entries'][p['eid']]
            return llm.complete_json(REASON_PROMPT.format(
                name=e['name'], genre=mi.genre_of(e) or 'no genre', note=e.get('note') or '', claim=p['claim'],
                tellings=tl.block(tells[mi.key(p['claim'])])), REASON_SCHEMA, max_tokens=300, model=GEMMA)
        ask_all(saved, 'reasons', [(p['key'], (p,)) for p in pairs if not p['kept']], reason)
    for ln in report(saved, pairs, index, {mi.key(p['claim']): tells[mi.key(p['claim'])] for p in pairs}):
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
