"""S9 Daedalus: the story and saga-part settings searched together, against Osiris's key (Nov 3; the person: "Have we
tried simply doing a kind of optimization or gradient descent on the hyperparameters for our story and saga
grouping?", then "Just run it!"). Daedalus told Icarus to fly the middle course, not too near the sun nor the sea.

Osiris (S7) keyed 15 running stories by event and replayed a month of hourly runs, but its replay fed each run only the
headlines live that half hour, where production clusters every headline seen in the last 24 hours (data.py,
STORY_LOOKBACK_HOURS, the live ones kept first). So 866 of the 4,072 keyed headlines never reached a story in the
replay, and it failed its fidelity test. Daedalus clusters as production does, then searches the settings.

    s9_daedalus.py clusters CONFIG...   each run's clusters under these clustering settings (CONFIGS); resumes
    s9_daedalus.py trial CONFIG PARAMS  one replay with these story settings (JSON), scored and stored
    s9_daedalus.py search CONFIG N W    today's settings, then N random settings, then a coordinate refinement from the
                                        best, on W processes at once
    s9_daedalus.py configs W            the other clustering settings, each with today's story settings and the best
    s9_daedalus.py report               fidelity, the best on the tuning cases, and the held-out cases

Data in ~/maudlin-data/archives/archives.sqlite (daedalus_*); the key is Osiris's (osiris_key). The paper is
~/maudlin-data/papers/daedalus.md."""
import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s7_osiris as o7  # noqa: E402
from app.utils import Config  # noqa: E402

WORK = os.path.join(harness.EXP, 's9_daedalus')
LIVE = td(minutes=30)  # Config.last_accessed: the latest scrape less half an hour
PER_STORY = 6
# Clustering settings: (likeness threshold, hours of dropped-off headlines kept in, seam cut score)
CONFIGS = {'base': (0.80, 24, 0.6),  # production today
           'look12': (0.80, 12, 0.6), 'look6': (0.80, 6, 0.6),
           'thr78': (0.78, 24, 0.6), 'thr82': (0.82, 24, 0.6),
           'seam5': (0.80, 24, 0.5), 'seam7': (0.80, 24, 0.7)}
STAY, NEVER = -5256000, 5256000  # carried minutes: every held headline stays put / the older-headline rule never acts
# The story settings (stories.py) and the values searched; the first value listed is not special, DEFAULTS is today
SPACE = {'carried': [STAY, 0, 30, 120, 360, NEVER],  # CARRIED_SLACK, minutes
         'window': [12, 24, 48, 96],  # RETURN_WINDOW, hours
         'gap': [30, 60, 90, 180],  # RETURN_GAP, minutes
         'words': [1, 2, 3, 4],  # RETURN_WORDS
         'candidates': [1, 2, 3, 5],  # RETURN_CANDIDATES
         'rejoin_least': [2, 3, 5, 8],  # REJOIN_LEAST
         'rejoin_share': [0.1, 0.2, 0.3, 0.5],  # REJOIN_SHARE
         'share': [0.2, 0.3, 0.4],  # frequent_words' share
         'continue_share': [0.0, 0.1, 0.2, 0.3, 0.5]}  # CONTINUE_SHARE (new, Nov 3)
DEFAULTS = {'carried': 30, 'window': 48, 'gap': 90, 'words': 2, 'candidates': 2, 'rejoin_least': 3,
            'rejoin_share': 0.2, 'share': 0.3, 'continue_share': 0.0}
SEED = 9

SCHEMA = """
create table if not exists daedalus_runs (config text, at text, headlines integer, clusters integer,
    primary key (config, at));
create table if not exists daedalus_clusters (config text, at text, cluster integer, headline integer, seam_root integer,
    primary key (config, at, headline));
create table if not exists daedalus_trials (trial text primary key, config text, params text, stage text,
    tune_f real, held_f real, all_f real, p real, r real, cases text, stories integer, at text);
"""


def db() -> sqlite3.Connection:
    con = o7.db()
    con.executescript(SCHEMA)
    return con


def held_cases(cases) -> set[str]:
    """The five held-out cases: the five whose names hash lowest (chosen blind, before any score)"""
    return set(sorted(cases, key=lambda c: hashlib.sha1(c.encode()).hexdigest())[:5])


# ---- clusters, as production makes them ----

