"""F26 Tiresias: the point a teller makes, for the shortlist to catch claims by (Oct 21; the person: "What about a
simple claim retelling: 'What is the teller trying to say with their statement?'"). Tiresias, the blind seer, saw what
was meant where others saw only what was said.

The shortlist finds what a claim is about and misses the move made with it (Indra's Net's 159 hard misses: Arguments,
Values and Exhortations missed twice as often). Gemma 4 26B writes each claim's point, what the teller means the
listener to take from it, with kinds in place of names, never a guess at motive; once from the claim alone (bare), once
with what it came from (sources: the posts, the fact-check, the shows' quotes, the Focus Group passage).

    signals        the point's likeness (mxbai) to each motif's name and note, and its best likeness to the points of
                   the motif's other claims (the claim's own left out); each arm two more signals in the learned
                   weighting, never in place of the claim

The paper is ~/maudlin-data/papers/tiresias.md (hypotheses and the decision rule written before the run).

    f26_tiresias.py ask       under the GPU lease: both points for every claim of every harness motif; resumes
    f26_tiresias.py report    the harness without and with each arm, by genre, the hard misses, the decision"""
import os
import sqlite3
import sys
from datetime import datetime as dt

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts')
from app.analysis import llm, local_models  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

DB = os.path.join(harness.EXP, 'f26_tiresias.sqlite')
MODEL = local_models.BIG
ARMS = ('bare', 'sources')
CHUNK = 40  # claims asked, then saved
MOVES = {'Arguments', 'Values', 'Exhortations'}
STORIES = {'Plots', 'Theories'}
PROMPT = """A claim people are telling or arguing over:
{claim}
{sources}
What point is the teller making with it? In one plain sentence, say what they mean the listener to take from it: the \
conclusion, charge or lesson it carries, with kinds of people, places and things in place of particular ones ("a \
leader", "the other party", "the press"), and no names or dates. Say what is meant, not why they say it: no guesses \
about motives. If it only reports what happened, say "It only reports what happened"."""
SCHEMA = {"type": "object", "properties": {"point": {"type": "string", "maxLength": 300}}, "required": ["point"]}


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute('create table if not exists points (key text, arm text, claim text, sources text, point text, at text, '
                'primary key (key, arm))')
    return con


def sources_of(claim: str) -> str:
    """What the claim came from, as the checker's claim detail gathers it, in a few hundred words; '' when nothing is
    left of it"""
    import validate
    try:
        d = validate.claim_detail(claim)
    except Exception:  # noqa: BLE001 - the claim alone, then
        return ''
    parts = []
    if d.get('examples'):
        parts.append('Posts telling it:\n' + '\n'.join(f'- {str(t)[:280]}' for t in d['examples'][:6]))
    if d.get('piece') or d.get('summary'):
        parts.append(f"The fact-check it came from ({d.get('source', '')}):\n{(d.get('piece') or d.get('summary'))[:1500]}")
    if d.get('tellings'):
        parts.append('Told on the shows:\n' + '\n'.join(f"- {t.get('show', '')}: \"{(t.get('quote') or t.get('claim') or '')[:300]}\""
                                                        for t in d['tellings'][:4]))
    if d.get('quote'):
        around = d.get('context') or {}
        parts.append(f"Said in a focus group: \"{d['quote']}\"\nAround it: {(around.get('before') or '')[-400:]} … "
                     f"{(around.get('after') or '')[:300]}")
    return '\n\n'.join(parts)


def claims_to_ask(data: dict) -> dict[str, str]:
    """Every claim of every motif in the harness: claim key -> text"""
    out = {k: c['claim'] for k, c in data['claims'].items()}
    for e in data['entries'].values():
        for c in e.get('claims', []):
            out.setdefault(mi.key(c['claim']), c['claim'])
    return out


def ask():
    data, con = harness.load(), connect()
    todo_all = claims_to_ask(data)
    have = {(k, a) for k, a in con.execute('select key, arm from points')}
    todo = [(k, t) for k, t in todo_all.items() if any((k, a) not in have for a in ARMS)]
    print(f'Tiresias: {len(todo_all) - len(todo)} of {len(todo_all)} claims asked already; asking {len(todo)}', flush=True)

    def one(item):
        k, text = item
        src = sources_of(text)
        got = {}
        for arm in ARMS:
            if (k, arm) in have:
                continue
            shown = f'\nWhat it came from:\n{src}\n' if arm == 'sources' and src else ''
            a = llm.complete_json(PROMPT.format(claim=text, sources=shown), SCHEMA, max_tokens=200, model=MODEL)
            if a and a.get('point'):
                got[arm] = (src if arm == 'sources' else '', ' '.join(a['point'].split()))
        return got
    for n in range(0, len(todo), CHUNK):
        part = todo[n:n + CHUNK]
        for (k, text), got in zip(part, llm.parallel(one, part)):
            for arm, (src, point) in (got or {}).items():
                con.execute('insert or replace into points values (?, ?, ?, ?, ?, ?)',
                            (k, arm, text, src, point, dt.now().isoformat(timespec='seconds')))
        con.commit()
        print(f'Tiresias: asked {min(n + CHUNK, len(todo))}/{len(todo)}', flush=True)


