"""F4-F6 abstracting a telling without its topic (Oct 11, the person: "Can we think of a more unique way to abstract a
telling?"). What the filing has (the shape restated with kinds for names, Matryoshka's five layers, Lethe's topic
directions subtracted) keeps the topic in generic words, which is why the Gordian Knot couldn't see two tellings inside
one motif: they share their topic's words. Three abstractions that drop the topic, asked of Gemma in one call a claim:

    Aesop       (F4) the proverb, idiom or fable the telling is an instance of: folklore's own abstraction of a situation
                (Kuusi's proverb types), and the language the index is named in ("Boy who cried wolf")
    Loki        (F5) the same story told about three unrelated subjects (a school board, a football club, a royal
                court); their embeddings averaged, the topic washes out and the shape stays
    Hermagoras  (F6) a small fixed signature from rhetoric: the stasis (fact, definition, quality, jurisdiction), Burke's
                driver (agent, scene, purpose, means, act), the time shape and the speech act

Two yardsticks, each against the plain claim:
    finding     for the person's confirmed filings, the right motif's rank when motifs are scored by the claim's likeness
                to the motif's name and its other claims (the claim left out), in each space and fused with the plain
                one: top 8/12/40 (a plain stand-in for the shortlist, not the learned one's 86.5%)
    seams       the Gordian Knot's replay: is the claim the person carved out of a motif its odd one out in this space?
                And for Hermagoras, do a motif's claims share their labels more than claims of different motifs?

Kept in f4_abstract.sqlite beside the catalog (one row a claim).

    f4_abstract_tellings.py ask       Gemma, under the GPU lease (lease 'aesop-ask')
    f4_abstract_tellings.py report    embeddings (GPU) and the two yardsticks, into the log and the catalog"""
import json
import os
import sqlite3
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f1_gordian_knot as f1  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

DB = os.path.join(harness.EXP, 'f4_abstract.sqlite')
MODEL = 'gemma4:26b'
KS = (8, 12, 40)
SUBJECTS = ('a small-town school board', 'a professional football club', 'a medieval royal court')
LABELS = {'stasis': ['fact', 'definition', 'quality', 'jurisdiction'],
          'driver': ['agent', 'scene', 'purpose', 'means', 'act'],
          'time': ['decline', 'revelation', 'prophecy', 'repetition', 'reversal', 'rise', 'none'],
          'speech': ['warning', 'accusation', 'mockery', 'lament', 'boast', 'praise', 'demand', 'report']}
PROMPT = """A claim people are telling or arguing over:
{claim}

proverb: the saying, idiom, proverb or fable this telling is an instance of, the one a folklorist would name for its \
shape, not its subject. A well-known one if any fits; if none does, coin one in the same terse style. Just the saying.
retellings: the same story told three times, one sentence each, about {subjects}. Keep everything that makes it this \
story; change everything that is only about its subject.
stasis: what the telling contends: fact (did it happen?), definition (what is it, really?), quality (was it right, \
justified, good or bad?), or jurisdiction (who should judge or act?).
driver: what it says drove what happened: agent (who they are), scene (the circumstances), purpose (what they are \
after), means (how it was done), or act (the deed itself).
time: the time shape it tells: decline, revelation (it was so all along), prophecy (it will happen), repetition (again), \
reversal (the tables turned), rise, or none.
speech: what the teller is doing: warning, accusation, mockery, lament, boast, praise, demand, or report."""
SCHEMA = {"type": "object", "properties": {
    "proverb": {"type": "string", "maxLength": 120},
    "retellings": {"type": "array", "items": {"type": "string", "maxLength": 300}, "minItems": 3, "maxItems": 3},
    **{k: {"type": "string", "enum": v} for k, v in LABELS.items()}},
    "required": ["proverb", "retellings", *LABELS]}


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute('create table if not exists asked (key text primary key, claim text, proverb text, retellings text, '
                'stasis text, driver text, time text, speech text)')
    return con


def confirmed(index: dict) -> list[tuple[str, str]]:
    """(claim, motif) for every filing the person kept in a motif they made or marked done"""
    return [(c['claim'], e['id']) for e in mi.live(index) if 'done' in e for c in e['claims'] if c.get('checked') == 'yes']


