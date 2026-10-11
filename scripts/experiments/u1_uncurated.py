"""U1 the machine alone (Oct 11, the person: "run our system without human curation on several different corpuses and
see if it produces motifs on its own that are interesting"). Our filing, started from an EMPTY motif index: no curated
motif, note, name, merge or link. Each claim is shortlisted among the motifs made so far and picked, or given a new
motif named by the filing model, as production does with a shape it hasn't seen; then the new motifs' notes, genres and
groups are drafted, as production drafts them. Nothing is approved, merged or renamed: no person.

The machinery itself isn't untouched by curation (the shortlist's weights, the confidence model and the naming rules
were made from the person's decisions); what's taken away is the index the person built.

Corpora (each in its own sandbox under archives/u1/, never production's files):
    ours      a sample of the claims the person confirmed in their own motifs: the machine's index set beside theirs
              (which claims it puts together that they do, B-cubed precision and recall over the claims)
    a2_1896   A2's claims from the 1896 newspapers
    a3_viral  A3's claims from the Viral Texts reprints
Then a blind test for the person: BLIND motifs the machine made on our claims and BLIND of theirs, each with its name,
note and three claims, mixed, to rate for interest without knowing which is which.

The Golem lumps (Oct 11, at 537 claims: 59 motifs where the person has 424 for the same claims; B-cubed precision 0.20,
recall 0.55): the first motifs it makes are broad, and every later claim, shown them, fits one. The person: "I wonder if
it's possible to second pass a grouping to see if it can split out more motifs". So `split` (Golem II): each motif of
SPLIT_MIN claims or more, Gemma reads its claims and splits them into the distinct tellings inside it, each a motif of
its own that rests on the broad one (the archetype stays above); the leaves scored against the person's index as before.

    u1_uncurated.py file <corpus> | report <corpus> | blind | split <corpus>"""
import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import a2_newspapers as a2  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.utils import Config  # noqa: E402

ROOT = os.path.join(Config.data, 'archives', 'u1')
OUT = os.path.join(harness.EXP, 'u1_uncurated.json')
SAMPLE = 600  # claims a corpus
BLIND = 20
SOURCES = {'a2_1896': os.path.join(harness.EXP, 'a2_newspapers.json'), 'a3_viral': os.path.join(harness.EXP, 'a3_viral_texts.json')}


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


def sandbox(corpus: str):
    """A2's sandbox (every file the filing machinery writes, in its own folder), its index emptied the first time"""
    from app.utils.store import write_json
    a2.WORK = os.path.join(ROOT, corpus)
    box = a2.sandbox()
    from app.analysis import motif_index as mi
    marker = os.path.join(box, 'emptied')
    if not os.path.exists(marker):
        write_json(mi.INDEX, {'next': 1, 'entries': {}, 'claims': {}})
        open(marker, 'w').write('the index started empty: U1')
    return box


def curated() -> dict[str, list[str]]:
    """The person's own: claim -> the done motifs it's confirmed in, from production's index file (read only; by its
    path, as a sandbox points motif_index at an empty copy)"""
    from app.utils.store import read_json
    index = read_json(os.path.join(Config.data, 'motif_index.json'), {'entries': {}})
    out = defaultdict(list)
    for e in index['entries'].values():
        if e.get('merged_into'):
            continue
        if e.get('done'):
            for c in e['claims']:
                if c.get('checked') == 'yes':
                    out[c['claim']].append(e['id'])
    return dict(out)


def claims_of(corpus: str) -> list[dict]:
    rnd = random.Random(11)
    if corpus == 'ours':
        cs = sorted(curated())
        return [{'claim': c, 'source': 'narrative', 'ref': 'u1'} for c in rnd.sample(cs, min(SAMPLE, len(cs)))]
    state = json.load(open(SOURCES[corpus]))
    cs = sorted({c['claim'] for v in state.get('claims', {}).values() for c in v})
    return [{'claim': c, 'source': 'narrative', 'ref': 'u1'} for c in rnd.sample(cs, min(SAMPLE, len(cs)))]


