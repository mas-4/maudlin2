"""F28 the Judgement of Paris: which model picks the motifs from the shortlist (Oct 22). Three shortlist experiments in
a row moved nothing, so the next lever is the pick itself. Gemma 4 26B has made it since Oct 5; Clef, Clef Flash and
Nimble v3 were tried only as the judge (the Norns, Oct 17). Each answers production's own question
(motif_filing.REUSE_PROMPT, options as motif_filing.name_claim writes them) on the learned shortlist's held-out top
twelve, against the person's confirmed filings, with the filings the person made by hand apart from the model-made
ones: the first lean against Gemma (it didn't pick them at the time), the second towards it (it picked them).

The paper is ~/maudlin-data/papers/judgement-of-paris.md (hypotheses and the decision rule written before the run).

    f28_paris.py ask       under the GPU lease: the prompts built once, then each model in turn; resumes
    f28_paris.py report    found (overall, hand-made, model-made), wrong, none, seconds a claim, paired intervals
                           against Gemma, the decision"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from f17_castor_pollux import hand_added  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_filing as mf  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402

DB = os.path.join(harness.EXP, 'f28_paris.sqlite')
GEMMA = 'gemma4:26b'
MODELS = [GEMMA, 'clef:latest', 'clef-flash:latest', 'nimble-v3:latest']
SAMPLE, SEED, SHOWN, ROUND = 600, 28, 12, 8
BOOTS = 1000


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute('create table if not exists prompts (key text primary key, claim text, shown text, truth text, '
                'hand text, prompt text)')
    con.execute('create table if not exists answers (model text, key text, picks text, reason text, '
                'primary key (model, key))')
    con.execute('create table if not exists timing (model text, claims integer, seconds real, at text)')
    return con


def options(entries: dict, k: str, shown: list[str]) -> str:
    """The twelve as production shows them (motif_filing.name_claim), each motif's last three claims but this one"""
    out = []
    for n, m in enumerate(shown, 1):
        e = entries[m]
        own = [c for c in e.get('claims', []) if mi.key(c['claim']) != k][-3:]
        out.append(f'{n}. {mi.described(e)}{mi.not_this(e)}\n' + '\n'.join(f'   - {c["claim"][:160]}' for c in own))
    return '\n'.join(out)


def build(con):
    """The sample's prompts, once: every claim with a hand-made filing, then random others to SAMPLE"""
    if con.execute('select count(*) from prompts').fetchone()[0]:
        return
    data = harness.load()
    hand = {}
    for k, m in hand_added():
        if k in data['claims'] and m in data['claims'][k]['truth']:
            hand.setdefault(k, set()).add(m)
    rest = sorted(k for k in data['claims'] if k not in hand)
    rng = np.random.default_rng(SEED)
    keys = sorted(hand) + [rest[i] for i in rng.permutation(len(rest))[:max(0, SAMPLE - len(hand))]]
    rk = harness.ranks(data)  # held out: each claim ranked by a weighting learned on the others
    ids = data['ids']
    today = datetime.now().strftime('%B %-d, %Y')
    for k in keys:
        shown = [ids[i] for i in np.argsort(rk[k])[:SHOWN]]
        c = data['claims'][k]
        prompt = mf.REUSE_PROMPT.format(today=today, claim=c['claim'], options=options(data['entries'], k, shown))
        con.execute('insert into prompts values (?, ?, ?, ?, ?, ?)',
                    (k, c['claim'], json.dumps(shown), json.dumps(sorted(c['truth'])), json.dumps(sorted(hand.get(k, ()))),
                     prompt))
    con.commit()
    print(f'Paris: {len(keys)} claims, {len(hand)} with a hand-made filing', flush=True)


def ask():
    con = connect()
    build(con)
    rows = {k: (json.loads(s), p) for k, s, p in con.execute('select key, shown, prompt from prompts')}
    for model in MODELS:  # one at a time, so each loads once
        done = {k for (k,) in con.execute('select key from answers where model = ?', (model,))}
        todo = [k for k in sorted(rows) if k not in done]
        print(f'Paris: {model}, {len(done)} asked already, {len(todo)} to ask', flush=True)
        for start in range(0, len(todo), ROUND):
            part = todo[start:start + ROUND]

            def one(k, model=model):
                shown, prompt = rows[k]
                schema = {"type": "object", "properties": {
                    "reason": {"type": "string", "maxLength": 1000},
                    "fits": {"type": "array", "maxItems": 3,
                             "items": {"type": "integer", "minimum": 1, "maximum": len(shown)}}},
                    "required": ["reason", "fits"]}
                a = llm.complete_json(prompt, schema, max_tokens=900, model=model)
                if a is None:
                    return None
                picks = [shown[n - 1] for n in dict.fromkeys(a.get('fits', [])) if isinstance(n, int) and 1 <= n <= len(shown)][:3]
                return picks, a.get('reason', '')
            t = time.time()
            got = llm.parallel(one, part)
            took = time.time() - t
            n = 0
            for k, a in zip(part, got):
                if a is not None:
                    con.execute('insert or replace into answers values (?, ?, ?, ?)', (model, k, json.dumps(a[0]), a[1]))
                    n += 1
            con.execute('insert into timing values (?, ?, ?, ?)', (model, len(part), took, datetime.now().isoformat(timespec='seconds')))
            con.commit()
            print(f'Paris: {model} {min(start + ROUND, len(todo))}/{len(todo)} ({took / len(part):.1f} s a claim)', flush=True)