def pool_at(s: sqlite3.Connection, at: dt, hours: int) -> pd.DataFrame:
    """get_main_headline_df(td(hours=...)) at `at`: headlines first seen in the last three days and last seen within
    `hours` of the live half hour, news only, US and the exempted British outlets, no aggregators; `live` marks those
    still on a front page"""
    from app.analysis.newsfilter import NEWS_THRESHOLD
    from app.site.page_headlines import AGGREGATORS
    from app.utils import Country
    rows = s.execute("""select h.id, coalesce(h.processed, h.title), ag.name, ar.url, ag._country, h.last_accessed
        from headline h join article ar on ar.id = h.article_id join agency ag on ag.id = ar.agency_id
        where h.first_accessed <= ? and h.last_accessed > ? and h.first_accessed > ?
          and (h.news_score is null or h.news_score >= ?)
        order by h.first_accessed desc, h.position asc""",
                     (str(at), str(at - LIVE - td(hours=hours)), str(at - td(days=3)), NEWS_THRESHOLD)).fetchall()
    df = pd.DataFrame(rows, columns=['headline_id', 'title', 'agency', 'url', 'country', 'last'])
    df = df.drop_duplicates(['agency', 'url', 'title'])
    us, gb = Country.us.value, Country.gb.value
    df = df[(df['country'] == us) | ((df['country'] == gb) & df['agency'].isin(Config.exempted_foreign_media))]
    df = df[~df['agency'].isin(AGGREGATORS)].reset_index(drop=True)
    df['live'] = df['last'] > str(at - LIVE)
    return df


def clusters():
    """Each run's clusters under each named setting, as cluster_and_summarize makes them up to sync_stories; one pool
    and one set of embeddings a run for all the settings asked"""
    from app.analysis import clustering as cl
    from app.analysis.pipelines import default_pipeline, prepare
    names = sys.argv[2:] or ['base']
    os.makedirs(WORK, exist_ok=True)
    seams_path = os.path.join(WORK, 'story_seams.json')
    if not os.path.exists(seams_path):  # production's verdicts, and those Osiris asked
        seams = json.load(open(os.path.join(Config.cache, 'story_seams.json')))
        mine = os.path.join(o7.WORK, 'story_seams.json')
        if os.path.exists(mine):
            seams = {**json.load(open(mine)), **seams}
        json.dump(seams, open(seams_path, 'w'))
    seams = json.load(open(seams_path))
    vectors = os.path.join(o7.WORK, 'vectors.sqlite')  # Osiris's embeddings, by headline
    pipeline = [*default_pipeline, ' '.join]
    con = db()
    done = defaultdict(set)
    for c, a in con.execute('select config, at from daedalus_runs'):
        done[c].add(a)
    times = [a for a in o7.run_times() if any(a not in done[n] for n in names)]
    hours = max(CONFIGS[n][1] for n in names)
    print(f'{len(times)} runs to cluster for {", ".join(names)}', flush=True)
    with contextlib.closing(o7.site()) as s:
        for k, at in enumerate(times):
            when = dt.fromisoformat(at)
            pool = pool_at(s, when, hours)
            if len(pool) < PER_STORY:
                for n in names:
                    con.execute('insert or replace into daedalus_runs values (?, ?, ?, 0)', (n, at, len(pool)))
                continue
            pool['processed'] = pool['title'].apply(lambda x: prepare(x, pipeline))
            v = cl.ollama_embed(pool['title'].tolist(), cache=vectors, keep_days=3650).astype(np.float64)
            full = v @ v.T
            for n in names:
                if at in done[n]:
                    continue
                thr, look, seam = CONFIGS[n]
                keep = np.flatnonzero((pool['last'] > str(when - LIVE - td(hours=look))).to_numpy())
                df = pool.iloc[keep].reset_index(drop=True)
                texts = df['title'].tolist()
                sim = full[np.ix_(keep, keep)].copy()
                sim = cl.unlink_money_conflicts(sim, texts)
                sim = cl.unlink_place_conflicts(sim, texts)
                groups = cl.form_clusters(sim, PER_STORY, thr)
                cl.SEAM = seam
                roots = []
                groups, _ = cl.split_seams(groups, df['processed'].tolist(), df['agency'].tolist(), PER_STORY, texts,
                                           confirm=lambda a, b: cl.two_events(a, b, seams), roots=roots)
                df = cl.label_clusters(df, groups)
                df['seam_root'] = df['cluster'].map(dict(enumerate(roots)))
                df = df[df['cluster'] != -1]
                df = df.sort_values('live', ascending=False, kind='stable')  # the live one per outlet, as production
                df = df.drop_duplicates(subset=['cluster', 'agency'], keep='first')
                df = df.groupby('cluster').filter(lambda x: len(x) >= PER_STORY)
                con.executemany('insert or replace into daedalus_clusters values (?, ?, ?, ?, ?)',
                                [(n, at, int(c), int(h), int(r) if pd.notna(r) else None)
                                 for c, h, r in zip(df['cluster'], df['headline_id'], df['seam_root'])])
                con.execute('insert or replace into daedalus_runs values (?, ?, ?, ?)',
                            (n, at, len(texts), int(df['cluster'].nunique())))
            con.commit()
            if k % 10 == 0:
                json.dump(seams, open(seams_path, 'w'))
                print(f'{at}: pool {len(pool)} ({k + 1}/{len(times)})', flush=True)
    json.dump(seams, open(seams_path, 'w'))


