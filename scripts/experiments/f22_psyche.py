"""F22 Psyche: the claim organizer run alongside the filing (Oct 13; decision 7 of Fable's handoff, Oct 12; the person:
"for testing at least, we can run it alongside or something to get some data"). Aphrodite set Psyche a heap of mixed
grains to sort; here the heap is a paraphrase group's posts and the grains are the tellings stitched into its claim.
The organizer (app/analysis/claim_organizer.py) asks Gemma which posts tell each picked motif; motifs on different
posts make a split, one child claim drafted per telling; motifs on the same posts are layers of one telling.

    chimera   arm 1, the Chimera's claims (80 the person filed in 3+ motifs, 80 in one; Isis's re-read posts): the
              filing's own picks (the confidence model past FILE, the claim held out as if new), the triggers on the
              person's motifs and on those picks, and the organizer on each set of 2+ picks
    forward   arm 2, claims from posts dated SINCE or later, outside the Chimera's: the triggers on their filings, the
              organizer on those with 2+; each result also into the proposals store (open splits for the checker,
              no-splits kept with their reason). Run again later, it reads only new claims or changed picks
    file      every parent and child scored as the Blind Men score theirs (the shortlist's 12, the confidence model)
    report    the paper's six hypotheses, the overlaps 0.3 and 0.7 read from the same answers, and decision 7's three
              numbers now

    f22_psyche.py chimera | forward | file | report      queued (exp_queue.py), under the GPU lease but report
The paper is ~/maudlin-data/papers/psyche.md."""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime as dt

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f9_isis as isis  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import claim_organizer as co  # noqa: E402
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f22_psyche.json')
FILE = 0.5  # a motif when the confidence model's fit is at least this (Isis's, the Blind Men's)
SINCE = '2026-10-06'
OVERLAPS = (0.3, 0.5, 0.7)
CHUNK = 50  # claims whose layers and shapes are asked between saves (the hourly run takes the GPU back each hour)
TRIGGERS = ('facing motifs', 'two of one genre', 'varied group', 'many authors', 'middling scores', 'also')


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


class Filer:
    """The confidence model's fit for a claim's shortlist of 12, the claim scored as a new one (out of its motifs, and
    not counted as in any), best first"""

    def __init__(self, index: dict):
        m = fc.model()
        if not m:
            sys.exit('no confidence model')
        self.coef, self.bias = np.array([m['weights'][f] for f in fc.FEATURES]), m['bias']
        self.scorer = fc.Scorer(index, mr.weights())

    def prepare(self, claims: list[str]):
        for i in range(0, len(claims), CHUNK):
            chunk = [c for c in claims[i:i + CHUNK] if mi.key(c) not in self.scorer.signals.layered]
            if chunk:
                self.scorer.signals.prepare(chunk)
                self.scorer.signals.save()
                print(f'prepare: {min(i + CHUNK, len(claims))}/{len(claims)}', flush=True)
        self.scorer.signals.prepare(claims, ask=False)

    def fit(self, claim: str) -> list[list]:
        k = mi.key(claim)
        held = self.scorer.motifs_of.pop(k, None)
        try:
            ids = self.scorer.candidates(claim)
            if not ids:
                return []
            p = 1 / (1 + np.exp(-(self.scorer.rows(claim, ids, 'narrative') @ self.coef + self.bias)))
        finally:
            if held is not None:
                self.scorer.motifs_of[k] = held
        return sorted(([eid, round(float(v), 3)] for eid, v in zip(ids, p)), key=lambda x: -x[1])


def _group(g: dict | None) -> dict:
    return {k: g.get(k) for k in ('variety', 'authors', 'posts')} if g else {}


def _ref(index: dict, claim: str) -> str:
    return next((rec.get('ref', '') for _, rec in co.picks(index, claim)), '')


