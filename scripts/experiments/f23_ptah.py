"""F23 Ptah: the note first, then the name (Oct 14, the person: "when a machine proposes a motif it should propose the
note first and then name the note right?"). Today the 💡 proposer (motif_proposals.NEW_MOTIF_PROMPT) asks for the name
and then the note in one JSON answer, and the model writes the fields in the order asked: the note explains a name
already chosen. The filing model (motif_index.NEW_PROMPT) asks for a name alone. Here each is asked both ways from the
same claims, the only change the field order and the instruction to write the note first and name what it describes.

The cases, the person's decided naming work (read, never written):
    renamed   motifs the model named and the person renamed (Adam's answer key, the curation log's renames): the
              person's name and note now
    approved  the 💡 new-motif proposals the person approved: the motif that holds most of their claims now
    slates    motifs made in the person's corrections (critiques.py's new_with records): drafted in a slate, corrected
              and approved by the person
    rejected  the 💡 new-motif proposals the person rejected: no answer key; for the labels and the proposal rate only

    f23_ptah.py ask      both orders for the proposer on every case, and for the filing prompt on the cases with an
                         answer (its first claim alone); Gemma 26B, saved every EVERY answers
    f23_ptah.py judge    each distinct name read blind by Gemma against the naming rules: a story name, an abstract
                         label or a topic label
    f23_ptah.py report   agreement with the person's names and notes (mxbai likeness, exact and near), labels, words,
                         the name against its own note, proposals made; paired differences with bootstrap intervals

The paper is ~/maudlin-data/papers/ptah.md."""
import functools
import json
import os
import random
import re
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402

OUT = os.path.join(harness.EXP, 'f23_ptah.json')
MODEL = mp.MODEL  # Gemma 4 26B, as both prompts use in production
EVERY = 10  # answers between saves
MAX_CLAIMS = mp.MOTIF_CLUSTER_MAX  # claims shown a case, as the proposer shows a cluster
NEAR = 5  # nearest motifs shown, as the proposer and the filing prompt show
NEAR_MATCH = 0.8  # a name this alike to the person's (mxbai) is a near match (Adam's line)
BLIND = 20  # pairs in the blind set for the person
BOOTS = 2000
ABSTRACT = re.compile(r"\b(of|via)\b|\b\w{3,}(tion|ment|ity|ness|ism)s?\b", re.I)  # Adam's count

# ---------- the two orders ----------
NOTE_WHAT = 'one plain sentence on what kind of story it covers, as its tellers tell it, never judging it true or false'
PROPOSER_SWAPS = [
    ('name the motif {rules}; no names of people, places or dates unless the story is about that one figure. Write its '
     f'scope note ({NOTE_WHAT}), give its genre',
     f'first write its scope note ({NOTE_WHAT}); then name the motif that note describes {{rules}}; no names of people, '
     'places or dates unless the story is about that one figure. Give its genre'),
    ('name: the motif\'s name, or ""\nnote: its scope note, or ""',
     'note: its scope note, written first, or ""\nname: the name of what that note describes, or ""')]
FILING_SWAPS = [
    ('If it does, name it as a new motif, {rules};',
     f'If it does, first write the new motif\'s scope note ({NOTE_WHAT}), then name what that note describes as a new '
     'motif, {rules};'),
    ("reason: a sentence\nnew: the new motif's name, or nothing",
     "reason: a sentence\nnote: its scope note, written first, or nothing\nnew: the name of what that note describes, "
     "or nothing")]


def swapped(prompt: str, swaps: list[tuple[str, str]]) -> str:
    """The prompt with each passage replaced; a passage not found is an error (production changed: the test is stale)"""
    for old, new in swaps:
        if prompt.count(old) != 1:
            raise ValueError(f'the production prompt no longer has: {old[:60]!r}')
        prompt = prompt.replace(old, new)
    return prompt