# ---- one replay ----

def trial_id(config: str, params: dict) -> str:
    return config + '-' + hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]


def replay(config: str, params: dict, path: str) -> dict[int, int]:
    """A fresh story database fed every run's clusters under `config`, with these story settings: {headline: story}"""
    import functools
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.analysis.stories as st
    import app.models as models
    from app.models import Base, Headline, StoryHeadline
    if os.path.exists(path):
        os.remove(path)
    engine = create_engine(f'sqlite:///{path}', connect_args={'timeout': 60})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    st.Session = models.Session = session
    st.SqlLock = contextlib.nullcontext()
    returns = os.path.join(WORK, 'story_returns.json')
    if not os.path.exists(returns):  # production's same-event verdicts, and Osiris's
        shutil.copy(os.path.join(o7.WORK, 'story_returns.json'), returns)
    st.RETURNS = returns
    st.CARRIED_SLACK = td(minutes=params['carried'])
    st.RETURN_WINDOW = td(hours=params['window'])
    st.RETURN_GAP = td(minutes=params['gap'])
    st.RETURN_WORDS = params['words']
    st.RETURN_CANDIDATES = params['candidates']
    st.REJOIN_LEAST = params['rejoin_least']
    st.REJOIN_SHARE = params['rejoin_share']
    st.CONTINUE_SHARE = params['continue_share']
    base_words = getattr(st.frequent_words, 'func', st.frequent_words)
    st.frequent_words = functools.partial(base_words, share=params['share'])
    o7.Clock.install(st)
    con = db()
    by_run = defaultdict(list)
    for at, c, h, r in con.execute('select at, cluster, headline, seam_root from daedalus_clusters where config = ? '
                                   'order by at', (config,)):
        by_run[at].append((c, h, r))
    ids = list({h for rows in by_run.values() for _, h, _ in rows})
    meta = {}
    with contextlib.closing(o7.site()) as s:
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            for r in s.execute(f"""select h.id, coalesce(h.processed, h.title), ag.name, h.first_accessed,
                    h.vader_compound, h.afinn, h.event_score from headline h join article ar on ar.id = h.article_id
                    join agency ag on ag.id = ar.agency_id where h.id in ({','.join('?' * len(chunk))})""", chunk):
                meta[r[0]] = r[1:]
    seen = set()
    for n, at in enumerate(sorted(by_run)):
        rows = by_run[at]
        new = [h for h in dict.fromkeys(h for _, h, _ in rows) if h not in seen]
        with session() as m:
            for h in new:
                first = dt.fromisoformat(meta[h][2][:26])
                m.add(Headline(id=h, article_id=h, title=meta[h][0], first_accessed=first, last_accessed=first))
            m.commit()
        seen.update(new)
        df = pd.DataFrame([{'cluster': c, 'headline_id': h, 'seam_root': r, 'title': meta[h][0], 'agency': meta[h][1],
                            'vader_compound': meta[h][3] or 0.0, 'afinn': meta[h][4] or 0.0,
                            'event_score': meta[h][5] or 0.0} for c, h, r in rows])
        o7.Clock.at = dt.fromisoformat(at)
        stories = st.sync_stories(df)
        st.fold_twins(df, stories)
    with session() as m:
        out = dict(m.query(StoryHeadline.headline_id, StoryHeadline.story_id))
    engine.dispose()
    os.remove(path)
    return out


