"""F27 Ali Baba: the tellers' own words for each motif, for the shortlist to catch claims by (Oct 22). Tiresias (a
sentence on a claim's point) and Indra's Net (versions of each motif) both wrote more generic text and gained 0.3
point; this tests the exact words instead. The cave opens to "open sesame" and to no others.

The phrase dictionary agreed on Oct 12, its machine half: for each motif, the one- to three-word phrases its claims'
tellings use more than the other claims do, by weighted log-odds with an informative Dirichlet prior (Monroe, Colaresi
and Quinn 2008), names left out. A claim's text is its sentence plus what it came from, as Tiresias gathered it from the
checker's claim detail (f26_tiresias.sqlite). No model, no GPU.

    signals        phrase hits (how many of the motif's phrases the claim's text uses) and phrase weight (their
                   z-scores summed, log-scaled), each arm two more signals in the learned weighting; a claim is scored
                   against its own motifs with them counted without it

The paper is ~/maudlin-data/papers/ali-baba.md (hypotheses and the decision rule written before the run).

    f27_ali_baba.py report    build the dictionary, the harness without and with each arm, by genre, the hard misses,
                              the dictionary saved and its biggest motifs' phrases printed, the decision"""
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402

DB = os.path.join(harness.EXP, 'f27_ali_baba.sqlite')
SOURCES = os.path.join(harness.EXP, 'f26_tiresias.sqlite')
PRIOR = 500.0  # the Dirichlet prior's total weight, spread by each phrase's share of all claims
Z = 1.96
TOP = 40
MIN_CLAIMS = 2
MOVES = {'Arguments', 'Values', 'Exhortations'}
STORIES = {'Plots', 'Theories'}
# The headings Tiresias' sources_of() wrote between the parts: not the tellers' words
HEADINGS = re.compile(r"Posts telling it:|The fact-check it came from \([^)]*\):|Told on the shows:|Said in a focus group:|"
                      r"Around it:|What it came from:")
STOP = set("""a about above after again against all am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further had has have having he her here hers
herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once
only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we were what when where which while who whom
why will with would you your yours yourself yourselves also said says say get got one two new like s t re ve ll d m
don doesn didn isn aren wasn weren won wouldn couldn shouldn can't don't it's i'm that's he's she's they're we're
you're there's let's""".split())  # noqa: SIM905 - a paragraph of words reads better than 200 quoted ones
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE = re.compile(r"[.!?\n;:]+|\s[-–—]\s")


def texts() -> tuple[dict[str, str], dict[str, str]]:
    """Every harness claim's sentence and its told text (sentence plus sources): two {claim key: text}"""
    data = harness.load()
    claim = {k: c['claim'] for k, c in data['claims'].items()}
    for e in data['entries'].values():
        for c in e.get('claims', []):
            claim.setdefault(mi.key(c['claim']), c['claim'])
    src = {}
    if os.path.exists(SOURCES):
        con = sqlite3.connect(SOURCES)
        src = {k: s or '' for k, s in con.execute("select key, sources from points where arm = 'sources'")}
    told = {k: t + '\n' + HEADINGS.sub('\n', src.get(k, '')) for k, t in claim.items()}
    return claim, told


def names(corpus: dict[str, str]) -> set[str]:
    """Words written with a capital in most of their uses away from a sentence's start: names"""
    cap, seen = Counter(), Counter()
    for t in corpus.values():
        for sent in SENTENCE.split(re.sub(r'https?://\S+', ' ', t)):
            for i, w in enumerate(WORD.findall(sent)):
                if i == 0:
                    continue
                lw = w.lower()
                seen[lw] += 1
                if w[0].isupper():
                    cap[lw] += 1
    return {w for w, n in seen.items() if cap[w] > n / 2}


def phrases(text: str, named: set[str]) -> set[str]:
    """The one- to three-word phrases a text uses, once each, not across a sentence end; none of only common words,
    none holding a name"""
    out = set()
    for sent in SENTENCE.split(re.sub(r'https?://\S+', ' ', text)):
        ws = [w.lower() for w in WORD.findall(sent)]
        for n in (1, 2, 3):
            for i in range(len(ws) - n + 1):
                g = ws[i:i + n]
                if all(w in STOP for w in g) or any(w in named for w in g) or g[0] in STOP or g[-1] in STOP:
                    continue
                out.add(' '.join(g))
    return out