def file(corpus: str):
    state = saved()
    todo = claims_of(corpus)  # picked before the sandbox: 'ours' reads production's index
    sandbox(corpus)
    from app.analysis import motif_index as mi
    print(f'file {corpus}: {len(todo)} claims, from an empty index', flush=True)
    mi.file_claims(todo, limit=len(todo))
    mi.draft_missing()
    index = mi.load()
    state.setdefault(corpus, {})['claims'] = [c['claim'] for c in todo]
    state[corpus]['motifs'] = {e['id']: {'name': e['name'], 'note': e.get('note', ''), 'genre': (e.get('facets') or {}).get('genre'),
                                         'claims': [c['claim'] for c in e['claims']]} for e in mi.live(index)}
    save(state)
    import archive_db as db  # the machine's index into the archives' database, to query beside the others
    rid = db.run('U1', f'file {corpus}', f'our filing from an empty index on {len(todo)} claims of {corpus}')
    ids = dict(zip([c['claim'] for c in todo], db.claims(f'u1_{corpus}', 'sample', [c['claim'] for c in todo],
                                                         'filing (gemma4:26b pick)', 'u1', rid)))
    live = mi.live(index)
    db.motifs(rid, live, {e['id'] for e in live})
    db.filings(rid, [(ids[c['claim']], e['id'], None, False) for e in live for c in e['claims'] if c['claim'] in ids])
    print(f"file {corpus}: {len(state[corpus]['motifs'])} motifs made; run {rid} in {db.DB}", flush=True)


def bcubed(pred: dict[str, set], gold: dict[str, set]) -> tuple[float, float]:
    """B-cubed precision and recall over the claims both cover: for each claim, of the claims sharing a motif with it
    in one index, the share that share one in the other"""
    claims = [c for c in pred if c in gold and pred[c] and gold[c]]
    by_p, by_g = defaultdict(set), defaultdict(set)
    for c in claims:
        for m in pred[c]:
            by_p[m].add(c)
        for m in gold[c]:
            by_g[m].add(c)
    p, r = [], []
    for c in claims:
        mates_p = set().union(*(by_p[m] for m in pred[c]))
        mates_g = set().union(*(by_g[m] for m in gold[c]))
        p.append(len(mates_p & mates_g) / len(mates_p))
        r.append(len(mates_p & mates_g) / len(mates_g))
    return sum(p) / len(p), sum(r) / len(r)


def report(corpus: str):
    import numpy as np
    state = saved()
    s = state[corpus]
    motifs = s['motifs']
    sizes = sorted((len(m['claims']) for m in motifs.values()), reverse=True)
    lines = [f"U1 the machine alone, {corpus}: {len(s['claims'])} claims made {len(motifs)} motifs from nothing; "
             f"sizes {sizes[:10]}..., {sum(1 for n in sizes if n == 1)} of one claim; median {np.median(sizes):.0f}"]
    if corpus == 'ours':
        gold = {c: set(ms) for c, ms in curated().items()}
        pred = defaultdict(set)
        for mid, m in motifs.items():
            for c in m['claims']:
                pred[c].add(mid)
        p, r = bcubed(pred, gold)
        cur = {mid for c in s['claims'] for mid in gold.get(c, ())}
        lines.append(f"  beside the person's index on the same claims ({len(cur)} of their motifs): B-cubed precision "
                     f"{p:.2f} (claims it puts together that they do), recall {r:.2f} (claims they put together that it does)")
    lines.append('  its biggest: ' + '; '.join(f"{m['name']} ({len(m['claims'])})" for m in
                                               sorted(motifs.values(), key=lambda m: -len(m['claims']))[:15]))
    for line in lines:
        print(line, flush=True)
        harness.note(line)


def blind():
    """BLIND motifs the machine made on our claims (three claims or more) and BLIND of the person's, mixed, unlabelled"""
    from app.analysis import motif_index as mi
    state = saved()
    rnd = random.Random(7)
    auto = [m for m in state['ours']['motifs'].values() if len(m['claims']) >= 3]
    theirs = [{'name': e['name'], 'note': e.get('note', ''), 'claims': [c['claim'] for c in e['claims']]}
              for e in mi.live(mi.load()) if e.get('done') and len(e['claims']) >= 3]
    items = [dict(m, by='machine') for m in rnd.sample(auto, min(BLIND, len(auto)))] + \
            [dict(m, by='person') for m in rnd.sample(theirs, min(BLIND, len(theirs)))]
    rnd.shuffle(items)
    state['blind'] = [{'n': i + 1, 'name': m['name'], 'note': m['note'], 'claims': rnd.sample(m['claims'], 3), 'by': m['by']}
                      for i, m in enumerate(items)]
    save(state)
    print(f"blind: {len(state['blind'])} motifs ({sum(m['by'] == 'machine' for m in state['blind'])} the machine's)", flush=True)