def score(story_of: dict) -> dict:
    """Osiris's measures on every case, averaged over the tuning cases, the held-out ones and all fifteen"""
    con = db()
    keys = o7.answer_key(con)
    firsts = dict(con.execute('select headline, first from osiris_headlines'))
    held = held_cases(keys)
    cases = {c: o7.measures(k, story_of, firsts) for c, k in keys.items()}
    cases = {c: m for c, m in cases.items() if m}
    mean = lambda f, cs: float(np.mean([cases[c][f] for c in cs]))  # noqa: E731
    tune = [c for c in cases if c not in held]
    return {'tune_f': mean('f', tune), 'held_f': mean('f', [c for c in cases if c in held]), 'all_f': mean('f', cases),
            'p': mean('p', cases), 'r': mean('r', cases),
            'cases': {c: {k: m[k] for k in ('p', 'r', 'f', 'carried', 'split', 'mixed')} for c, m in cases.items()}}


def trial():
    config, params, stage = sys.argv[2], json.loads(sys.argv[3]), (sys.argv[4] if len(sys.argv) > 4 else '')
    params = {**DEFAULTS, **params}
    tid = trial_id(config, params)
    os.makedirs(os.path.join(WORK, 'trials'), exist_ok=True)
    story_of = replay(config, params, os.path.join(WORK, 'trials', f'{tid}.sqlite'))
    sc = score(story_of)
    con = db()
    con.execute('insert or replace into daedalus_trials values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (tid, config, json.dumps(params, sort_keys=True), stage, sc['tune_f'], sc['held_f'], sc['all_f'],
                 sc['p'], sc['r'], json.dumps(sc['cases']), len(set(story_of.values())),
                 dt.now().isoformat(timespec='seconds')))
    con.commit()
    print(f'{tid} {stage}: tune F {sc["tune_f"]:.3f} (p {sc["p"]:.2f} r {sc["r"]:.2f}) {params}', flush=True)


# ---- the search ----

def run_trials(config: str, settings: list[dict], stage: str, workers: int):
    """Each setting not yet tried, `workers` replays at a time, each in its own process (the stories module is set
    per replay)"""
    con = db()
    tried = {t for (t,) in con.execute('select trial from daedalus_trials')}
    todo, seen = [], set()
    for p in settings:
        p = {**DEFAULTS, **p}
        t = trial_id(config, p)
        if t not in tried and t not in seen:
            todo.append(p)
            seen.add(t)
    print(f'{stage}: {len(todo)} replays to run on {config}', flush=True)
    me = os.path.abspath(__file__)

    def one(p):
        r = subprocess.run([sys.executable, '-u', me, 'trial', config, json.dumps(p), stage], capture_output=True,
                           text=True, cwd='/home/mas/Repos/maudlin2')
        line = (r.stdout.strip().splitlines() or [''])[-1]
        print(line if r.returncode == 0 else f'failed: {p}\n{r.stderr[-2000:]}', flush=True)
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, todo))


def best(config: str | None = None) -> tuple[str, dict, float] | None:
    con = db()
    q = 'select trial, params, tune_f from daedalus_trials' + (' where config = ?' if config else '') + \
        ' order by tune_f desc, trial limit 1'
    row = con.execute(q, (config,) if config else ()).fetchone()
    return (row[0], json.loads(row[1]), row[2]) if row else None


def search():
    config, n, workers = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    run_trials(config, [DEFAULTS], 'today', 1)
    rng = np.random.default_rng(SEED)
    randoms = [{k: v[rng.integers(len(v))] for k, v in SPACE.items()} for _ in range(n)]
    randoms = [{k: (v.item() if hasattr(v, 'item') else v) for k, v in p.items()} for p in randoms]
    run_trials(config, randoms, 'random', workers)
    for rnd in (1, 2):  # coordinate refinement: every other value of each setting, one at a time, from the best
        _, start, f = best(config)
        steps = [{**start, k: v} for k, vals in SPACE.items() for v in vals if v != start[k]]
        run_trials(config, steps, f'refine {rnd}', workers)
        _, after, f2 = best(config)
        if f2 <= f:
            break
        # take every single change that helped together, then refine once more from there
        con = db()
        helped = {}
        for params, tf in con.execute('select params, tune_f from daedalus_trials where config = ? and stage = ?',
                                      (config, f'refine {rnd}')):
            p = json.loads(params)
            diff = [k for k in p if p[k] != start[k]]
            if len(diff) == 1 and tf > f and tf > helped.get(diff[0], (None, -1))[1]:
                helped[diff[0]] = (p[diff[0]], tf)
        run_trials(config, [{**start, **{k: v for k, (v, _) in helped.items()}}], f'combined {rnd}', 1)


