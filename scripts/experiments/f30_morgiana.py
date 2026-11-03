"""F30 Morgiana: the hand-kept carrying words, for the shortlist to catch claims by (Nov 2). Ali Baba (F27, Oct 22)
tested the phrase dictionary's machine half, log-odds over the tellings, and it added 0.1 point. This tests the other
half agreed on Oct 12: the carrying words a reader marked on each filing in the checker (1,381 filings over 605 motifs
on Nov 2). Morgiana is the servant in Ali Baba's tale who reads the chalk mark on the door.

A claim's text is its sentence plus what it came from: a show claim's quote (show_claim, by its episode and wording),
else the sources Tiresias gathered (f26_tiresias.sqlite). A motif's phrases are its filings' carrying words cut into
runs of two to four words (not all common words, not starting or ending on one). A claim never counts its own filings'
words, nor those of filings told in the same episode or from the same source (its twins). No model, no GPU in report.

    signals        phrase hits (how many of the motif's runs the claim's text has) and phrase weight (each run weighted
                   by the share of the motif's carried filings that use it, summed, log-scaled)
    arms           told (names kept: a motif is its pattern and the content that moves it), told without names, claim
                   only, and Ali Baba's dictionary on the same claims for the hand-versus-machine comparison

The paper is ~/maudlin-data/papers/morgiana.md (hypotheses and the decision rule written before the run).

    f30_morgiana.py build     the filing harness again on today's index, into its own cache (signals-morgiana.pkl):
                              the one of Oct 20 predates nearly every carrying word. Embeds the new claims
    f30_morgiana.py report    the dictionary, every arm through the harness, recall on the carried motifs' filings with
                              a paired interval, by genre, the hard misses, the decision; all kept in f30_morgiana.sqlite
    f30_morgiana.py peek      the dictionary alone: its size and the biggest motifs' runs"""
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f27_ali_baba as ab  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

CACHE = os.path.join(harness.EXP, 'signals-morgiana.pkl')
DB = os.path.join(harness.EXP, 'f30_morgiana.sqlite')
DATA_DB = os.path.join(Config.data, 'data.db')
RUNS = (2, 3, 4)
K = 12
BOOTS = 1000
SPEAKER = re.compile(r"^\s*[^'\"“‘:]{1,80}?\([^)]*\)\s*:\s*")  # "Solomon (War Room): ..."
BREAKS = re.compile(r"\.\.\.|…|[\"“”]|[.!?;]\s")


def runs(text: str, named: set[str] | None = None) -> set[str]:
    """The two- to four-word runs of a text that aren't common words throughout, nor start or end on one"""
    out = set()
    for part in BREAKS.split(SPEAKER.sub('', text or '')):
        words = [w.lower() for w in ab.WORD.findall(part)]
        for n in RUNS:
            for i in range(len(words) - n + 1):
                g = words[i:i + n]
                if g[0] in ab.STOP or g[-1] in ab.STOP or all(w in ab.STOP for w in g):
                    continue
                if named and any(w in named for w in g):
                    continue
                out.add(' '.join(g))
    return out


def told_texts(data: dict) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """{claim key: sentence}, {claim key: sentence plus what it came from}, {claim key: its source group (episode,
    url or source name)}; reworded claims are found under their old wording too"""
    claim, group = {}, {}
    for e in data['entries'].values():
        for c in e.get('claims', []):
            k = mi.key(c['claim'])
            claim.setdefault(k, c['claim'])
            group.setdefault(k, c.get('ref') or c.get('source') or k)
    for k, c in data['claims'].items():
        claim.setdefault(k, c['claim'])
        group.setdefault(k, k)
    old = defaultdict(list)  # new wording's key -> the wordings it was corrected from
    for was, now in (mi.load().get('corrections') or {}).items():
        old[mi.key(now)].append(was)
    quotes = defaultdict(list)
    con = sqlite3.connect(f'file:{DATA_DB}?mode=ro', uri=True)
    for url, text, quote in con.execute('select url, claim, quote from show_claim where quote is not null'):
        quotes[(url, mi.key(text))].append(quote)
    con.close()
    src = {}
    if os.path.exists(ab.SOURCES):
        s = sqlite3.connect(ab.SOURCES)
        src = {k: v or '' for k, v in s.execute("select key, sources from points where arm = 'sources'")}
        s.close()
    told = {}
    for k, text in claim.items():
        qs = []
        for w in [text] + old.get(k, []):
            qs += quotes.get((group[k], mi.key(w)), [])
        told[k] = text + '\n' + ('\n'.join(dict.fromkeys(qs)) if qs else ab.HEADINGS.sub('\n', src.get(k, '')))
    return claim, told, group