def measures(keys, P, S, T, H) -> np.ndarray:
    """Per claim: [found, reach, wrong, picks, none, found hand-made, reach hand-made, found model-made, reach
    model-made], to sum over any draw of claims. Hand-made filings lean against Gemma (it didn't pick them at the
    time), model-made ones towards it (it picked them and the person kept them)"""
    out = []
    for k in keys:
        p, s, t, h = set(P[k]), set(S[k]), set(T[k]), set(H[k])
        reach, hreach, mreach = t & s, h & s, (t - h) & s
        out.append([len(p & reach), len(reach), len(p - t), len(p), 0 if p else 1, len(p & hreach), len(hreach),
                    len(p & mreach), len(mreach)])
    return np.array(out, dtype=float)


def rates(m: np.ndarray) -> np.ndarray:
    """found, wrong, none, found hand-made, found model-made, from the per-claim counts"""
    s = m.sum(axis=0)
    return np.array([s[0] / max(s[1], 1), s[2] / max(s[3], 1), s[4] / max(len(m), 1), s[5] / max(s[6], 1),
                     s[7] / max(s[8], 1)])


def report():
    con = connect()
    S, T, H = {}, {}, {}
    for k, s, t, h in con.execute('select key, shown, truth, hand from prompts'):
        S[k], T[k], H[k] = json.loads(s), json.loads(t), json.loads(h)
    A = {m: {k: json.loads(p) for k, p in con.execute('select key, picks from answers where model = ?', (m,))} for m in MODELS}
    keys = sorted(k for k in S if all(k in A[m] for m in MODELS))
    sec = {m: (lambda r: r[1] / max(r[0], 1))(con.execute('select sum(claims), sum(seconds) from timing where model = ?',
                                                            (m,)).fetchone()) for m in MODELS}
    M = {m: measures(keys, A[m], S, T, H) for m in MODELS}
    hand_n, model_n = int(M[GEMMA][:, 6].sum()), int(M[GEMMA][:, 8].sum())
    harness.note(f'F28 Paris: {len(keys)} claims answered by all four ({sum(1 for k in keys if H[k])} with a hand-made '
                 f'filing); among the twelve shown, {hand_n} hand-made filings and {model_n} model-made')
    rng = np.random.default_rng(0)
    draws = [rng.integers(0, len(keys), len(keys)) for _ in range(BOOTS)]
    R = {m: rates(M[m]) for m in MODELS}
    for m in MODELS:
        f, w, nn, fh, fm = R[m]
        line = (f'F28 {m}: found {f:.1%}, wrong {w:.1%}, none {nn:.1%}, found hand-made {fh:.1%}, found model-made '
                f'{fm:.1%}, {sec[m]:.1f} s a claim')
        if m != GEMMA:
            diffs = np.array([rates(M[m][d]) - rates(M[GEMMA][d]) for d in draws])
            lo, hi = np.percentile(diffs, 2.5, axis=0), np.percentile(diffs, 97.5, axis=0)
            dd = R[m] - R[GEMMA]
            line += (f'; against Gemma: found {dd[0]:+.1%} ({lo[0]:+.1%} to {hi[0]:+.1%}), wrong {dd[1]:+.1%} '
                     f'({lo[1]:+.1%} to {hi[1]:+.1%}), hand-made {dd[3]:+.1%} ({lo[3]:+.1%} to {hi[3]:+.1%}), '
                     f'model-made {dd[4]:+.1%} ({lo[4]:+.1%} to {hi[4]:+.1%})')
            R[m] = (R[m], dd, lo, hi)
        harness.note(line)
    # The decision rule
    g = R[GEMMA]
    passing = []
    for m in MODELS[1:]:
        r, dd, lo, hi = R[m]
        fewer_wrong = dd[0] >= -0.01 and dd[1] <= -0.03 and hi[1] < 0
        more_found = dd[0] >= 0.03 and dd[1] <= 0.01 and lo[0] > 0
        if (fewer_wrong or more_found) and dd[3] >= -0.02 and dd[4] >= -0.05 and sec[m] <= 2 * sec[GEMMA]:
            passing.append(m)
    if passing:
        best = min(passing, key=lambda m: sec[m])
        verdict = f'{best} replaces Gemma for the pick, after a week\'s shadow run (passing: {", ".join(passing)})'
    else:
        fast = [m for m in MODELS[1:] if abs(R[m][1][0]) <= 0.01 and abs(R[m][1][1]) <= 0.01 and sec[m] <= sec[GEMMA] / 2]
        verdict = 'Gemma stays' + (f'; at Gemma\'s quality in half the time or less: {", ".join(fast)} (reported, not acted on)'
                                   if fast else '')
    harness.note(f'F28 decision: {verdict} (Gemma: found {g[0]:.1%}, wrong {g[1]:.1%}, {sec[GEMMA]:.1f} s a claim)')


if __name__ == '__main__':
    {'ask': ask, 'report': report}[sys.argv[1]]()