SPLIT_MIN = 6  # claims: a smaller motif is left whole
SPLIT_PROMPT = """These claims were filed under one motif, "{name}"{note}:
{claims}

A folklorist would split a broad motif into the distinct tellings inside it: shapes that people retell, each with its
own who-does-what-to-whom (foreign meddling, a trusted figure's betrayal and leaked secrets are three tellings, not one
"enemy within"). Split these claims into the tellings they hold, or keep them as one if they truly are one. Each group:
name: {rules}
note: one sentence, the shape the group's claims share
claims: the numbers of its claims
Every claim in exactly one group; a group of one claim only if it truly stands alone."""
SPLIT_SCHEMA = {"type": "object", "properties": {"groups": {"type": "array", "items": {"type": "object", "properties": {
    "name": {"type": "string", "maxLength": 80}, "note": {"type": "string", "maxLength": 300},
    "claims": {"type": "array", "items": {"type": "integer"}}}, "required": ["name", "note", "claims"]}}},
    "required": ["groups"]}


def split(corpus: str):
    """Golem II: each big motif split by Gemma into the tellings inside it; the leaves into the state and the archives'
    database (each rests on its parent), and scored against the person's index on 'ours'"""
    from app.analysis import llm
    from app.analysis import motif_index as mi
    from app.analysis import motif_signals as ms
    state = saved()
    motifs = state[corpus]['motifs']
    big = {mid: m for mid, m in motifs.items() if len(m['claims']) >= SPLIT_MIN}

    def ask(item):
        mid, m = item
        listed = '\n'.join(f'{n}. {c[:220]}' for n, c in enumerate(m['claims'], 1))
        return llm.complete_json(SPLIT_PROMPT.format(name=m['name'], note=f" ({m['note']})" if m.get('note') else '',
                                                     claims=listed, rules=mi.NAME_RULES), SPLIT_SCHEMA,
                                 max_tokens=3000, model=ms.JUDGE_MODEL)
    leaves = {mid: m for mid, m in motifs.items() if mid not in big}
    for (mid, m), r in zip(big.items(), llm.parallel(ask, list(big.items()))):
        groups = (r or {}).get('groups') or []
        seen = set()
        for k, g in enumerate(groups):
            cs = [m['claims'][n - 1] for n in g.get('claims', []) if 1 <= n <= len(m['claims']) and n - 1 not in seen]
            seen |= {n - 1 for n in g.get('claims', []) if 1 <= n <= len(m['claims'])}
            if cs:
                leaves[f'{mid}.{k + 1}'] = {'name': g['name'], 'note': g['note'], 'claims': cs, 'rests_on': mid}
        rest = [c for n, c in enumerate(m['claims']) if n not in seen]
        if rest or not groups:  # what the split left out stays in the broad motif
            leaves[mid] = dict(m, claims=rest or m['claims'])
    state[corpus]['split'] = leaves
    save(state)
    import numpy as np
    sizes = sorted((len(m['claims']) for m in leaves.values()), reverse=True)
    lines = [f"U1 Golem II, {corpus}: {len(big)} motifs of {SPLIT_MIN}+ claims split by Gemma into the tellings inside; "
             f"{len(motifs)} motifs became {len(leaves)}; sizes {sizes[:10]}..., median {np.median(sizes):.0f}"]
    if corpus == 'ours':
        gold = {c: set(ms_) for c, ms_ in curated().items()}
        for label, idx in (('before', motifs), ('after', leaves)):
            pred = defaultdict(set)
            for mid, m in idx.items():
                for c in m['claims']:
                    pred[c].add(mid)
            p, r = bcubed(pred, gold)
            lines.append(f'  {label} the split: B-cubed precision {p:.2f}, recall {r:.2f}')
    for line in lines:
        print(line, flush=True)
        harness.note(line)


def main():
    stage = sys.argv[1]
    if stage == 'blind':
        blind()
    else:
        {'file': file, 'report': report, 'split': split}[stage](sys.argv[2])
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