def proposer_schema(n: int, note_first: bool) -> dict:
    """motif_proposals.new_motifs's schema, the name and note in the order asked (the model writes them in this order)"""
    name, note = ('name', {"type": "string", "maxLength": 60}), ('note', {"type": "string", "maxLength": 320})
    props = [('reason', {"type": "string", "maxLength": 600}), ('new', {"type": "boolean"}),
             *((note, name) if note_first else (name, note)), ('genre', {"type": "string", "maxLength": 40}),
             ('claims', {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": n}})]
    return {"type": "object", "properties": dict(props), "required": [k for k, _ in props]}


def filing_schema(note_first: bool) -> dict:
    """motif_index.name_claim's schema for NEW_PROMPT, with a note before the name when asked"""
    props = [('reason', {"type": "string", "maxLength": 600})]
    if note_first:
        props.append(('note', {"type": "string", "maxLength": 320}))
    props.append(('new', {"type": "array", "maxItems": 1, "items": {"type": "string", "maxLength": 60}}))
    return {"type": "object", "properties": dict(props), "required": [k for k, _ in props]}


PROPOSER = {'name, then note': (mp.NEW_MOTIF_PROMPT, False),
            'note, then name': (swapped(mp.NEW_MOTIF_PROMPT, PROPOSER_SWAPS), True)}
FILING = {'filing: name': (mi.NEW_PROMPT, False),
          'filing: note, then name': (swapped(mi.NEW_PROMPT, FILING_SWAPS), True)}
ARMS = {**PROPOSER, **FILING}


# ---------- small pieces ----------
def norm(name: str) -> str:
    """A name for exact matching: lower case, words only, a leading 'the' dropped"""
    words = re.sub(r'[^a-z0-9 ]', ' ', name.lower()).split()
    return ' '.join(words[1:] if words[:1] == ['the'] else words)


def paired(a: np.ndarray, b: np.ndarray, boots: int = BOOTS, seed: int = 0) -> tuple[float, float, float]:
    """The mean of b - a over the cases, with its 95% bootstrap interval (cases drawn with replacement)"""
    d = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    if not len(d):
        return float('nan'), float('nan'), float('nan')
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), (boots, len(d)))].mean(1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(d.mean()), float(lo), float(hi)


def proposed(answer: dict, n: int) -> bool:
    """Whether production would make the proposal (new, a name that fits, two of the claims, or the one there is);
    not asking whether the name is taken, as the person's own name for these claims is"""
    picked = {x for x in answer.get('claims') or [] if isinstance(x, int) and 1 <= x <= n}
    return bool(answer.get('new')) and mi.fits_name(answer.get('name') or '') and len(picked) >= min(2, n)


def in_rules(name: str) -> bool:
    """The person's name is one of the naming rules' own examples (Adam left these out of the score)"""
    return bool(name) and name.lower() in mi.NAME_RULES.lower()


def blind_pairs(state: dict, n: int = BLIND, seed: int = 23) -> list[dict]:
    """The blind set: cases with an answer whose two proposer names differ, each with which arm is shown first; the
    same every time"""
    a, b = PROPOSER
    got = state.get('answers', {})
    keys = sorted(k for k, c in state.get('cases', {}).items()
                  if c['answer'] and (got.get(a, {}).get(k) or {}).get('name')
                  and (got.get(b, {}).get(k) or {}).get('name')
                  and norm(got[a][k]['name']) != norm(got[b][k]['name']))
    rnd = random.Random(seed)
    picked = rnd.sample(keys, min(n, len(keys)))
    return [{'case': k, 'first': rnd.choice([a, b])} for k in picked]


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'), indent=1)
    os.replace(OUT + '.tmp', OUT)


# ---------- the cases ----------
def _claims(first: list[str], entry: dict | None) -> list[str]:
    """The claims the decision was made on first, then the motif's own claims now, up to MAX_CLAIMS"""
    more = [c['claim'] for c in (entry or {}).get('claims', [])]
    return list(dict.fromkeys(x for x in first + more if x))[:MAX_CLAIMS]


def gather(index: dict) -> dict:
    """Every case: {id: {source, claims, answer: {name, note, id} or None, at}}"""
    import p2_praxis_oct10 as p2  # Adam's answer key
    from app.analysis import critiques as cr
    E = index['entries']
    held = {}
    for e in mi.live(index):
        for c in e['claims']:
            held.setdefault(mi.key(c['claim']), []).append(e['id'])
    out = {}
    for r in p2.renames():
        e = E.get(r['id'])
        if not e or e.get('merged_into'):
            continue
        out[f"R:{r['id']}"] = {'source': 'renamed', 'claims': _claims(r['claims'], e), 'at': r['at'],
                               'model': r['model'], 'answer': {'id': e['id'], 'name': e['name'], 'note': e.get('note', '')}}
    for p in mp.load().values():
        if p['kind'] != 'new_motif' or p['status'] not in ('approved', 'rejected'):
            continue
        claims = [c['claim'] for c in p['args']['claims']]
        answer = None
        if p['status'] == 'approved':
            votes = {}
            for c in claims:
                for i in held.get(mi.key(c), []):
                    votes[i] = votes.get(i, 0) + 1
            if votes:
                top = max(votes, key=lambda i: (votes[i], i))
                answer = {'id': top, 'name': E[top]['name'], 'note': E[top].get('note', '')}
        out[f"{'P' if answer else 'X'}:{p['id']}"] = {
            'source': 'approved' if p['status'] == 'approved' else 'rejected', 'claims': claims[:MAX_CLAIMS],
            'at': p.get('decided', ''), 'model': p['args']['name'], 'answer': answer}
    for r in cr.critiques():
        f = r.get('final') or {}
        if r['kind'] != 'new_with' or not f.get('name'):
            continue
        eid = mi.same_name(index, f['name'])
        e = E.get(eid) if eid else None
        out[f"N:{eid or mi.key(f['name'])[:10]}"] = {
            'source': 'slates', 'claims': _claims([c['claim'] for c in f.get('claims', [])], e), 'at': r['at'],
            'model': '', 'answer': {'id': eid, 'name': e['name'] if e else f['name'],
                                    'note': (e or {}).get('note') or f.get('note', '')}}
    return out


def near_motifs(index: dict, cases: dict) -> dict:
    """Each case's NEAR nearest live motifs by meaning (mxbai, as the proposer finds them), none holding any of the
    case's claims (the motif the person made of them would give the answer away): {case: [motif id]}"""
    from app.narratives import embed
    entries = [e for e in mi.live(index) if e['claims']]
    V = embed([mi.described(e) for e in entries])
    keys = [{mi.key(c['claim']) for c in e['claims']} for e in entries]
    out = {}
    for n, (cid, c) in enumerate(cases.items(), 1):
        mine = {mi.key(x) for x in c['claims']}
        told = embed([shapes().get(mi.key(x)) or x for x in c['claims']])
        first = embed([c['claims'][0]])[0]
        ok = np.array([not (k & mine) for k in keys])
        for which, centre in (('proposer', told.mean(0)), ('filing', first)):
            s = np.where(ok, V @ centre, -9)
            out.setdefault(cid, {})[which] = [entries[i]['id'] for i in np.argsort(-s)[:NEAR]]
        if n % 20 == 0 or n == len(cases):
            print(f'near: {n}/{len(cases)}', flush=True)
    return out


@functools.cache
def shapes() -> dict:
    """claim key -> its bare shape, by the filing model (motif_signals' cache), as the proposer shows them"""
    from app.analysis import motif_signals as ms
    return json.load(open(ms.SHAPES)) if os.path.exists(ms.SHAPES) else {}


# ---------- asking ----------
def ask_one(arm: str, case: dict, near: list[dict], genres: str) -> dict | None:
    from app.analysis import llm
    prompt, note_first = ARMS[arm]
    if arm in PROPOSER:
        listing = '\n'.join(f'{n}. {x[:240]}\n   shape: {(shapes().get(mi.key(x)) or x)[:200]}'
                            for n, x in enumerate(case['claims'], 1))
        a = llm.complete_json(prompt.format(claims=listing, near='\n'.join(f'- {mp.shown(e)}' for e in near) or '(none)',
                                            genres=genres, rules=mi.NAME_RULES),
                              proposer_schema(len(case['claims']), note_first), max_tokens=900, model=MODEL)
        if a is None:
            return None
        return {'name': mi.clean(a.get('name') or ''), 'note': ' '.join((a.get('note') or '').split()),
                'new': bool(a.get('new')), 'genre': a.get('genre', ''), 'claims': a.get('claims', []),
                'reason': a.get('reason', ''), 'order': list(a)}
    a = llm.complete_json(prompt.format(claim=case['claims'][0], rules=mi.NAME_RULES,
                                        closest='; '.join(e['name'] for e in near)),
                          filing_schema(note_first), max_tokens=700, model=MODEL)
    if a is None:
        return None
    names = [m for m in map(mi.clean, a.get('new') or []) if m]
    return {'name': names[0] if names else '', 'note': ' '.join((a.get('note') or '').split()),
            'new': bool(names), 'reason': a.get('reason', ''), 'order': list(a)}


def ask():
    index = mi.load()
    state = saved()
    if 'cases' not in state:
        cases = gather(index)
        state['cases'] = cases
        state['near'] = near_motifs(index, cases)
        save(state)
        print(f'cases: {len(cases)} ({counts(cases)})', flush=True)
    cases, E = state['cases'], index['entries']
    genres = ', '.join(mi.facet_values(index).get('genre', [])) or 'none yet'
    answers = state.setdefault('answers', {})
    total = sum(1 for arm in ARMS for c in cases.values() if arm in PROPOSER or c['answer'])
    for attempt in range(2):  # an answer that failed once is asked once more; then the report goes without it
        todo = [(arm, cid) for arm in ARMS for cid, c in cases.items()
                if cid not in answers.get(arm, {}) and (arm in PROPOSER or c['answer'])]
        done = total - len(todo)
        if attempt and todo:
            print(f'ask: {len(todo)} without an answer, asked again', flush=True)
        ask_all(todo, state, E, genres, done, total)


def ask_all(todo: list, state: dict, E: dict, genres: str, done: int, total: int):
    from app.analysis import llm
    cases, answers = state['cases'], state['answers']
    for start in range(0, len(todo), EVERY):
        part = todo[start:start + EVERY]

        def one(job):
            arm, cid = job
            which = 'proposer' if arm in PROPOSER else 'filing'
            near = [E[i] for i in state['near'][cid][which] if i in E]
            return ask_one(arm, cases[cid], near, genres)
        got = llm.parallel(one, part)
        if all(g is None for g in got):
            sys.exit('ask: no answers; Ollama down? stopping to try again')
        for (arm, cid), g in zip(part, got):
            if g is not None:
                answers.setdefault(arm, {})[cid] = g
                done += 1
        save(state)
        print(f'ask: {done}/{total}', flush=True)


# ---------- the labels, read blind ----------
LABEL_PROMPT = """A name proposed for a motif in our index of recurring story shapes in what people tell about politics \
and public life. Names should be given {rules}

The name: "{name}"

Is it a name of the kind those rules ask for (an idiom, a catchphrase, the tellers' own words, a well-known story, a \
kind of person), or an abstract label (an abstract nominalization such as "X of Y via Z", an academic label), or a \
topic label (it names what the stories are about, not the story told)?

reason: a sentence
label: "story name", "abstract label" or "topic label\""""
LABEL_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 400}, "label": {
    "type": "string", "enum": ["story name", "abstract label", "topic label"]}}, "required": ["reason", "label"]}


