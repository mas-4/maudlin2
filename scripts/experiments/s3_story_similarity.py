"""S3 what makes headlines one story: word matching, embeddings, or both (Oct 11). Stories were made from TF-IDF word
matching (the person's 2024 algorithm: headlines sharing rare words, cosine 0.5, connected clusters) until Oct 3, then
from embeddings (potion, then mxbai-embed-large at 0.80 on Oct 4, after a four-model test of embedders only: TF-IDF was
never measured). Embeddings catch paraphrase but blur what happened: on saga-30's diesel-deal and Zelensky headlines the
two events sit at 89% of their own likeness by mxbai, 57% by TF-IDF. The person: "probably a hybrid would help a lot".

Arms, each clustered as production does (clustering.form_clusters, money conflicts unlinked, six outlets a story):
    tfidf          TF-IDF cosine on the headlines (the 2024 way)
    mxbai          the embeddings (production)
    gate T         mxbai, but a pair links only if its TF-IDF cosine is at least T: some distinctive words in common
    blend          the mean of the two, each scaled to its own spread over the day's pairs
    seams T        two passes (the person's idea): stories by mxbai, then inside each a TF-IDF graph (links at T or
                   more); where it falls into two or more groups of OUTLETS outlets each, the story is cut there, and
                   the headlines no words link (often pure paraphrase) join the side they're nearest by meaning
At equal coverage (each arm's threshold set so about COVERAGE headlines are in stories), as on Oct 4:
- precision: cross-outlet pairs sampled inside each arm's stories, judged "the same news event?" by Gemma 26B under
  two wordings, agreement only;
- recall: a shared pool of pairs sampled across every arm's similarity range, judged the same way: of the pairs judged
  the same event, the share each arm puts in one story;
- and on S1's 89 day-to-day transitions (Claude's answer key, 53 new events): how well each arm's likeness of the day's
  new headlines to the story's earlier ones tells a new event from an update (AUC), with no clustering needed.

    s3_story_similarity.py prepare | judge | report"""
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import clustering as cl  # noqa: E402

OUT = os.path.join(harness.EXP, 's3_story_similarity.json')
DAY = os.path.join(harness.EXP, 's3_day.json')  # the day's headlines, kept so every stage sees the same day
COVERAGE = (400, 500)  # headlines in stories (Oct 4 used 900 and 1,100 of 6,733; a Sunday of 4,989 tops out lower: TF-IDF ~520, mxbai ~740)
OUTLETS = 6
GATES = (0.15, 0.25, 0.35)
SEAMS = (0.15, 0.25)
PER_CELL = 80  # pairs judged for each arm's precision at each coverage
POOL = 700  # pairs in the shared recall pool
MODEL = 'gemma4:26b'
ASK = ["""Two news headlines:
A: {a}
B: {b}

Do they report the same news event: the same announcement, incident, decision, ruling, vote, game or report (one may
add details or reactions)? A different development, even in the same running story (a new statement, a response, a
later vote, another attack), is a different event.

reason: one sentence
same: true or false""", """A: {a}
B: {b}

Would an editor put these two headlines on one story card, because they report one news event, or on two, because
they report different events (a later development, someone's response, another incident on the same subject)?

reason: one sentence
same: true if one card"""]
SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 300}, "same": {"type": "boolean"}},
          "required": ["reason", "same"]}


def day() -> list[dict]:
    """The last 24 hours of headlines as the hourly run clusters them: US outlets (and the exempted British ones), not
    aggregators, one row per outlet's headline"""
    if os.path.exists(DAY):
        return json.load(open(DAY))
    from app.site.data import STORY_LOOKBACK_HOURS, DataHandler
    from app.site.page_headlines import AGGREGATORS
    from app.utils import Config, Country
    from datetime import timedelta as td
    Config.set_debug()
    df = DataHandler.get_main_headline_df(td(hours=STORY_LOOKBACK_HOURS))
    us, gb = Country.us.value, Country.gb.value
    df = df[((df['country'] == us) | ((df['country'] == gb) & df['agency'].isin(Config.exempted_foreign_media)))
            & ~df['agency'].isin(AGGREGATORS)]
    rows = [{'title': t, 'agency': a} for t, a in zip(df['title'], df['agency']) if t]
    json.dump(rows, open(DAY, 'w'))
    return rows


