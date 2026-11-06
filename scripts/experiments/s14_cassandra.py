"""S14 Cassandra: a story's tellings foretold at its launch. (Nov 6, the person: "Can we backtest an algorithm to match
stories to motif bumps ... train some kind of a model to see a story and identify that it fits into a pre-existing
motif narrative", then "Yep".) Each story is read by its first hours' headlines, and every motif that already held a
claim before the launch is ranked by how likely the story is to be told through it. The answer is the motifs filed
for claims tied to the story (Bluesky narratives, mostly). Trained on stories before Oct 19, tested on Oct 19 - Nov 2,
against the motifs busiest that week; then whether a story's top motif rises in TV and radio after the launch.

    s14_cassandra.py build    stories, headlines, filings and motifs, embedded (mxbai under the lease)
    s14_cassandra.py judge    Gemma 4 26B picks from the learned arm's top 12 for each test story (lease; resumes)
    s14_cassandra.py report   hit@5 and recall@10 per arm; the bump test; examples

Data in ~/maudlin-data/archives/archives.sqlite (cassandra_*). The paper is ~/maudlin-data/papers/cassandra.md."""
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime as dt, timedelta as td

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import archive_db  # noqa: E402
import harness  # noqa: E402
from app.utils import Config  # noqa: E402

START, END = '2026-10-03', '2026-11-03'  # stories first seen in [START, END)
SPLIT = '2026-10-19'  # stories before train the learned arm; from it on, the test
EARLY = td(hours=6)  # a story is read by its headlines from these first hours
SHOWN = 8  # central headlines
BUSY_DAYS = 7
TOP_POOL = 50  # the learned arm's negatives: the rest of each train story's top this many by mixed
JUDGE_TOP = 12
BUMP_FLOOR = 20  # the bump test's motifs: this many filings or more
BUMP_DAYS, BEFORE_DAYS, DRAWS = 3, 7, 200
FEATURES = ['name', 'mean', 'nearest', 'busy', 'size']
LEFT_OUT = {'M742'}  # Straight news: kept so the models learn what isn't a motif; nothing to foretell
EXAMPLES = os.path.expanduser('~/maudlin-data/motifs/experiments/reads/s14_cassandra_examples.md')

SCHEMA = """
create table if not exists cassandra_stories (story integer primary key, first text, titles text, vector blob);
create table if not exists cassandra_claims (i integer primary key, motif text, day text, story integer, source text,
    checked text, claim text, vector blob);
create table if not exists cassandra_motifs (motif text primary key, name text, note text, vector blob);
create table if not exists cassandra_judge (story integer primary key, shown text, picks text, reason text);
"""

JUDGE_PROMPT = """These headlines are from the first hours of a new news story:

{story}

People retell the news through stories they already tell: shapes like these, each with its name, what it is, and \
claims people told through it before this story broke.

{motifs}

Which of these are people likely to tell this new story through, in posts, shows and rumors over the next days? Pick \
every one that fits, most likely first, or none. Pick a shape only if this story could be told as it, not because \
it shares a topic.

reason: one or two sentences
picks: the numbers, most likely first; empty for none"""


def db():
    con = archive_db.connect()
    con.executescript(SCHEMA)
    return con