def judge():
    from app.analysis import llm
    state = saved()
    names = sorted({a['name'] for arm in state.get('answers', {}).values() for a in arm.values() if a.get('name')}
                   | {c['answer']['name'] for c in state.get('cases', {}).values() if c['answer']})
    labels = state.setdefault('labels', {})
    todo = [n for n in names if n not in labels]
    for start in range(0, len(todo), EVERY):
        part = todo[start:start + EVERY]
        got = llm.parallel(lambda n: llm.complete_json(LABEL_PROMPT.format(rules=mi.NAME_RULES, name=n), LABEL_SCHEMA,
                                                       max_tokens=300, model=MODEL), part)
        if all(g is None for g in got):
            sys.exit('judge: no answers; Ollama down? stopping to try again')
        for n, g in zip(part, got):
            if g is not None:
                labels[n] = g['label']
        save(state)
        print(f'judge: {len(labels)}/{len(names)}', flush=True)


# ---------- the report ----------
SOURCES = ('renamed', 'approved', 'slates', 'rejected')


def counts(cases: dict) -> str:
    return ', '.join(f"{s} {sum(c['source'] == s for c in cases.values())}" for s in SOURCES)


def expected(arm: str) -> list[str]:
    """The fields in the order the arm asks for them"""
    prompt, note_first = ARMS[arm]
    return list((proposer_schema(2, note_first) if arm in PROPOSER else filing_schema(note_first))['properties'])