class Dictionary:
    """The weighted log-odds of every phrase in each motif against all the other claims, with the motif's members
    left out one at a time on request"""

    def __init__(self, sets: dict[str, set[str]], members: dict[str, list[str]]):
        self.sets, self.members = sets, members
        self.df = Counter(p for s in sets.values() for p in s)  # claims using each phrase
        self.total = sum(self.df.values())
        self.mdf = {m: Counter(p for k in ks for p in sets[k]) for m, ks in members.items()}
        self.mtot = {m: sum(c.values()) for m, c in self.mdf.items()}
        self.full = {m: self.top(m) for m in members}

    def top(self, m: str, without: str | None = None) -> list[tuple[str, float, int]]:
        """The motif's phrases, best first: (phrase, z, claims using it), without one of its claims if asked"""
        mine, ym_total = self.mdf[m], self.mtot[m]
        out_set = self.sets.get(without, set()) if without else set()
        total, df = self.total, self.df
        if without:
            ym_total -= len(out_set)
            total -= len(out_set)
        rest_total = total - ym_total
        res = []
        for p, ym in mine.items():
            gone = 1 if p in out_set else 0
            ym -= gone
            if ym < MIN_CLAIMS:
                continue
            g = df[p] - gone
            a = PRIOR * g / total
            yr = g - ym
            delta = (math.log((ym + a) / (ym_total + PRIOR - ym - a))
                     - math.log((yr + a) / (rest_total + PRIOR - yr - a)))
            z = delta / math.sqrt(1 / (ym + a) + 1 / (yr + a))
            if z > Z:
                res.append((p, z, ym))
        res.sort(key=lambda x: -x[1])
        return res[:TOP]


def signals(data: dict, d: Dictionary, sets: dict[str, set[str]], arm: str) -> dict:
    """The arm's two signals as the harness takes them: {name: (data, claim key) -> a score per motif}"""
    ids = data['ids']
    col = {m: j for j, m in enumerate(ids)}
    index = defaultdict(list)  # phrase -> [(motif column, z)], from the full dictionary
    for m, ps in d.full.items():
        if m in col:
            for p, z, _ in ps:
                index[p].append((col[m], z))
    own = defaultdict(list)  # claim -> its motifs (scored without it)
    for m, ks in d.members.items():
        for k in ks:
            own[k].append(m)
    memo = {}
    for k in data['claims']:
        hits, weight = np.zeros(len(ids)), np.zeros(len(ids))
        s = sets.get(k, set())
        mine = {col[m] for m in own[k] if m in col}
        for p in s:
            for j, z in index.get(p, ()):
                if j not in mine:
                    hits[j] += 1
                    weight[j] += z
        for m in own[k]:  # its own motifs, with their phrases counted without it
            if m not in col:
                continue
            j = col[m]
            hits[j] = weight[j] = 0
            for p, z, _ in d.top(m, without=k):
                if p in s:
                    hits[j] += 1
                    weight[j] += z
        memo[k] = (hits, np.log1p(weight))
    zero = np.zeros(len(ids))
    return {f'{arm} phrase hits': lambda dd, k: memo[k][0] if k in memo else zero,
            f'{arm} phrase weight': lambda dd, k: memo[k][1] if k in memo else zero}


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


def save(d: Dictionary, data: dict):
    con = sqlite3.connect(DB)
    con.execute('drop table if exists phrases')
    con.execute('create table phrases (motif text, name text, phrase text, z real, claims integer)')
    con.executemany('insert into phrases values (?, ?, ?, ?, ?)',
                    [(m, data['entries'].get(m, {}).get('name', m), p, round(z, 2), n)
                     for m, ps in d.full.items() for p, z, n in ps])
    con.commit()
    con.close()