def _vec(v) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def _arr(b) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def _embed(texts: list[str]) -> np.ndarray:
    from app.narratives import embed
    out = []
    for i in range(0, len(texts), 256):
        out.append(embed(texts[i:i + 256]))
        print(f'embed {min(i + 256, len(texts))}/{len(texts)}', flush=True)
    v = np.vstack(out).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def build():
    import app.analysis.sagas as sg
    con = db()
    site = sqlite3.connect(f'file:{os.path.join(Config.data, "data.db")}?mode=ro', uri=True)
    rows = []
    for sid, first in site.execute('select id, first_seen from story where first_seen >= ? and first_seen < ? '
                                   'order by first_seen', (START, END)).fetchall():
        cut = (dt.fromisoformat(first[:19]) + EARLY).isoformat(' ')
        hs = [t for (t,) in site.execute(
            'select h.title from story_headline sh join headline h on h.id = sh.headline_id where sh.story_id = ? '
            'and h.first_accessed <= ? order by h.first_accessed', (sid, cut))]
        hs = list({t.strip().casefold(): t.strip() for t in reversed(hs) if t and t.strip()}.values())[::-1]
        if hs:
            rows.append((sid, first[:19], hs))
    print(f'{len(rows)} stories', flush=True)
    vs = _embed([t for _, _, hs in rows for t in hs])
    k = 0
    con.execute('delete from cassandra_stories')
    for sid, first, hs in rows:
        v = vs[k:k + len(hs)]
        k += len(hs)
        c = v.mean(axis=0)
        con.execute('insert into cassandra_stories values (?, ?, ?, ?)',
                    (sid, first, json.dumps(sg.central(hs, v, SHOWN)), _vec(c / np.linalg.norm(c))))
    con.commit()
    mx = sqlite3.connect(f'file:{os.path.join(Config.data, "motif_index.sqlite")}?mode=ro', uri=True)
    live = {mid: (name, json.loads(data)) for mid, name, data in
            mx.execute('select id, name, data from motifs where merged_into is null')}
    claims = []
    for motif, claim, data in mx.execute('select motif, claim, data from filings'):
        d = json.loads(data)
        if motif in live and claim and (d.get('date') or '')[:10]:
            claims.append((motif, d['date'][:10], d.get('story'), d.get('source') or '', d.get('checked') or '',
                           claim))
    print(f'{len(claims)} filings of {len(live)} motifs', flush=True)
    cv = _embed([c[-1] for c in claims])
    con.execute('delete from cassandra_claims')
    con.executemany('insert into cassandra_claims values (?, ?, ?, ?, ?, ?, ?, ?)',
                    [(i, *c, _vec(cv[i])) for i, c in enumerate(claims)])
    ids = sorted(live)
    texts = [f'{live[m][0]}. {live[m][1].get("note") or ""}'.strip() for m in ids]
    mv = _embed(texts)
    con.execute('delete from cassandra_motifs')
    con.executemany('insert into cassandra_motifs values (?, ?, ?, ?)',
                    [(m, live[m][0], live[m][1].get('note') or '', _vec(mv[i])) for i, m in enumerate(ids)])
    con.commit()
    print('build done', flush=True)


class Data:
    """Everything an arm needs, as arrays: stories, claims (with their days, motifs and stories) and motifs"""

    def __init__(self, con):
        st = con.execute('select story, first, titles, vector from cassandra_stories order by first').fetchall()
        self.stories = [{'id': s, 'first': f, 'day': f[:10], 'titles': json.loads(t)} for s, f, t, _ in st]
        self.S = np.vstack([_arr(v) for *_, v in st])
        mo = con.execute('select motif, name, note, vector from cassandra_motifs order by motif').fetchall()
        self.motifs = [m for m, *_ in mo]
        self.names = {m: (n, note) for m, n, note, _ in mo}
        self.at = {m: i for i, m in enumerate(self.motifs)}
        self.M = np.vstack([_arr(v) for *_, v in mo])
        cl = con.execute('select motif, day, story, source, claim, vector from cassandra_claims order by i').fetchall()
        self.c_motif = np.array([self.at[m] for m, *_ in cl])
        self.c_day = np.array([d for _, d, *_ in cl])
        self.c_story = np.array([s if s is not None else -1 for _, _, s, *_ in cl])
        self.c_source = np.array([src for *_, src, _, _ in cl])
        self.c_text = [c for *_, c, _ in cl]
        self.C = np.vstack([_arr(v) for *_, v in cl])
        self.total = np.bincount(self.c_motif, minlength=len(self.motifs))
        self.keep = np.array([m not in LEFT_OUT for m in self.motifs])

    def features(self, k: int) -> tuple[np.ndarray, np.ndarray, set]:
        """For story k: (feature rows for the motifs that existed before its launch, their motif indices, the answer
        among them). A motif existed if it held a claim dated before the launch day, not tied to this story"""
        s = self.stories[k]
        before = (self.c_day < s['day']) & (self.c_story != s['id'])
        if not before.any():
            return np.zeros((0, len(FEATURES))), np.zeros(0, int), set()
        sims = self.C[before] @ self.S[k]
        mot = self.c_motif[before]
        n = len(self.motifs)
        count = np.bincount(mot, minlength=n)
        mean = np.bincount(mot, weights=sims, minlength=n) / np.maximum(count, 1)
        nearest = np.full(n, -1.0)
        np.maximum.at(nearest, mot, sims)
        week = (date.fromisoformat(s['day']) - td(days=BUSY_DAYS)).isoformat()
        busy = np.bincount(mot[self.c_day[before] >= week], minlength=n)
        idx = np.flatnonzero((count > 0) & self.keep)
        X = np.column_stack([self.M[idx] @ self.S[k], mean[idx], nearest[idx], np.log1p(busy[idx]),
                             np.log1p(count[idx])])
        answer = set(self.c_motif[self.c_story == s['id']].tolist()) & set(idx.tolist())
        return X, idx, answer


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() or 1.0)