def carried(data: dict) -> dict[str, list[tuple[str, str, set[str]]]]:
    """motif -> [(claim key, its source group, the runs of its carrying words)] for each filing with carrying words"""
    out = defaultdict(list)
    for m, e in data['entries'].items():
        for c in e.get('claims', []):
            words = c.get('carrying') or []
            if isinstance(words, str):
                words = [words]
            rs = set().union(*(runs(p) for w in words for p in w.split(';'))) if words else set()
            if rs:
                out[m].append((mi.key(c['claim']), c.get('ref') or c.get('source') or '', rs))
    return out


def signals(data: dict, dictionary: dict, sets: dict[str, set[str]], group: dict[str, str], arm: str) -> dict:
    """The arm's two signals as the harness takes them: {name: (data, claim key) -> a score per motif}"""
    ids, col = data['ids'], data['at']
    by_run = defaultdict(list)  # run -> [(motif column, claim key, group)]
    size = {}
    for m, filings in dictionary.items():
        if m not in col:
            continue
        size[col[m]] = filings
        for k, g, rs in filings:
            for r in rs:
                by_run[r].append((col[m], k, g))
    memo = {}
    for k in data['claims']:
        mine = group.get(k, k)
        hits, weight = np.zeros(len(ids)), np.zeros(len(ids))
        users = defaultdict(lambda: defaultdict(set))  # motif column -> run -> the filings using it, not its twins
        for r in sets.get(k, ()):
            for j, ck, g in by_run.get(r, ()):
                if ck != k and g != mine:
                    users[j][r].add(ck)
        for j, rs in users.items():
            others = sum(1 for ck, g, _ in size[j] if ck != k and g != mine)
            if others:
                hits[j] = len(rs)
                weight[j] = sum(len(u) for u in rs.values()) / others
        memo[k] = (hits, np.log1p(weight))
    zero = np.zeros(len(ids))
    return {f'{arm} phrase hits': lambda dd, k: memo[k][0] if k in memo else zero,
            f'{arm} phrase weight': lambda dd, k: memo[k][1] if k in memo else zero}


def carried_pairs(data: dict, dictionary: dict, group: dict[str, str]) -> list[tuple[str, str]]:
    """The person's confirmed filings whose motif has carrying words from some other filing, not the claim's twins"""
    out = []
    for k, c in data['claims'].items():
        for m in c['truth']:
            if any(ck != k and g != group.get(k, k) for ck, g, _ in dictionary.get(m, ())):
                out.append((k, m))
    return out


def recall(data: dict, ranks: dict, pairs: list[tuple[str, str]]) -> np.ndarray:
    at = data['at']
    return np.array([ranks[k][at[m]] < K for k, m in pairs], dtype=float)


def paired(data: dict, base: dict, new: dict, pairs: list[tuple[str, str]]) -> tuple[float, float, float]:
    """Top-12 gain on these filings, with a 95% bootstrap interval over claims (a claim's filings drawn together)"""
    b, n = recall(data, base, pairs), recall(data, new, pairs)
    by_claim = defaultdict(list)
    for i, (k, _) in enumerate(pairs):
        by_claim[k].append(i)
    claims = list(by_claim)
    rng = np.random.default_rng(30)
    gains = []
    for _ in range(BOOTS):
        idx = [i for c in rng.choice(len(claims), len(claims)) for i in by_claim[claims[c]]]
        gains.append(n[idx].mean() - b[idx].mean())
    return float(n.mean() - b.mean()), float(np.percentile(gains, 2.5)), float(np.percentile(gains, 97.5))


def by_genre(data: dict, base: dict, new: dict, pairs: list[tuple[str, str]]) -> dict:
    out = {}
    for label, test in (('moves', ab.MOVES), ('stories', ab.STORIES)):
        sub = [(k, m) for k, m in pairs if (data['entries'][m].get('facets') or {}).get('genre') in test]
        if sub:
            out[label] = (len(sub), float(recall(data, base, sub).mean()), float(recall(data, new, sub).mean()))
    return out


def keep(rows: list[tuple], dictionary: dict, data: dict):
    con = sqlite3.connect(DB)
    con.execute('drop table if exists results')
    con.execute('create table results (arm text, measure text, value real, note text)')
    con.executemany('insert into results values (?, ?, ?, ?)', rows)
    con.execute('drop table if exists phrases')
    con.execute('create table phrases (motif text, name text, claim text, grp text, runs text)')
    con.executemany('insert into phrases values (?, ?, ?, ?, ?)',
                    [(m, data['entries'].get(m, {}).get('name', m), k, g, json.dumps(sorted(rs)))
                     for m, fs in dictionary.items() for k, g, rs in fs])
    con.commit()
    con.close()


def build():
    harness.build(CACHE)