def replay() -> list[dict]:
    """The Gordian Knot's carvings: each source motif's claims as they stood, and the ones carved out"""
    out, versions = [], f1.Versions()
    for k in f1.carvings():
        e = ((versions.before(k['at']) or {}).get('entries') or {}).get(k['source'])
        if not e:
            continue
        texts = list(dict.fromkeys(c['claim'] for c in e['claims']))
        moved = [t for t in k['moved'] if t in texts]
        if len(texts) >= f1.MIN_ODD and moved:
            out.append({'source': k['source'], 'texts': texts, 'moved': moved})
    return out


def ask():
    index = mi.load()
    claims = list(dict.fromkeys([c for c, _ in confirmed(index)] + [t for r in replay() for t in r['texts']]))
    con = connect()
    have = {k for (k,) in con.execute('select key from asked')}
    todo = [c for c in claims if mi.key(c) not in have]
    print(f'ask: {len(claims)} claims, {len(todo)} to ask', flush=True)
    subjects = '; '.join(SUBJECTS)
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        got = llm.parallel(lambda c: llm.complete_json(PROMPT.format(claim=c, subjects=subjects), SCHEMA, max_tokens=500,
                                                       model=MODEL), part)
        with con:
            for c, r in zip(part, got):
                if r and r.get('proverb') and len(r.get('retellings') or []) == 3:
                    con.execute('insert or replace into asked values (?, ?, ?, ?, ?, ?, ?, ?)',
                                (mi.key(c), c, r['proverb'].strip(), json.dumps(r['retellings']),
                                 *(r.get(k) for k in LABELS)))
        print(f'ask: {min(start + 32, len(todo))}/{len(todo)}', flush=True)


class Spaces:
    """A claim in each space, unit vectors: plain (the claim), aesop (its proverb), loki (its retellings' mean)"""

    def __init__(self, rows: dict, vec):
        self.rows, self.vec, self.cache = rows, vec, {}

    def __call__(self, space: str, claims: list[str]) -> np.ndarray:
        out = []
        for c in claims:
            if (space, c) not in self.cache:
                r = self.rows.get(mi.key(c))
                if space == 'plain' or r is None:
                    v = self.vec([c])[0]
                elif space == 'aesop':
                    v = self.vec([r['proverb']])[0]
                else:
                    v = self.vec(r['retellings']).mean(0)
                self.cache[(space, c)] = v / (np.linalg.norm(v) + 1e-9)
            out.append(self.cache[(space, c)])
        return np.array(out)


def finding(index: dict, rows: dict, sp: Spaces) -> dict:
    """The right motif's rank among all, by max(likeness to its name, to its nearest other claim), in each space and
    fused (the spaces' scores summed)"""
    entries = [e for e in mi.live(index) if e['claims'] or 'done' in e]
    at = {e['id']: n for n, e in enumerate(entries)}
    claims = sorted({c['claim'] for e in entries for c in e['claims'] if mi.key(c['claim']) in rows})
    row = {c: i for i, c in enumerate(claims)}
    owner, member = zip(*[(n, row[t]) for n, e in enumerate(entries) for t in dict.fromkeys(c['claim'] for c in e['claims'])
                          if t in row])  # one line per (motif, claim) filing
    owner, member = np.array(owner), np.array(member)
    names, V = {}, {}
    for space in ('plain', 'aesop', 'loki'):  # a motif's name is an idiom already: compared with each view of the claim
        v = sp.vec([mi.described(e) for e in entries])
        names[space] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        V[space] = sp(space, claims)
    pairs = [(c, m) for c, m in confirmed(index) if m in at and c in row]
    ranks = {}
    for i, (c, m) in enumerate(pairs):
        scores = {}
        for space in ('plain', 'aesop', 'loki'):
            q = V[space][row[c]]
            s = V[space] @ q
            s[row[c]] = -1.0  # the claim left out of its motifs
            near = np.full(len(entries), -1.0)
            np.maximum.at(near, owner, s[member])
            scores[space] = np.maximum(names[space] @ q, near)
        scores['plain + aesop'] = scores['plain'] + scores['aesop']
        scores['plain + loki'] = scores['plain'] + scores['loki']
        scores['all three'] = scores['plain'] + scores['aesop'] + scores['loki']
        for arm, sc in scores.items():
            ranks.setdefault(arm, []).append(int((sc > sc[at[m]]).sum()))
        if i % 500 == 0:
            print(f'finding: {i}/{len(pairs)}', flush=True)
    return {arm: {K: round(float(np.mean(np.array(r) < K)), 3) for K in KS} for arm, r in ranks.items()} | {'n': len(pairs)}