def rankings(d: Data, con=None) -> tuple[dict, dict, list]:
    """{arm: {story index: motif indices, best first}}, the answers {story index: set}, and the test story indices"""
    from sklearn.linear_model import LogisticRegression
    feats, answers = {}, {}
    for k in range(len(d.stories)):
        X, idx, ans = d.features(k)
        if len(idx) and ans:
            feats[k], answers[k] = (X, idx), ans
    train = [k for k in feats if d.stories[k]['day'] < SPLIT]
    test = [k for k in feats if d.stories[k]['day'] >= SPLIT]

    def mixed(X):
        return _z(X[:, 0]) + _z((X[:, 1] + X[:, 2]) / 2)
    rows, ys = [], []
    for k in train:
        X, idx = feats[k]
        pool = np.argsort(-mixed(X))[:TOP_POOL]
        keep = sorted(set(pool.tolist()) | {i for i, m in enumerate(idx) if m in answers[k]})
        for i in keep:
            rows.append(X[i])
            ys.append(int(idx[i] in answers[k]))
    R = np.array(rows)
    mu, sd = R.mean(0), R.std(0) + 1e-9
    model = LogisticRegression(max_iter=2000, class_weight='balanced').fit((R - mu) / sd, ys)
    arms = defaultdict(dict)
    for k in test:
        X, idx = feats[k]
        arms['busy'][k] = idx[np.lexsort((-X[:, 4], -X[:, 3]))]
        arms['name'][k] = idx[np.argsort(-X[:, 0])]
        arms['claims'][k] = idx[np.argsort(-(X[:, 1] + X[:, 2]) / 2)]
        arms['mixed'][k] = idx[np.argsort(-mixed(X))]
        arms['learned'][k] = idx[np.argsort(-model.decision_function((X - mu) / sd))]
    if con is not None:
        judged = {s: json.loads(p) for s, p in con.execute('select story, picks from cassandra_judge')}
        if all(d.stories[k]['id'] in judged for k in test):
            for k in test:
                top = list(arms['learned'][k][:JUDGE_TOP])
                picks = [m for m in (d.at.get(x) for x in judged[d.stories[k]['id']]) if m in top]
                rest = [m for m in arms['learned'][k] if m not in picks]
                arms['judge'][k] = np.array(picks + rest)
    coef = dict(zip(FEATURES, np.round(model.coef_[0], 3).tolist()))
    print(f'learned on {len(train)} train stories, {len(ys)} pairs, {sum(ys)} positive; weights {coef}', flush=True)
    return arms, answers, test


def judge():
    from app.analysis import llm, local_models
    con = db()
    d = Data(con)
    arms, _, test = rankings(d)
    done = {s for (s,) in con.execute('select story from cassandra_judge')}
    for n, k in enumerate(test, 1):
        s = d.stories[k]
        if s['id'] in done:
            continue
        top = list(arms['learned'][k][:JUDGE_TOP])
        lines = []
        for j, m in enumerate(top, 1):
            mid = d.motifs[m]
            name, note = d.names[mid]
            before = np.flatnonzero((d.c_motif == m) & (d.c_day < s['day']) & (d.c_story != s['id']))[-2:]
            lines.append(f'{j}. {name}: {note}' + ''.join(f'\n   - "{d.c_text[i][:140]}"' for i in before))
        prompt = JUDGE_PROMPT.format(story='\n'.join(f'- {t}' for t in s['titles']), motifs='\n'.join(lines))
        schema = {"type": "object", "properties": {
            "reason": {"type": "string", "maxLength": 800},
            "picks": {"type": "array", "items": {"type": "integer", "enum": list(range(1, len(top) + 1))},
                      "maxItems": len(top)}}, "required": ["reason", "picks"]}
        answer = llm.complete_json(prompt, schema, max_tokens=500, model=local_models.BIG)
        if not answer or not isinstance(answer.get('picks'), list):
            print(f'no answer for story {s["id"]}; left for the next try', flush=True)
            sys.exit(1)
        picks = list(dict.fromkeys(top[p - 1] for p in answer['picks'] if 1 <= p <= len(top)))
        con.execute('insert or replace into cassandra_judge values (?, ?, ?, ?)',
                    (s['id'], json.dumps([d.motifs[m] for m in top]), json.dumps([d.motifs[m] for m in picks]),
                     answer.get('reason', '')))
        con.commit()
        print(f'judge {n}/{len(test)}', flush=True)
    print(f'judge {len(test)}/{len(test)} done', flush=True)