def signals(data: dict, con, arm: str, vec) -> dict:
    """The arm's two signals as the harness takes them: {name: (data, claim key) -> a score per motif}"""
    points = dict(con.execute('select key, point from points where arm = ?', (arm,)))
    keys = sorted(points)
    P = dict(zip(keys, vec([points[k] for k in keys])))
    ids = data['ids']
    N = vec([mi.described(data['entries'][m]) for m in ids])
    of_motif = {m: [mi.key(c['claim']) for c in data['entries'][m].get('claims', [])] for m in ids}

    zero = np.zeros(len(ids))
    M = np.vstack([P[k] for k in keys]) if keys else np.zeros((0, 1))
    row = {k: i for i, k in enumerate(keys)}
    members = [np.array([row[x] for x in of_motif[m] if x in row], dtype=int) for m in ids]
    memo = {}
    for k in data['claims']:
        if k not in P:
            continue
        sims = M @ P[k]
        own = row[k]
        near = np.zeros(len(ids))
        for j, idx in enumerate(members):
            idx = idx[idx != own]
            if len(idx):
                near[j] = float(sims[idx].max())
        memo[k] = (N @ P[k], near)
    return {f'{arm} point note': lambda d, k: memo[k][0] if k in memo else zero,
            f'{arm} point near': lambda d, k: memo[k][1] if k in memo else zero}


def by_genre(data: dict, base: dict, new: dict) -> dict[str, tuple[int, float, float]]:
    """Top-12 recall without and with, for filings in each kind of motif"""
    at = data['at']
    out = {}
    for label, test in (('moves (Arguments, Values, Exhortations)', MOVES), ('stories (Plots, Theories)', STORIES)):
        pairs = [(k, m) for k, c in data['claims'].items() for m in c['truth']
                 if (data['entries'][m].get('facets') or {}).get('genre') in test]
        if pairs:
            out[label] = (len(pairs), float(np.mean([base[k][at[m]] < 12 for k, m in pairs])),
                          float(np.mean([new[k][at[m]] < 12 for k, m in pairs])))
    return out


def report():
    data, con = harness.load(), connect()
    vec = mr.Vectors()
    asked = {a: con.execute('select count(*) from points where arm = ?', (a,)).fetchone()[0] for a in ARMS}
    harness.note(f"F26 Tiresias: points for {asked} claims ({len(claims_to_ask(data))} in the harness's motifs); "
                 f"{len(data['claims'])} claims tested, {sum(len(c['truth']) for c in data['claims'].values())} filings")
    base = harness.ranks(data)
    results = {}
    for arm in ARMS:
        extra = signals(data, con, arm, vec)
        out = harness.evaluate(data, extra=extra, label=f'F26 Tiresias, {arm}')
        new = harness.ranks(data, extra)
        results[arm] = (out, new)
        for label, (n, b, w) in by_genre(data, base, new).items():
            harness.note(f'F26 {arm}, {label}: {n} filings, top-12 {b:.1%} -> {w:.1%} ({w - b:+.1%})')
        back = out['brought back'] / max(1, out['misses before'])
        harness.note(f"F26 {arm}: hard misses (outside the top 40) brought back {out['brought back']} of "
                     f"{out['misses before']} ({back:.0%}), {out['newly missed']} new")
    # Which hard misses the sources arm brings back, to read
    at = data['at']
    new = results['sources'][1]
    for k, c in data['claims'].items():
        for m in c['truth']:
            if base[k][at[m]] >= 40 and new[k][at[m]] < 40:
                print(f"  back: {c['claim'][:110]} -> {data['entries'][m]['name']} ({base[k][at[m]]} -> {new[k][at[m]]})")
    # The decision rule
    s_out = results['sources'][0]
    gain = s_out['with'][12] - s_out['base'][12]
    low = s_out.get('gain interval', {}).get(12, (0, 0))[0]
    genre = by_genre(data, base, results['sources'][1])
    moves = genre.get('moves (Arguments, Values, Exhortations)', (0, 0, 0))
    bare_gain = results['bare'][0]['with'][12] - results['bare'][0]['base'][12]
    b_low = results['bare'][0].get('gain interval', {}).get(12, (0, 0))[0]
    b_moves = by_genre(data, base, results['bare'][1]).get('moves (Arguments, Values, Exhortations)', (0, 0, 0))
    if gain >= 0.01 and low > 0 and moves[2] - moves[1] >= 0.03:
        verdict = f'in production with sources (top-12 {gain:+.1%}, moves {moves[2] - moves[1]:+.1%})'
    elif bare_gain >= 0.01 and b_low > 0 and b_moves[2] - b_moves[1] >= 0.03:
        verdict = f'in production without sources (top-12 {bare_gain:+.1%}, moves {b_moves[2] - b_moves[1]:+.1%})'
    else:
        verdict = (f'not kept: sources top-12 {gain:+.1%} (interval from {low:+.1%}), moves {moves[2] - moves[1]:+.1%}; '
                   f'bare top-12 {bare_gain:+.1%}')
    harness.note(f'F26 decision: {verdict}')


if __name__ == '__main__':
    {'ask': ask, 'report': report}[sys.argv[1]]()