def chimera():
    state = saved()
    rows = state.setdefault('chimera', {})
    index = mi.load()
    groups = isis.saved()['groups']
    need = [c for c in groups if 'filing' not in rows.get(c, {})]
    if need:
        filer = Filer(index)
        filer.prepare(need)
        for n, c in enumerate(need):
            rows.setdefault(c, {})['filing'] = filer.fit(c)
            if n % 20 == 0:
                filer.scorer.signals.save()
                save(state)
                print(f'chimera: picks {n + 1}/{len(need)}', flush=True)
        filer.scorer.signals.save()
        save(state)
    reports, also = co.report_groups(index), co.alsos()
    live = {e['id'] for e in mi.live(index)}
    for n, (claim, g) in enumerate(groups.items()):
        r = rows[claim]
        yours = [m for m in dict.fromkeys(mi.resolve(index, m) for m in g['motifs']) if m in live]
        theirs = [eid for eid, p in r['filing'] if p >= FILE]
        group = co.group_of(claim, _ref(index, claim), reports)
        r.update(kind=g['kind'], yours=yours, theirs=theirs, group=_group(group))
        r['triggers'] = {'yours': co.triggers(claim, index, group, also, motifs=yours),
                         'theirs': co.triggers(claim, index, group, also, fits=dict(r['filing']), motifs=theirs)}
        read = r.setdefault('read', {})
        for arm, ms in (('yours', yours), ('theirs', theirs)):
            if arm in read:
                continue
            other = read.get('theirs' if arm == 'yours' else 'yours')
            if other and sorted(other['motifs']) == sorted(ms):  # the same picks: read once
                read[arm] = other
                continue
            got = co.organize(claim, g['posts'], ms, index)
            if got.get('failed'):
                print(f'chimera: no answer for claim {n}; asked again next time', flush=True)
                continue
            read[arm] = got
        save(state)
        print(f'chimera: read {n + 1}/{len(groups)}', flush=True)


def forward():
    state = saved()
    rows = state.setdefault('forward', {})
    index = mi.load()
    store = mp.load()
    reports, also = co.report_groups(index), co.alsos()
    skip = set(isis.saved()['groups'])
    claims = {}
    for e in mi.live(index):
        for c in e['claims']:
            if c.get('source') == 'narrative' and (c.get('date') or '') >= SINCE and c['claim'] not in skip:
                claims.setdefault(c['claim'], c)
    print(f'forward: {len(claims)} claims from posts since {SINCE}', flush=True)
    for n, (claim, rec) in enumerate(claims.items()):
        motifs = [e['id'] for e, _ in co.picks(index, claim)]
        if claim in rows and rows[claim].get('motifs') == motifs and 'read' in rows[claim]:
            continue  # read already, with these picks
        group = co.group_of(claim, rec.get('ref', ''), reports)
        r = {'motifs': motifs, 'date': rec.get('date'), 'group': _group(group),
             'triggers': co.triggers(claim, index, group, also), 'at': dt.now().isoformat(timespec='seconds')}
        if len(motifs) < 2:
            r['read'] = {'split': False, 'reason': 'one motif picked', 'motifs': motifs, 'tells': {}}
        elif co.asked(store, claim, motifs):  # read already (the organizer in production, or an earlier run)
            i = next(co.proposal_id(claim, motifs, s) for s in (True, False) if co.proposal_id(claim, motifs, s) in store)
            p = store[i]
            r['proposal'] = i
            r['read'] = {'split': p['kind'] == 'split', 'reason': p['reason'], 'motifs': motifs, 'tells': {},
                         'children': [{'claim': c['claim'], 'motifs': c['motifs']} for c in p['args'].get('children', [])]}
        else:
            posts = co.posts_of((group or {}).get('keys') or [])
            got = co.organize(claim, [p['text'] for p in posts], motifs, index)
            if got.get('failed'):
                print(f'forward: no answer for claim {n}; asked again next time', flush=True)
                continue
            r['read'] = got
            r['proposal'] = co.propose(store, got, r['triggers'], [p['keys'] for p in posts])
            mp.save(store)
            store = mp.load()
        rows[claim] = r
        save(state)
        print(f'forward: {n + 1}/{len(claims)}', flush=True)


def children(state: dict) -> list[str]:
    out = []
    for part in ('chimera', 'forward'):
        for r in state.get(part, {}).values():
            for read in ([r['read'].get('yours'), r['read'].get('theirs')] if part == 'chimera' else [r.get('read')]):
                out += [c['claim'] for c in (read or {}).get('children', [])]
    return sorted(set(out))


