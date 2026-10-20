"""F25 Indra's Net: each motif mirrored in many versions, for the shortlist to catch claims by (Oct 20; the person:
"experiment with a model generating and caching variations on the motifs for seeding a better spiderweb match
technique for surfacing the short list"). In Indra's net every jewel reflects all the others; here each motif is
written out twenty times over, in other casts, settings and voices, and a claim is compared with every reflection.

Scheherazade's shortlist misses matched the cast, not the plot (a fox tale to another fox tale); a motif's real claims
share one cast, and a small motif or a seed has little to be found by. The versions widen the motif, not the claim
(Loki and Aesop rewrote the claim, and lost).

    versions       Gemma 4 26B, from a motif's name and note only (never its claims: no claim leaks into its own
                   test), 20 one-sentence claims telling it; for each ATU tale type with tales in Scheherazade's set,
                   from its name and description, 20 one-sentence tale summaries; cached by the text they came from
    signals        the claim's best likeness (mxbai) to a motif's versions, and the mean of its best three

The paper is ~/maudlin-data/papers/indras-net.md (hypotheses and the decision rule written before the run).

    f25_indras_net.py weave     under the GPU lease: the harness rebuilt, then the versions; resumes from what it saved
    f25_indras_net.py report    the harness with and without the signals, by motif size; the folktales; the decision"""
import hashlib
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.utils import Config  # noqa: E402

DB = os.path.join(harness.EXP, 'f25_indras_net.sqlite')
MODEL = 'gemma4:26b'
N = 20  # versions a motif
BATCH = 8  # motifs asked, then saved
SMALL, LARGE = 5, 20  # claims: a small motif at most, a large one at least (hypothesis 2)
OURS = """A motif: a recurring story or argument people tell about public life.
Name: {name}
What it is: {note}

Write {n} different one-sentence claims that each tell this motif, the way a person would state them as true. Keep the \
motif's shape in every one, but change everything else: spread them over national and local politics, business, \
sports, celebrity, foreign affairs, religion, science and the internet; use different casts (named and unnamed people, \
groups, institutions); and different voices (a believer, a critic, a joker). Don't repeat the motif's name or its \
words."""
TALES = """A folktale type from the ATU index.
Name: {name}
What happens: {note}

Write {n} different one-sentence summaries of tales of this type, as a folklorist would sum up a tale they collected. \
Keep the type's plot in every one, but change the cast and setting: animals, ordinary people, kings, tricksters, \
spirits, from many cultures. Don't repeat the type's name or its words."""
SCHEMA = {"type": "object", "properties": {"versions": {"type": "array", "items": {"type": "string", "maxLength": 300},
                                                         "minItems": N, "maxItems": N}}, "required": ["versions"]}


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute('create table if not exists versions (space text, id text, source text, i integer, text text, '
                'primary key (space, id, i))')
    return con


def sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def ours(data: dict) -> dict[str, str]:
    """Motif id -> the text its versions come from (name and note; the name alone where there's no note)"""
    return {m: f"{e['name']}\n{(e.get('note') or '').strip()}" for m, e in data['entries'].items()}


def tales() -> tuple[list[dict], dict[str, str]]:
    """Scheherazade's one-sentence tale claims ({claim, type}) for the types with two tales or more, and those types'
    texts (type id -> name and description)"""
    import pandas as pd
    import lab
    saved = lab._load('a1_folktales.json')
    folder = os.path.join(Config.data, 'archives', 'trilogy')
    t = pd.read_csv(os.path.join(folder, 'aft.csv')).dropna(subset=['text', 'atu_id']).reset_index(drop=True)
    t['atu_id'] = t['atu_id'].astype(str)
    counts = t['atu_id'].value_counts()
    said = saved['claims']['one sentence']
    claims = [{'claim': c, 'type': t['atu_id'][int(i)]} for i, c in said.items() if c and counts[t['atu_id'][int(i)]] >= 2]
    atu = pd.read_csv(os.path.join(folder, 'atu_df.csv'))
    keep = {c['type'] for c in claims}
    types = {str(r.atu_id): f"{r.tale_name}\n{r.tale_type if isinstance(r.tale_type, str) else ''}"
             for r in atu.itertuples() if str(r.atu_id) in keep}
    return [c for c in claims if c['type'] in types], types


def weave_space(con, space: str, texts: dict[str, str], prompt: str):
    have = {(i, s) for i, s in con.execute('select id, source from versions where space = ? and i = ?', (space, N - 1))}
    todo = [(m, t) for m, t in texts.items() if (m, sha(t)) not in have]
    print(f'{space}: {len(texts) - len(todo)} of {len(texts)} woven; weaving {len(todo)}', flush=True)
    for n in range(0, len(todo), BATCH):
        part = todo[n:n + BATCH]

        def ask(item):
            name, _, note = item[1].partition('\n')
            return llm.complete_json(prompt.format(name=name, note=note or '(none given)', n=N), SCHEMA,
                                     max_tokens=4000, model=MODEL)
        for (m, t), a in zip(part, llm.parallel(ask, part)):
            vs = [' '.join(v.split()) for v in (a or {}).get('versions', []) if isinstance(v, str) and v.strip()]
            if len(vs) < N:
                continue  # asked again next time
            con.execute('delete from versions where space = ? and id = ?', (space, m))
            con.executemany('insert into versions values (?, ?, ?, ?, ?)',
                            [(space, m, sha(t), i, v) for i, v in enumerate(vs[:N])])
        con.commit()
        print(f'{space}: woven {min(n + BATCH, len(todo))}/{len(todo)}', flush=True)