def report():
    data = harness.load(CACHE)
    claim, told, group = told_texts(data)
    dictionary = carried(data)
    pairs = carried_pairs(data, dictionary, group)
    quoted = sum(1 for k in data['claims'] if told[k].strip() != claim[k].strip())
    harness.note(f'F30 Morgiana: {len(data["claims"])} claims, {quoted} with what they came from; carrying words on '
                 f'{sum(len(v) for v in dictionary.values())} filings of {len(dictionary)} motifs; '
                 f'{len(pairs)} confirmed filings in a motif with others\' carrying words')
    named = ab.names(told)
    sets = {'told': {k: runs(t) for k, t in told.items()},
            'told, names out': {k: runs(t, named) for k, t in told.items()},
            'claim only': {k: runs(t) for k, t in claim.items()}}
    base = harness.ranks(data)
    rows, news = [], {}
    for arm, s in sets.items():
        extra = signals(data, dictionary, s, group, arm)
        out = harness.evaluate(data, extra=extra, label=f'F30 Morgiana, {arm}')
        new = news[arm] = harness.ranks(data, extra)
        g, lo, hi = paired(data, base, new, pairs)
        harness.note(f'F30 {arm}, carried motifs\' filings: top-12 {recall(data, base, pairs).mean():.1%} -> '
                     f'{recall(data, new, pairs).mean():.1%} ({g:+.1%}, {lo:+.1%} to {hi:+.1%})')
        rows += [(arm, 'all top12 base', out['base'][12], ''), (arm, 'all top12 with', out['with'][12], ''),
                 (arm, 'carried gain', g, ''), (arm, 'carried gain low', lo, ''), (arm, 'carried gain high', hi, ''),
                 (arm, 'hard misses before', out['misses before'], ''), (arm, 'brought back', out['brought back'], ''),
                 (arm, 'newly missed', out['newly missed'], '')]
        for label, (n, b, w) in by_genre(data, base, new, pairs).items():
            harness.note(f'F30 {arm}, {label}: {n} filings, top-12 {b:.1%} -> {w:.1%} ({w - b:+.1%})')
            rows.append((arm, f'{label} gain', w - b, f'{n} filings'))
        harness.note(f"F30 {arm}: hard misses brought back {out['brought back']} of {out['misses before']}, "
                     f"{out['newly missed']} new")
    # Ali Baba's dictionary on the same claims and texts, for hand against machine
    members = {m: [mi.key(c['claim']) for c in e.get('claims', []) if mi.key(c['claim']) in told]
               for m, e in data['entries'].items()}
    members = {m: ks for m, ks in members.items() if len(ks) >= ab.MIN_CLAIMS}
    ab_sets = {k: ab.phrases(t, named) for k, t in told.items()}
    ab_new = harness.ranks(data, ab.signals(data, ab.Dictionary(ab_sets, members), ab_sets, 'ali baba'))
    g_ab, _, _ = paired(data, base, ab_new, pairs)
    g_told = paired(data, base, news['told'], pairs)[0]
    harness.note(f'F30 Ali Baba on the same claims, carried motifs\' filings: top-12 {g_ab:+.1%}; Morgiana told '
                 f'{g_told:+.1%}')
    rows.append(('ali baba', 'carried gain', g_ab, 'same claims and texts'))
    # The decision rule, from the paper
    g, lo, _ = paired(data, base, news['told'], pairs)
    moves = by_genre(data, base, news['told'], pairs).get('moves', (0, 0.0, 0.0))
    stories = by_genre(data, base, news['told'], pairs).get('stories', (0, 0.0, 0.0))
    held = {1: g >= 0.01 and lo > 0, 2: moves[2] - moves[1] >= 0.02 and stories[2] - stories[1] >= -0.005,
            4: g_told - g_ab >= 0.01}
    verdict = ('production: the carrying words as two signals in the learned shortlist' if held[1] and
               moves[2] - moves[1] >= 0.02 else 'not kept: the carrying words stay a reading aid and flow tracker')
    harness.note(f'F30 decision: {verdict} (H1 {held[1]}, H2 {held[2]}, H4 {held[4]}; told {g:+.1%} from {lo:+.1%}, '
                 f'moves {moves[2] - moves[1]:+.1%})')
    rows.append(('told', 'decision', float(held[1]), verdict))
    keep(rows, dictionary, data)
    at = data['at']
    for k, m in pairs:
        if base[k][at[m]] >= 40 > news['told'][k][at[m]]:
            print(f"  back: {data['claims'][k]['claim'][:100]} -> {data['entries'][m]['name']} "
                  f"({base[k][at[m]]} -> {news['told'][k][at[m]]})")


def peek():
    data = harness.load(CACHE) if os.path.exists(CACHE) else harness.load()
    dictionary = carried(data)
    print(sum(len(v) for v in dictionary.values()), 'carried filings in', len(dictionary), 'motifs (of the cache\'s)')
    for m in sorted(dictionary, key=lambda m: -len(dictionary[m]))[:int(sys.argv[2]) if len(sys.argv) > 2 else 12]:
        rs = sorted({r for _, _, s in dictionary[m] for r in s}, key=len)[:10]
        print(f"  {data['entries'][m]['name']} ({len(dictionary[m])}): " + ', '.join(rs))


if __name__ == '__main__':
    {'build': build, 'report': report, 'peek': peek}[sys.argv[1]]()