def file():
    state = saved()
    scored = state.setdefault('scored', {})
    todo = [c for c in children(state) if c not in scored]
    if not todo:
        return
    filer = Filer(mi.load())
    filer.prepare(todo)
    for n, c in enumerate(todo):
        scored[c] = filer.fit(c)
        if n % 20 == 0:
            filer.scorer.signals.save()
            save(state)
            print(f'file: {n + 1}/{len(todo)}', flush=True)
    filer.scorer.signals.save()
    save(state)


def spread_at(read: dict, overlap: float) -> bool:
    """Two tellings or more in the posts, at this overlap (the answers kept; no question asked again)"""
    was = co.SAME_POSTS
    co.SAME_POSTS = overlap
    try:
        found, _ = co.tellings(dict(read.get('tells') or {}))
    finally:
        co.SAME_POSTS = was
    return len(found) >= 2


def rate(xs: list) -> str:
    return f'{np.mean(xs):.0%} of {len(xs)}' if xs else 'none'


def past(fits: list, line: float = FILE) -> set[str]:
    return {eid for eid, p in fits or [] if p >= line}


def report():
    state = saved()
    ch, fw, scored = state.get('chimera', {}), state.get('forward', {}), state.get('scored', {})
    out = {}
    # 1: spread on the person's motifs, the 3+ claims
    yours3 = [r['read']['yours'] for r in ch.values() if r.get('kind') == '3+ motifs' and 'yours' in r.get('read', {})]
    out['1 spread on yours, 3+'] = {str(o): rate([spread_at(x, o) for x in yours3]) for o in OVERLAPS}
    out['1 split drafted on yours, 3+'] = rate([x['split'] for x in yours3])
    out['1 reasons, 3+'] = Counter(x['reason'].split(':')[0] for x in yours3 if not x['split']).most_common()
    # 2: the filing's picks, by the person's filing
    by = {}
    for kind in ('3+ motifs', 'one motif'):
        rs = [r for r in ch.values() if r.get('kind') == kind and 'theirs' in r.get('read', {})]
        by[kind] = {'all': [r['read']['theirs']['split'] for r in rs],
                    '2+ picks': [r['read']['theirs']['split'] for r in rs if len(r['theirs']) >= 2],
                    'picks': float(np.mean([len(r['theirs']) for r in rs])) if rs else 0.0}
        for o in OVERLAPS:
            by[kind][f'spread {o}'] = [spread_at(r['read']['theirs'], o) for r in rs]
    out['2 split on the filing\'s picks'] = {k: {m: rate(v) if isinstance(v, list) else round(v, 2) for m, v in d.items()}
                                             for k, d in by.items()}
    gap = (np.mean(by['3+ motifs']['all']) - np.mean(by['one motif']['all'])) if by['3+ motifs']['all'] and by['one motif']['all'] else None
    out['2 gap (points)'] = round(100 * gap, 1) if gap is not None else None
    # 3: children against their parent, the 3+ claims split on the person's motifs
    narrower, reach_p, reach_c = [], [], []
    for r in ch.values():
        x = (r.get('read') or {}).get('yours')
        if r.get('kind') != '3+ motifs' or not x or not x['split'] or not all(c['claim'] in scored for c in x['children']):
            continue
        kids = [past(scored[c['claim']]) for c in x['children']]
        parent = past(r['filing'])
        narrower.append(len(parent) - float(np.mean([len(k) for k in kids])))
        reach_p.append(len(parent & set(r['yours'])))
        reach_c.append(len(set().union(*kids) & set(r['yours'])))
    out['3 claims'] = len(narrower)
    if narrower:
        out['3 motifs past 0.5: parent minus mean child'] = round(float(np.mean(narrower)), 2)
        out["3 the person's motifs reached: parent, children"] = [round(float(np.mean(reach_p)), 2),
                                                                  round(float(np.mean(reach_c)), 2)]
    # 4: triggers, split rate when each fires and when it doesn't, claims with 2+ picks
    pools = {'arm 1 (filing\'s picks)': [(r['triggers']['theirs'], r['read']['theirs']['split']) for r in ch.values()
                                         if len(r.get('theirs', [])) >= 2 and 'theirs' in r.get('read', {})],
             'arm 2 (forward)': [(r['triggers'], r['read']['split']) for r in fw.values() if len(r['motifs']) >= 2]}
    pools['both'] = pools["arm 1 (filing's picks)"] + pools['arm 2 (forward)']
    out['4 triggers'] = {}
    for name, pool in pools.items():
        t = {}
        for trig in TRIGGERS:
            on = [s for f, s in pool if trig in f]
            off = [s for f, s in pool if trig not in f]
            ratio = (np.mean(on) / np.mean(off)) if on and off and np.mean(off) > 0 else None
            t[trig] = {'fires': len(on), 'split when fired': rate(on), 'split when not': rate(off),
                       'ratio': round(float(ratio), 2) if ratio is not None else None}
        out['4 triggers'][name] = t
    # 5: forward split rate; how many fire any trigger
    two = [r for r in fw.values() if len(r['motifs']) >= 2]
    out['5 forward'] = {'claims': len(fw), '2+ picks': len(two), 'any trigger': rate([bool(r['triggers']) for r in fw.values()]),
                        'split, 2+ picks': rate([r['read']['split'] for r in two]),
                        'children a split': round(float(np.mean([len(r['read'].get('children', [])) for r in two
                                                                 if r['read']['split']])), 2) if any(r['read']['split'] for r in two) else 0}
    # 6: the person's decisions on the forward proposals
    store = mp.load()
    decided = Counter()
    for r in fw.values():
        p = store.get(r.get('proposal') or '')
        if p and p['kind'] == 'split':
            decided[p['status'] + (' (edited)' if p.get('final') else '')] += 1
    out['6 decided'] = dict(decided)
    # decision 7's three numbers now
    index = mi.load()
    also = co.alsos()
    motifs_of, source = defaultdict(set), {}
    for e in mi.live(index):
        for c in e['claims']:
            motifs_of[c['claim']].add(e['id'])
            s = c.get('source', '')
            source[c['claim']] = s if s in ('narrative', 'shows', 'Focus Group') else 'fact-checks'
    watch = {}
    for s in ('narrative', 'shows', 'Focus Group', 'fact-checks'):
        cl = [c for c in motifs_of if source[c] == s]
        watch[s] = {'claims': len(cl), '3+ motifs': rate([len(motifs_of[c]) >= 3 for c in cl]),
                    'also': rate([mi.key(c) in also for c in cl])}
    from app.utils.store import read_json
    history = read_json(mi.METRICS, {})
    last = max(history) if history else None
    watch['sure share'] = (last, history[last].get('sure_share')) if last else None
    watch['splits applied'] = len(index.get('tellings', {}))
    out['decision 7 now'] = watch
    state['report'] = out
    save(state)
    filing = out["2 split on the filing's picks"]
    line = (f"F22 Psyche: on the person's motifs, the 3+ motif claims spread over different posts "
            f"{out['1 spread on yours, 3+']['0.5']} (split drafted {out['1 split drafted on yours, 3+']}); on the "
            f"filing's own picks, split {filing.get('3+ motifs', {}).get('all')} of the 3+ against "
            f"{filing.get('one motif', {}).get('all')} of the one-motif (gap {out['2 gap (points)']} points); ")
    if narrower:
        reached = out["3 the person's motifs reached: parent, children"]
        line += (f"children land in {out['3 motifs past 0.5: parent minus mean child']} fewer motifs past 0.5 than their "
                 f"parent, reaching {reached[1]} of the person's motifs against {reached[0]}; ")
    both = out['4 triggers']['both']
    line += 'split ratio when each trigger fires: ' + ', '.join(f"{t} {v['ratio']} ({v['fires']})" for t, v in both.items())
    line += (f"; forward: {out['5 forward']['split, 2+ picks']} of claims with 2+ motifs split; posts claims in 3+ motifs "
             f"now {watch['narrative']['3+ motifs']}, also {watch['narrative']['also']}")
    print(json.dumps(out, indent=1), flush=True)
    print(line, flush=True)
    harness.note(line)


def main():
    {'chimera': chimera, 'forward': forward, 'file': file, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