def weave():
    data = harness.load(rebuild=True)  # the index and the person's decisions as they stand now
    print(f"harness: {len(data['claims'])} claims, {len(data['ids'])} motifs", flush=True)
    con = connect()
    weave_space(con, 'ours', ours(data), OURS)
    weave_space(con, 'tales', tales()[1], TALES)


def versions(con, space: str, ids: list[str], vec) -> dict[str, np.ndarray]:
    """Each id's versions, embedded (unit vectors)"""
    rows = {}
    for m, v in con.execute('select id, text from versions where space = ? order by id, i', (space,)):
        rows.setdefault(m, []).append(v)
    out = {}
    for m in ids:
        if m in rows:
            out[m] = vec(rows[m])
    return out


def scores(q: np.ndarray, V: dict, ids: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """For one claim's unit vector: (best likeness, mean of the best three) to each id's versions; 0 for none"""
    best, top3 = np.zeros(len(ids)), np.zeros(len(ids))
    for j, m in enumerate(ids):
        if m in V:
            s = np.sort(V[m] @ q)[::-1]
            best[j], top3[j] = s[0], s[:3].mean()
    return best, top3


def report():
    con = connect()
    vec = mr.Vectors()
    data = harness.load()
    ids = data['ids']
    V = versions(con, 'ours', ids, vec)
    keys = sorted(data['claims'])
    Q = dict(zip(keys, vec([data['claims'][k]['claim'] for k in keys])))
    memo = {k: scores(Q[k], V, ids) for k in keys}
    harness.note(f"F25 Indra's Net: {len(V)} of {len(ids)} motifs woven ({N} versions each); {len(keys)} claims, "
                 f"{sum(len(data['claims'][k]['truth']) for k in keys)} confirmed filings")
    extra = {'indra best': lambda d, k: memo[k][0], 'indra top3': lambda d, k: memo[k][1]}
    out = harness.evaluate(data, extra=extra, label="F25 Indra's Net, our shortlist")
    # by motif size (hypothesis 2): top-12 recall of the filings in small and large motifs, without and with
    base, new = harness.ranks(data), harness.ranks(data, extra)
    at = data['at']
    for label, test in ((f'motifs of {SMALL} claims or fewer', lambda n: n <= SMALL),
                        (f'motifs of {LARGE} claims or more', lambda n: n >= LARGE)):
        pairs = [(k, m) for k in keys for m in data['claims'][k]['truth'] if test(len(data['entries'][m]['claims']))]
        if pairs:
            b = np.mean([base[k][at[m]] < 12 for k, m in pairs])
            w = np.mean([new[k][at[m]] < 12 for k, m in pairs])
            harness.note(f"F25 {label}: {len(pairs)} filings, top-12 {b:.1%} -> {w:.1%} ({w - b:+.1%})")
    # not generic (hypothesis 5): the own motif's best likeness against the others' 90th percentile
    above = [memo[k][0][at[m]] > np.percentile(np.delete(memo[k][0], at[m]), 90)
             for k in keys for m in data['claims'][k]['truth'] if m in V]
    harness.note(f"F25 own motif's versions above the others' 90th percentile: {np.mean(above):.0%} of {len(above)}")
    back = out['brought back'] / max(1, out['misses before'])
    harness.note(f"F25 hard misses (outside the top 40) brought back: {out['brought back']} of {out['misses before']} "
                 f"({back:.0%})")
    folktales(con, vec)
    gain = out['with'][12] - out['base'][12]
    low = out['gain interval'][12][0]
    large = [(k, m) for k in keys for m in data['claims'][k]['truth'] if len(data['entries'][m]['claims']) >= LARGE]
    large_loss = (np.mean([base[k][at[m]] < 12 for k, m in large]) - np.mean([new[k][at[m]] < 12 for k, m in large])
                  if large else 0.0)
    ok = gain >= 0.02 and low > 0 and large_loss <= 0.01
    harness.note(f"F25 decision: {'into production' if ok else 'not kept'} (top-12 gain {gain:+.1%}, interval from "
                 f"{low:+.1%}; large motifs {-large_loss:+.1%})")


def folktales(con, vec):
    """Hypothesis 4: over the tale types with tales, the right type's place by plain likeness to its name and
    description, by its versions, and by both (z-scores summed per claim)"""
    claims, types = tales()
    ids = sorted(types)
    T = vec([types[t].replace('\n', '. ') for t in ids])
    V = versions(con, 'tales', ids, vec)
    Q = vec([c['claim'] for c in claims])
    z = lambda x: (x - x.mean()) / (x.std() + 1e-9)  # noqa: E731
    hits = {'plain': [], 'versions': [], 'both': []}
    for q, c in zip(Q, claims):
        plain = T @ q
        best = scores(q, V, ids)[0]
        right = ids.index(c['type'])
        for name, s in (('plain', plain), ('versions', best), ('both', z(plain) + z(best))):
            hits[name].append(int((s > s[right]).sum()) < 8)
    r = {n: float(np.mean(h)) for n, h in hits.items()}
    harness.note(f"F25 folktales, {len(claims)} tales over {len(ids)} types ({len(V)} woven), right type in the top 8: "
                 f"plain {r['plain']:.1%}, versions {r['versions']:.1%}, both {r['both']:.1%}")


if __name__ == '__main__':
    {'weave': weave, 'report': report}[sys.argv[1]]()