def bump(d: Data, arms: dict, answers: dict, test: list) -> tuple[float, float, float, int]:
    """The mean show-filing lift of each test story's top learned motif (one with BUMP_FLOOR+ filings) after its
    launch, the placebo's mean (the same motifs on other test stories' launch days) and the p-value"""
    shows = d.c_source == 'shows'
    daily = defaultdict(Counter)
    for m, day in zip(d.c_motif[shows], d.c_day[shows]):
        daily[m][day] += 1

    def lift(m, day):
        d0 = date.fromisoformat(day)
        after = sum(daily[m][(d0 + td(days=i)).isoformat()] for i in range(BUMP_DAYS))
        prior = sum(daily[m][(d0 - td(days=i)).isoformat()] for i in range(1, BEFORE_DAYS + 1)) / BEFORE_DAYS
        return after - BUMP_DAYS * prior
    pairs = []
    for k in test:
        top = [m for m in arms['learned'][k] if d.total[m] >= BUMP_FLOOR]
        if top:
            pairs.append((top[0], d.stories[k]['day']))
    real = float(np.mean([lift(m, day) for m, day in pairs]))
    days = [d.stories[k]['day'] for k in test]
    rng = np.random.default_rng(14)
    draws = [float(np.mean([lift(m, days[rng.integers(len(days))]) for m, _ in pairs])) for _ in range(DRAWS)]
    p = (1 + sum(x >= real for x in draws)) / (1 + DRAWS)
    return real, float(np.mean(draws)), p, len(pairs)


def report():
    con = db()
    d = Data(con)
    arms, answers, test = rankings(d, con)
    lines = [f'S14 {len(d.stories)} stories, {len(answers)} with a pre-existing answer motif ({len(test)} test, '
             f'from {SPLIT}); {len(d.motifs)} motifs, {len(d.c_day)} filings']
    for arm, rank in arms.items():
        hit = np.mean([bool(set(rank[k][:5].tolist()) & answers[k]) for k in test])
        rec = np.mean([len(set(rank[k][:10].tolist()) & answers[k]) / len(answers[k]) for k in test])
        lines.append(f'S14 {arm}: hit@5 {hit:.3f}, recall@10 {rec:.3f}')
    real, placebo, p, n = bump(d, arms, answers, test)
    lines.append(f'S14 bump: {n} stories\' top motifs, show-filing lift over {BUMP_DAYS} days {real:+.2f} against '
                 f'placebo {placebo:+.2f}, p {p:.3f}')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    out = ['# Cassandra: test stories, the learned arm\'s top 5 (✅ = told through it), and what they were told as']
    rng = np.random.default_rng(140)
    for k in sorted(rng.choice(test, size=min(30, len(test)), replace=False).tolist(), key=lambda k: d.stories[k]['day']):
        s = d.stories[k]
        out.append(f'## {s["day"]} · {s["titles"][0]}\n' + '\n'.join(
            f'- {"✅" if m in answers[k] else "·"} {d.names[d.motifs[m]][0]}' for m in arms['learned'][k][:5]) +
            '\nTold as: ' + '; '.join(d.names[d.motifs[m]][0] for m in answers[k]))
    os.makedirs(os.path.dirname(EXAMPLES), exist_ok=True)
    with open(EXAMPLES, 'w') as fh:
        fh.write('\n\n'.join(out) + '\n')
    print(f'examples in {EXAMPLES}', flush=True)


if __name__ == '__main__':
    {'build': build, 'judge': judge, 'report': report}[sys.argv[1] if len(sys.argv) > 1 else 'report']()