def configs():
    workers = int(sys.argv[2])
    con = db()
    have = {c for (c,) in con.execute('select distinct config from daedalus_runs')}
    _, top, _ = best('base')
    for name in CONFIGS:
        if name != 'base' and name in have:
            run_trials(name, [DEFAULTS, top], 'clustering', workers)


# ---- the report ----

def report():
    con = db()
    keys = o7.answer_key(con)
    held = held_cases(keys)
    firsts = dict(con.execute('select headline, first from osiris_headlines'))
    sagas = {c: set(json.loads(s)) for c, s in con.execute('select case_id, sagas from osiris_cases')}
    prod = {}
    with contextlib.closing(o7.site()) as s:
        for h, story, saga in s.execute('select sh.headline_id, sh.story_id, st.saga_id from story_headline sh '
                                        'join story st on st.id = sh.story_id'):
            prod[h] = (story, saga)
    P = {c: o7.measures(k, {h: prod[h][0] for h in k if h in prod and prod[h][1] in sagas[c]}, firsts)
         for c, k in keys.items()}
    lines = [f'S9 held out (blind, by name hash): {", ".join(sorted(held))}']
    rows = con.execute('select trial, config, params, stage, tune_f, held_f, all_f, p, r, cases, stories '
                       'from daedalus_trials order by tune_f desc').fetchall()
    trials = {r[0]: r for r in rows}
    today = trials.get(trial_id('base', DEFAULTS))
    if today:
        cs = json.loads(today[9])
        close = sum(abs(cs[c]['f'] - P[c]['f']) <= 0.05 for c in cs)
        lines.append(f'S9 fidelity (today\'s settings, production\'s pool): F {today[6]:.3f} against production '
                     f'{np.mean([m["f"] for m in P.values()]):.3f}; within 0.05 on {close} of {len(cs)} cases')
        for c in sorted(cs):
            lines.append(f'S9   {c}: replay F {cs[c]["f"]:.2f} (p {cs[c]["p"]:.2f} r {cs[c]["r"]:.2f}), production '
                         f'{P[c]["f"]:.2f} (p {P[c]["p"]:.2f} r {P[c]["r"]:.2f})' + (' · held' if c in held else ''))
    lines.append(f'S9 trials: {len(rows)}')
    for r in rows[:10]:
        lines.append(f'S9   {r[0]} [{r[3]}] tune {r[4]:.3f} held {r[5]:.3f} all {r[6]:.3f} (p {r[7]:.2f} '
                     f'r {r[8]:.2f}) {r[2]}')
    by_config = {}
    for r in rows:
        by_config.setdefault(r[1], r)
    for c, r in sorted(by_config.items()):
        d = trials.get(trial_id(c, DEFAULTS))
        lines.append(f'S9 config {c} {CONFIGS[c]}: best tune {r[4]:.3f} held {r[5]:.3f}' +
                     (f'; today\'s story settings tune {d[4]:.3f} held {d[5]:.3f}' if d else ''))
    if today and rows:
        top = rows[0]
        lines.append(f'S9 best on the tuning cases: {top[0]} tune {top[4]:.3f} (today {today[4]:.3f}, '
                     f'{top[4] - today[4]:+.3f}); held out {top[5]:.3f} (today {today[5]:.3f}, {top[5] - today[5]:+.3f})')
        tc, dc = json.loads(top[9]), json.loads(today[9])
        worse = [c for c in held if c in tc and tc[c]['f'] < dc[c]['f'] - 0.005]
        lines.append(f'S9   held-out cases worse under the best: {len(worse)} of {len(held)} {worse}')
        lines.append(f'S9   stories made over the month: {top[10]} (today {today[10]}, {top[10] / today[10] - 1:+.0%})')
        for c in sorted(tc):
            lines.append(f'S9   {c}: today F {dc[c]["f"]:.2f} (p {dc[c]["p"]:.2f}) -> {tc[c]["f"]:.2f} '
                         f'(p {tc[c]["p"]:.2f} r {tc[c]["r"]:.2f})' + (' · held' if c in held else ''))
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


if __name__ == '__main__':
    {'clusters': clusters, 'trial': trial, 'search': search, 'configs': configs, 'report': report}[
        sys.argv[1] if len(sys.argv) > 1 else 'report']()
