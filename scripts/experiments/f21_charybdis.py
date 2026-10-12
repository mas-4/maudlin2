"""F21 Charybdis: does Straight news work as a sink? (Oct 12, from the person's decision on Straight news: "Keep the
motif only if it works as a sink.") Charybdis swallows whatever sails near her; a sink motif should swallow the claims
that tell nothing, and only those.

The claims, sorted as Procrustes sorts them (F7, f7_procrustes.sorted_claims) with the decision's (c), Straight news
and no motif as one "nothing fit" population (f7_procrustes.with_plain_news): every nothing-fit claim, and as the
control as many claims that fit as Procrustes has nothing-fit claims (seed 21). For each, the learned shortlist with
the claim held out of its motifs, as it was first filed: the motifs it's in now left out for nothing-fit claims (Straight
news aside), the motifs a person took it out of let back in. The filing model (motif_index.name_claim) asked twice on
the same shortlist: without Straight news, and with it (where the weights put it, or last). The picks sorted:

    nothing fit    Straight news alone; Straight news and a wrong motif; a wrong motif alone; a new name; nothing
    fits           the claim's own motif (with or without Straight news); Straight news without it; a wrong motif
                   alone; a new name; nothing

The paper is ~/maudlin-data/papers/charybdis.md (hypotheses and the decision rule written before the run).

    f21_charybdis.py offer      under the GPU lease (the filing model; lease 'f21-offer'); resumes from what it saved
    f21_charybdis.py report     the shares, the paired change with Straight news offered, and the decision rule"""
import json
import os
import random
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f7_procrustes as f7  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'f21_charybdis.json')
SEED = 21
BATCH = 16  # claims asked at once, then saved
DRAWS = 2000  # bootstrap draws for the paired changes


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


def ids_now(index: dict, k: str) -> set[str]:
    return {mi.resolve(index, i) for i in mi._ids(index, k)}


def kept_in(index: dict) -> dict[str, set[str]]:
    """Claim key -> the motifs a person kept it in (checked yes)"""
    out = {}
    for e in mi.live(index):
        for c in e['claims']:
            if c.get('checked') == 'yes':
                out.setdefault(mi.key(c['claim']), set()).add(e['id'])
    return out


def draw(index: dict) -> dict:
    """The claims: every nothing-fit one, and the fits control"""
    from app.analysis import filing_confidence as fc
    registered = f7.sorted_claims(index)
    kinds, extras, plain = f7.with_plain_news(index, registered)
    made = f7.carved()
    words = {mi.key(c): (c, s) for c, _, s, _ in fc.labeled(index)} | extras
    kept = kept_in(index)
    out = {}
    for k, kind in kinds.items():
        if kind == 'nothing fit' and k in words:
            out[k] = {'group': 'nothing fit', 'core': registered.get(k) == 'nothing fit',
                      'sub': 'carved' if k in made else 'plain' if k in plain else 'other'}
    pool = sorted(k for k, kind in kinds.items() if kind == 'fits' and k in words and kept.get(k))
    n = sum(1 for kind in registered.values() if kind == 'nothing fit')
    for k in random.Random(SEED).sample(pool, min(n, len(pool))):
        out[k] = {'group': 'fits', 'core': False, 'sub': '', 'own': sorted(kept[k])}
    for k, c in out.items():
        c.update(key=k, claim=words[k][0], source=words[k][1])
    return out


def shortlist(index: dict, sig, w: dict, L: dict, claim: str, leave: set[str]) -> list[dict]:
    """The learned shortlist as filing builds it (motif_retriever.learned_shortlist), the claim held out of its motifs
    and the motifs in `leave` left out; a person's "not this one" not applied (see the paper)"""
    from app.analysis import motif_retriever as mr
    entries = sig.entries
    score, F = mr.learned_scores(sig, claim, w, L, leave_out=True)
    alike = (F[:, :3].max(1) >= mi.SHOWN_FLOOR) & np.array([e['id'] not in leave for e in entries])
    order = [int(i) for i in np.argsort(-score) if alike[i]]
    top = order[:mi.SHOWN]
    tree = mr._tree(entries, {e['id']: n for n, e in enumerate(entries)})
    more = sorted({x for m in top for x in tree[m] if x not in top and alike[x]}, key=lambda x: -score[x])[:mr.TREE_MORE]
    return [entries[i] for i in top + more] + [s for s in mr.seeds(index, claim, sig.vec) if s['id'] not in leave]


def offer():
    from app.analysis import llm
    from app.analysis import motif_retriever as mr
    from app.analysis import motif_signals as ms
    index = mi.load()
    sn = f7.straight_news(index)
    if sn is None:
        raise SystemExit('no motif called Straight news')
    state = saved()
    if not state.get('claims'):
        state = {'straight news': sn, 'claims': draw(index)}
        save(state)
    claims = state['claims']
    print(f"offer: {len(claims)} claims ({Counter(c['group'] for c in claims.values())}), Straight news is {sn}", flush=True)
    w, L = mr.weights(), mr.learned()
    if not (w and L):
        raise SystemExit('the learned shortlist is not trained')
    sig = ms.Signals(index, mr.Vectors())
    todo = [c for c in claims.values() if 'arms' not in c]
    sig.prepare([c['claim'] for c in todo])
    by_id = index['entries']

    def shown_as(c: dict, entries: list[dict]) -> list[dict]:  # each motif shown with its own claims, this one out
        return [{**e, 'claims': [x for x in e['claims'] if mi.key(x['claim']) != c['key']]} for e in entries]

    def ask(c: dict) -> dict:
        arms = {}
        for arm in ('without', 'with'):
            named = mi.name_claim(c['claim'], shown_as(c, c['lists'][arm]))
            arms[arm] = None if named is None else {'picked': [e['id'] for e in named['existing']], 'new': named['new']}
        return arms
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        for c in batch:
            leave = (ids_now(index, c['key']) - {sn}) if c['group'] == 'nothing fit' else set()
            base = shortlist(index, sig, w, L, c['claim'], leave)
            c['natural'] = any(e['id'] == sn for e in base)
            without = [e for e in base if e['id'] != sn]
            c['shown'] = [e['id'] for e in base]
            c['lists'] = {'without': without, 'with': base if c['natural'] else without + [by_id[sn]]}
        for c, arms in zip(batch, llm.parallel(ask, batch)):
            del c['lists']
            if arms and all(arms.values()):
                c['arms'] = arms
        save(state)
        print(f'offer: {min(start + BATCH, len(todo))}/{len(todo)}', flush=True)
    sig.save()