def seams(rows: dict, sp: Spaces) -> dict:
    """The Gordian Knot's odd one out in each space; and how far Hermagoras's labels hold together within a motif"""
    cases = [r for r in replay() if all(mi.key(t) in rows for t in r['texts'])]
    out, chance = {}, []
    for space in ('plain', 'aesop', 'loki'):
        first = []
        for r in cases:
            V = sp(space, r['texts'])
            W = V @ V.T
            np.fill_diagonal(W, 0)
            order = list(np.argsort(W.sum(1)))
            for t in r['moved']:
                first.append(order.index(r['texts'].index(t)) == 0)
                if space == 'plain':
                    chance.append(1 / len(r['texts']))
        out[space] = round(float(np.mean(first)), 3) if first else None
    out['chance'] = round(float(np.mean(chance)), 3) if chance else None
    out['cases'] = sum(len(r['moved']) for r in cases)
    for label in LABELS:  # the carved claim's label differs from the rest's commonest: how often, against any claim's
        differ, base = [], []
        for r in cases:
            for t in r['moved']:
                rest = Counter(rows[mi.key(x)][label] for x in r['texts'] if x != t)
                differ.append(rows[mi.key(t)][label] != rest.most_common(1)[0][0])
            for t in r['texts']:
                rest = Counter(rows[mi.key(x)][label] for x in r['texts'] if x != t)
                base.append(rows[mi.key(t)][label] != rest.most_common(1)[0][0])
        out[f'{label} differs'] = (round(float(np.mean(differ)), 3) if differ else None, round(float(np.mean(base)), 3) if base else None)
    return out


def coherence(index: dict, rows: dict) -> dict:
    """Hermagoras: the chance two claims of one motif share a label, against two claims of different motifs"""
    import random
    rnd = random.Random(5)
    by = [[mi.key(c['claim']) for c in e['claims'] if mi.key(c['claim']) in rows] for e in mi.live(index) if 'done' in e]
    by = [ks for ks in by if len(ks) >= 2]
    flat = [(n, k) for n, ks in enumerate(by) for k in ks]
    out = {}
    for label in LABELS:
        within = [rows[a][label] == rows[b][label] for ks in by for i, a in enumerate(ks) for b in ks[i + 1:]]
        between = []
        while len(between) < 5000:
            (na, a), (nb, b) = rnd.sample(flat, 2)
            if na != nb:
                between.append(rows[a][label] == rows[b][label])
        out[label] = (round(float(np.mean(within)), 3), round(float(np.mean(between)), 3))
    return out


def report():
    index = mi.load()
    con = connect()
    rows = {k: {'claim': c, 'proverb': p, 'retellings': json.loads(r), 'stasis': s, 'driver': d, 'time': t, 'speech': sp}
            for k, c, p, r, s, d, t, sp in con.execute('select * from asked')}
    vec = mr.Vectors()
    vec([r['claim'] for r in rows.values()] + [r['proverb'] for r in rows.values()]
        + [t for r in rows.values() for t in r['retellings']])  # every text embedded in one go, then looked up
    sp = Spaces(rows, vec)
    found = finding(index, rows, sp)
    seam = seams(rows, sp)
    held = coherence(index, rows)
    json.dump({'finding': found, 'seams': seam, 'coherence': held}, open(DB.replace('.sqlite', '.json'), 'w'))
    top = lambda arm: f"{found[arm][8]:.0%}/{found[arm][12]:.0%}/{found[arm][40]:.0%}"  # noqa: E731
    lines = [
        f"F4 Aesop and F5 Loki, finding: right motif in the top 8/12/40 of {found['n']} confirmed filings by plain likeness: "
        + '; '.join(f'{arm} {top(arm)}' for arm in found if arm != 'n'),
        f"F4 Aesop and F5 Loki, seams: the carved claim its motif's odd one out ({seam['cases']} carved claims; chance "
        f"{seam['chance']:.0%}): plain {seam['plain']:.0%}, Aesop {seam['aesop']:.0%}, Loki {seam['loki']:.0%}",
        "F6 Hermagoras: two claims of one motif share the label, against two of different motifs: "
        + '; '.join(f'{k} {w:.0%} against {b:.0%}' for k, (w, b) in held.items())
        + '; the carved claim unlike its motif: '
        + '; '.join(f"{k} {seam[f'{k} differs'][0]:.0%} against {seam[f'{k} differs'][1]:.0%} for any claim" for k in LABELS)]
    for line in lines:
        print(line, flush=True)
        harness.note(line)


def main():
    {'ask': ask, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