def tfidf(texts: list[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    T = TfidfVectorizer().fit_transform(texts)
    return (T @ T.T).toarray()


def matrices(texts: list[str]) -> dict[str, np.ndarray]:
    t = tfidf(texts)
    v = cl.ollama_embed(texts).astype(np.float64)
    m = v @ v.T
    out = {'tfidf': t, 'mxbai': m}
    for g in GATES:
        out[f'gate {g}'] = np.where(t >= g, m, 0.0)
    off = ~np.eye(len(texts), dtype=bool)
    z = lambda x: (x - x[off].mean()) / x[off].std()  # noqa: E731
    out['blend'] = (z(t) + z(m)) / 2
    return out


def stories(S: np.ndarray, threshold: float, rows: list[dict]) -> list[set]:
    clusters = cl.form_clusters(cl.unlink_money_conflicts(S.copy(), [r['title'] for r in rows]), OUTLETS, threshold)
    return [c for c in clusters if len({rows[i]['agency'] for i in c}) >= OUTLETS]


def split_seams(clusters: list[set], T: np.ndarray, E: np.ndarray, tau: float, rows: list[dict]) -> list[set]:
    """Each story cut where its TF-IDF graph (links at tau or more) falls into two or more groups of OUTLETS outlets;
    the rest of its headlines join the group they're nearest by meaning (mean embedding likeness)"""
    out = []
    for c in clusters:
        members = sorted(c)
        from scipy.sparse.csgraph import connected_components
        _, lab = connected_components(T[np.ix_(members, members)] >= tau, directed=False)
        comps = {}
        for k, g in enumerate(lab):
            comps.setdefault(g, []).append(members[k])
        big = [g for g in comps.values() if len({rows[i]['agency'] for i in g}) >= OUTLETS]
        if len(big) < 2:
            out.append(c)
            continue
        sides = [set(g) for g in big]
        for i in members:
            if not any(i in g for g in sides):
                best = max(range(len(sides)), key=lambda n: E[i, list(sides[n])].mean())
                sides[best].add(i)
        out += sides
    return out


def coverage(clusters: list[set], rows: list[dict]) -> int:
    """Headlines in stories, one per outlet in each"""
    return sum(len({rows[i]['agency'] for i in c}) for c in clusters)


def threshold_for(S: np.ndarray, target: int, rows: list[dict], make=None) -> float:
    """The threshold at which an arm puts about `target` headlines into stories. Not a bisection: coverage rises as the
    threshold falls only until everything chains into one giant story (which counts its outlets once), so scan down
    from the top through the highest pairs' values, stop past the target, then narrow between the last two"""
    make = make or (lambda t: stories(S, t, rows))
    rnd = np.random.default_rng(0)
    n = len(S)
    i, j = rnd.integers(0, n, 400000), rnd.integers(0, n, 400000)
    vals = S[i[i != j], j[i != j]]
    top = float(np.sort(S[~np.eye(n, dtype=bool)])[-n // 2])  # stories form in the very top of the pairs (mxbai 0.80)
    grid = np.linspace(top, float(np.quantile(vals, 0.99)), 60)
    prev = top
    for t in grid:
        if coverage(make(float(t)), rows) >= target:
            lo, hi = float(t), prev  # coverage at lo >= target > coverage at hi
            for _ in range(8):
                mid = (lo + hi) / 2
                if coverage(make(mid), rows) >= target:
                    lo = mid
                else:
                    hi = mid
            return round(lo, 4)
        prev = float(t)
    return round(float(grid[-1]), 4)


def prepare():
    rows = day()
    texts = [r['title'] for r in rows]
    M = matrices(texts)
    rnd = random.Random(3)
    state = {'headlines': len(rows), 'arms': {}, 'pairs': {}}
    makers = {arm: (S, None) for arm, S in M.items()}
    for tau in SEAMS:  # the two passes: mxbai's stories, cut at TF-IDF's seams
        makers[f'seams {tau}'] = (M['mxbai'], lambda t, tau=tau: split_seams(stories(M['mxbai'], t, rows), M['tfidf'],
                                                                             M['mxbai'], tau, rows))
    for arm, (S, make) in makers.items():
        for target in COVERAGE:
            th = threshold_for(S, target, rows, make)
            cs = make(th) if make else stories(S, th, rows)
            label = {i: n for n, c in enumerate(cs) for i in c}
            inside = [(i, j) for c in cs for i in c for j in c if i < j and rows[i]['agency'] != rows[j]['agency']]
            sample = rnd.sample(inside, min(PER_CELL, len(inside)))
            state['arms'][f'{arm} @{target}'] = {'threshold': th, 'stories': len(cs), 'covered': coverage(cs, rows),
                                                 'label': {str(i): n for i, n in label.items()},
                                                 'precision_pairs': [list(p) for p in sample]}
    # the shared recall pool: pairs spread over every arm's similarity range (cross-outlet), so each arm's links and
    # misses are both in it
    n = len(rows)
    pool = set()
    off = np.argwhere(np.triu(np.ones((n, n), dtype=bool), 1))
    for arm, S in M.items():
        vals = S[off[:, 0], off[:, 1]]
        qs = np.quantile(vals, np.linspace(0.9, 1, 12))  # where links can happen: the top tenth of each arm's pairs
        for lo, hi in zip(qs, qs[1:]):
            band = off[(vals >= lo) & (vals <= hi)]
            for i, j in band[rnd.sample(range(len(band)), min(len(band), POOL // (len(M) * 11)))]:
                if rows[i]['agency'] != rows[j]['agency']:
                    pool.add((int(i), int(j)))
    state['pool'] = sorted(pool)
    json.dump(state, open(OUT, 'w'))
    print(f"prepare: {n} headlines; {len(makers)} arms x {len(COVERAGE)} coverages; pool {len(pool)} pairs", flush=True)
    for k, a in state['arms'].items():
        print(f"  {k}: threshold {a['threshold']}, {a['stories']} stories, {a['covered']} headlines", flush=True)


def judge():
    """Gemma's two wordings on every pair to be judged (cached by the two headlines)"""
    rows = day()
    state = json.load(open(OUT))
    got = state.setdefault('judged', {})
    pairs = {tuple(p) for a in state['arms'].values() for p in a['precision_pairs']} | {tuple(p) for p in state['pool']}
    todo = [p for p in pairs if f'{p[0]}|{p[1]}' not in got]

    def ask(p):
        a, b = rows[p[0]]['title'], rows[p[1]]['title']
        answers = [llm.complete_json(q.format(a=a, b=b), SCHEMA, max_tokens=300, model=MODEL) for q in ASK]
        return None if any(x is None for x in answers) else [bool(x['same']) for x in answers]
    for start in range(0, len(todo), 64):
        part = todo[start:start + 64]
        for p, r in zip(part, llm.parallel(ask, part)):
            if r is not None:
                got[f'{p[0]}|{p[1]}'] = r
        json.dump(state, open(OUT, 'w'))
        print(f'judge: {len(got)}/{len(pairs)}', flush=True)


def transitions_auc() -> dict[str, float]:
    """On S1's transitions: how well each arm's likeness of the day's new headlines to the earlier ones tells a new
    event (lower likeness) from an update"""
    from sklearn.metrics import roc_auc_score
    import s1_story_splits as s1
    saved = json.load(open(s1.OUT))
    person = saved['person']
    ts = [t for t in s1.transitions() if t['key'] in person]
    y = np.array([person[t['key']] for t in ts], dtype=bool)
    scores = {}
    for t in ts:
        texts = t['before'] + t['new']
        M = matrices(texts)
        n = len(t['before'])
        for arm, S in M.items():
            across = S[:n, n:].mean()
            within = (S[:n, :n][~np.eye(n, dtype=bool)].mean() + S[n:, n:][~np.eye(len(t['new']), dtype=bool)].mean()) / 2
            scores.setdefault(arm, []).append(-(across / within) if within else 0)  # new events: less alike across
    return {arm: round(float(roc_auc_score(y, s)), 3) for arm, s in scores.items()}


def report():
    state = json.load(open(OUT))
    got = state.get('judged', {})
    agreed = {k: v[0] for k, v in got.items() if v[0] == v[1]}  # both wordings alike, as on Oct 4
    lines = [f"S3 story likeness, {state['headlines']} headlines of a day; precision and recall judged by Gemma 26B "
             f"under two wordings (agreement only: {len(agreed)} of {len(got)} pairs)"]
    same_pool = [tuple(map(int, k.split('|'))) for k, v in agreed.items() if v and list(map(int, k.split('|'))) in state['pool']]
    for name, a in state['arms'].items():
        pp = [agreed[f'{i}|{j}'] for i, j in a['precision_pairs'] if f'{i}|{j}' in agreed]
        lab = a['label']
        rec = [str(i) in lab and lab.get(str(i)) == lab.get(str(j)) for i, j in same_pool]
        lines.append(f"  {name:16} threshold {a['threshold']:<7} {a['stories']:>3} stories, {a['covered']:>4} headlines: "
                     f"precision {np.mean(pp):.2f} (n {len(pp)}), recall {np.mean(rec):.2f} (n {len(rec)})")
    try:
        auc = transitions_auc()
        lines.append('  on S1\'s transitions, new event or update (AUC): ' + ', '.join(f'{k} {v}' for k, v in auc.items()))
    except Exception as e:  # noqa: BLE001
        lines.append(f'  transitions: {e}')
    for line in lines:
        print(line, flush=True)
        harness.note(line)


def main():
    {'prepare': prepare, 'judge': judge, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