def report():
    data = harness.load()
    claim, told = texts()
    named = names(told)
    members = {m: [mi.key(c['claim']) for c in e.get('claims', []) if mi.key(c['claim']) in told]
               for m, e in data['entries'].items()}
    members = {m: ks for m, ks in members.items() if len(ks) >= MIN_CLAIMS}
    told_sets = {k: phrases(t, named) for k, t in told.items()}
    claim_sets = {k: phrases(t, named) for k, t in claim.items()}
    d = Dictionary(told_sets, members)
    have = sum(1 for ps in d.full.values() if ps)
    harness.note(f'F27 Ali Baba: {len(told)} claims, {len(named)} words taken as names, {len(d.df)} phrases; '
                 f'{have} of {len(members)} motifs with 2+ claims have phrases '
                 f'(median {int(np.median([len(ps) for ps in d.full.values()]))})')
    save(d, data)
    for m in sorted(members, key=lambda m: -len(members[m]))[:20]:
        ps = d.full[m]
        print(f"  {data['entries'][m]['name']} ({len(members[m])} claims): " + ', '.join(p for p, _, _ in ps[:12]))

    base = harness.ranks(data)
    results = {}
    for arm, sets in (('told', told_sets), ('claim only', claim_sets)):
        extra = signals(data, d, sets, arm)
        out = harness.evaluate(data, extra=extra, label=f'F27 Ali Baba, {arm}')
        new = harness.ranks(data, extra)
        results[arm] = (out, new)
        for label, (n, b, w) in by_genre(data, base, new).items():
            harness.note(f'F27 {arm}, {label}: {n} filings, top-12 {b:.1%} -> {w:.1%} ({w - b:+.1%})')
        back = out['brought back'] / max(1, out['misses before'])
        harness.note(f"F27 {arm}: hard misses (outside the top 40) brought back {out['brought back']} of "
                     f"{out['misses before']} ({back:.0%}), {out['newly missed']} new")
    at = data['at']
    new = results['told'][1]
    for k, c in data['claims'].items():
        for m in c['truth']:
            if base[k][at[m]] >= 40 and new[k][at[m]] < 40:
                print(f"  back: {c['claim'][:110]} -> {data['entries'][m]['name']} ({base[k][at[m]]} -> {new[k][at[m]]})")
    # The decision rule
    t_out = results['told'][0]
    gain = t_out['with'][12] - t_out['base'][12]
    low = t_out.get('gain interval', {}).get(12, (0, 0))[0]
    moves = by_genre(data, base, results['told'][1]).get('moves (Arguments, Values, Exhortations)', (0, 0, 0))
    c_gain = results['claim only'][0]['with'][12] - results['claim only'][0]['base'][12]
    if gain >= 0.01 and low > 0 and moves[2] - moves[1] >= 0.02:
        verdict = f'in production (top-12 {gain:+.1%}, moves {moves[2] - moves[1]:+.1%}; claim only {c_gain:+.1%})'
    else:
        verdict = (f'not kept: told top-12 {gain:+.1%} (interval from {low:+.1%}), moves {moves[2] - moves[1]:+.1%}; '
                   f'claim only top-12 {c_gain:+.1%}')
    harness.note(f'F27 decision: {verdict}')


def peek():
    """The dictionary alone, no evaluation: a quick look before the run (biggest motifs' phrases)"""
    data = harness.load()
    claim, told = texts()
    named = names(told)
    members = {m: [mi.key(c['claim']) for c in e.get('claims', []) if mi.key(c['claim']) in told]
               for m, e in data['entries'].items()}
    members = {m: ks for m, ks in members.items() if len(ks) >= MIN_CLAIMS}
    d = Dictionary({k: phrases(t, named) for k, t in told.items()}, members)
    print(len(named), 'names;', len(d.df), 'phrases')
    for m in sorted(members, key=lambda m: -len(members[m]))[:int(sys.argv[2]) if len(sys.argv) > 2 else 15]:
        print(f"  {data['entries'][m]['name']} ({len(members[m])}): " + ', '.join(p for p, _, _ in d.full[m][:12]))


if __name__ == '__main__':
    {'report': report, 'peek': peek}[sys.argv[1]]()