def sort_pick(c: dict, arm: str, sn: str) -> str:
    a = c['arms'][arm]
    picked = set(a['picked'])
    sink = sn in picked
    if c['group'] == 'nothing fit':
        wrong = bool(picked - {sn})
        return ('sink and wrong' if wrong else 'sink alone') if sink else 'wrong alone' if wrong else \
            'new name' if a['new'] else 'nothing'
    own = bool(picked & set(c['own']))
    if own:
        return 'own and sink' if sink else 'own'
    return 'sink without own' if sink else 'wrong alone' if picked else 'new name' if a['new'] else 'nothing'


def paired(a: list[bool], b: list[bool]) -> tuple[float, float, float]:
    """The change in share from a to b, with its 95% bootstrap interval over claims"""
    a, b = np.array(a, float), np.array(b, float)
    if not len(a):
        return float('nan'), float('nan'), float('nan')
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(a), (DRAWS, len(a)))
    d = b[idx].mean(1) - a[idx].mean(1)
    return float(b.mean() - a.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def report():
    state = saved()
    sn, claims = state['straight news'], [c for c in state['claims'].values() if 'arms' in c]
    groups = {'nothing fit, Procrustes\'s 112': [c for c in claims if c['core']],
              'nothing fit, all (c)': [c for c in claims if c['group'] == 'nothing fit'],
              'carved': [c for c in claims if c['sub'] == 'carved'],
              'plain': [c for c in claims if c['sub'] == 'plain'],
              'fits': [c for c in claims if c['group'] == 'fits']}
    out = {'straight news': sn, 'groups': {}}
    lines = []
    for name, cs in groups.items():
        if not cs:
            continue
        g = {'n': len(cs), 'reach': round(float(np.mean([c['natural'] for c in cs])), 3)}
        for arm in ('without', 'with'):
            tally = Counter(sort_pick(c, arm, sn) for c in cs)
            g[arm] = {k: round(v / len(cs), 3) for k, v in sorted(tally.items())}
        if name == 'fits':
            own = lambda c, arm: sort_pick(c, arm, sn) in ('own', 'own and sink')  # noqa: E731
            g['own picked, change'] = [round(x, 3) for x in paired([own(c, 'without') for c in cs], [own(c, 'with') for c in cs])]
            g['swallowed'] = g['with'].get('sink without own', 0.0)
            lines.append(f"fits ({len(cs)}): Straight news reached the shortlist for {g['reach']:.0%}; offered, it "
                         f"swallowed {g['swallowed']:.0%} (picked without the claim's own motif); own motif picked "
                         f"{g['own picked, change'][0]:+.1%} ({g['own picked, change'][1]:+.1%} to {g['own picked, change'][2]:+.1%})")
        else:
            wrong = lambda c, arm: sort_pick(c, arm, sn) in ('wrong alone', 'sink and wrong')  # noqa: E731
            g['wrong picked, change'] = [round(x, 3) for x in paired([wrong(c, 'without') for c in cs], [wrong(c, 'with') for c in cs])]
            wr = float(np.mean([wrong(c, 'without') for c in cs]))
            lines.append(f"{name} ({len(cs)}): Straight news reached the shortlist for {g['reach']:.0%}; offered, it was "
                         f"picked alone for {g['with'].get('sink alone', 0):.0%} (with a wrong motif "
                         f"{g['with'].get('sink and wrong', 0):.0%}); a wrong motif picked {wr:.0%} without it, "
                         f"{g['wrong picked, change'][0]:+.1%} with it ({g['wrong picked, change'][1]:+.1%} to "
                         f"{g['wrong picked, change'][2]:+.1%}); new names {g['without'].get('new name', 0):.0%} and "
                         f"{g['with'].get('new name', 0):.0%}")
        out['groups'][name] = g
    core, fits = out['groups'].get("nothing fit, Procrustes's 112"), out['groups'].get('fits')
    if core and fits:
        works = -core['wrong picked, change'][0] >= 0.10 and fits['swallowed'] <= 0.05 and fits['own picked, change'][0] >= -0.03
        out['works as a sink'] = works
        lines.append(f"decision rule (the paper's): Straight news {'works' if works else 'does not work'} as a sink "
                     f"(wrong picks on the 112 {core['wrong picked, change'][0]:+.1%}, needs -10 points or more; "
                     f"fits swallowed {fits['swallowed']:.0%}, at most 5%; own picks {fits['own picked, change'][0]:+.1%}, "
                     f"at least -3 points)")
    state['report'] = out
    save(state)
    for line in lines:
        line = 'F21 Charybdis: ' + line
        print(line, flush=True)
        harness.note(line)


def main():
    {'offer': offer, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