def report():
    from app.narratives import embed
    state = saved()
    cases, answers, labels = state['cases'], state['answers'], state.get('labels', {})
    if 'blind' not in state:
        state['blind'] = blind_pairs(state)
        save(state)
    lines = [f'F23 Ptah: the note first, then the name; {len(cases)} cases ({counts(cases)})']

    def unit(texts):
        return embed([t or '-' for t in texts])

    for pair in (list(PROPOSER), list(FILING)):
        a, b = pair
        for label, keep in (('renamed and approved', ('renamed', 'approved')), ('slates', ('slates',)),
                            ('all with an answer', ('renamed', 'approved', 'slates'))):
            ks = [k for k, c in cases.items() if c['source'] in keep and c['answer'] and not in_rules(c['answer']['name'])
                  and (answers.get(a, {}).get(k) or {}).get('name') and (answers.get(b, {}).get(k) or {}).get('name')]
            if not ks:
                continue
            P = unit([cases[k]['answer']['name'] for k in ks])
            PN = unit([cases[k]['answer']['note'] for k in ks])
            per = {}
            for arm in pair:
                got = [answers[arm][k] for k in ks]
                N, NN = unit([g['name'] for g in got]), unit([g.get('note', '') for g in got])
                sim = (N * P).sum(1)
                per[arm] = {'name': sim, 'note': (NN * PN).sum(1), 'own': (N * NN).sum(1), 'near': sim >= NEAR_MATCH,
                            'exact': np.array([norm(g['name']) == norm(cases[k]['answer']['name'])
                                               for g, k in zip(got, ks)]),
                            'has note': np.array([bool(g.get('note')) for g in got])}
            lines.append(f'  {a} against {b}, {label}: {len(ks)} cases named both ways')
            for m, what in (('name', "name like the person's"), ('note', "note like the person's"),
                            ('own', 'name like its own note')):
                mask = np.ones(len(ks), bool) if m == 'name' else per[a]['has note'] & per[b]['has note']
                if not mask.any():  # the filing prompt writes no note today: the note-first arm's alone
                    hb = per[b]['has note']
                    if hb.any():
                        lines.append(f'    {what}: {b} only, {per[b][m][hb].mean():.3f} ({int(hb.sum())} notes)')
                    continue
                d, lo, hi = paired(per[a][m][mask], per[b][m][mask])
                lines.append(f'    {what}: {per[a][m][mask].mean():.3f} -> {per[b][m][mask].mean():.3f} '
                             f'(gain {d:+.3f}, {lo:+.3f} to {hi:+.3f}; {int(mask.sum())} cases)')
            for m in ('exact', 'near'):
                d, lo, hi = paired(per[a][m], per[b][m])
                lines.append(f'    {m} match: {per[a][m].mean():.0%} -> {per[b][m].mean():.0%} '
                             f'({d * 100:+.1f} points, {lo * 100:+.1f} to {hi * 100:+.1f})')
        for arm in pair:  # the labels and words, on every case the arm named
            got = [g for g in answers.get(arm, {}).values() if g.get('name')]
            if not got:
                continue
            judged = [labels[g['name']] for g in got if g['name'] in labels]
            read = ', '.join(f'{lab} {judged.count(lab) / len(judged):.0%}' for lab in
                             ('story name', 'abstract label', 'topic label')) if judged else 'not yet'
            order = np.mean([g.get('order') == expected(arm) for g in got])
            lines.append(f"  {arm}: {len(got)} named; abstract (Adam's count) "
                         f"{np.mean([bool(ABSTRACT.search(g['name'])) for g in got]):.0%}; read: {read}; "
                         f"{np.mean([len(g['name'].split()) for g in got]):.1f} words; fields in the order asked {order:.0%}")
        if a in PROPOSER:  # proposals made, as production would make them (but for an existing name)
            for arm in pair:
                for src in SOURCES:
                    got = [g for k, g in answers.get(arm, {}).items() if cases[k]['source'] == src]
                    if got:
                        made = sum(proposed(g, len(cases[k]['claims'])) for k, g in answers.get(arm, {}).items()
                                   if cases[k]['source'] == src)
                        lines.append(f'    {arm}, {src}: proposed {made} of {len(got)}')
    judged = [labels[c['answer']['name']] for c in cases.values() if c['answer'] and c['answer']['name'] in labels]
    if judged:
        lines.append("  the person's names, read the same way: " + ', '.join(
            f'{lab} {judged.count(lab) / len(judged):.0%}' for lab in ('story name', 'abstract label', 'topic label')))
    a, b = PROPOSER
    named = sorted(k for k, c in cases.items() if c['answer'] and k in answers.get(a, {}) and k in answers.get(b, {}))
    for k in random.Random(8).sample(named, min(8, len(named))):
        lines.append(f"    e.g. person {cases[k]['answer']['name']!r}; {a} {answers[a][k]['name']!r}; "
                     f"{b} {answers[b][k]['name']!r}")
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def main():
    {'ask': ask, 'judge': judge, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
