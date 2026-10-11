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

    u1_uncurated.py file <corpus> | report <corpus> | blind"""
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


def main():
    stage = sys.argv[1]
    if stage == 'blind':
        blind()
    else:
        {'file': file, 'report': report}[stage](sys.argv[2])
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
