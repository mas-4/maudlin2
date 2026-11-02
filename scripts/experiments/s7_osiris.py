"""S7 Osiris: are a saga's parts its events? (Nov 2, the person, of the Michigan Senate saga: "I'm worried it
reformulated old headlines into the new one"; of the ex-FBI officials' saga: "this one is too separated: is it possible
for us to design experiments to improve our algorithm"). Fifteen running stories, every headline sorted into the
story's events (the answer key, drafted blind by Claude readers and corrected by the person), and the ways of making
stories scored against it: production as stored (P), and a replay of every hourly run since Oct 4 under yesterday's
story code (A), today's (B) and a stay-put rule (C); and Gemma sorting each case's headlines into events directly (E).

    s7_osiris.py key        load the drafts (and any corrections) into archives.sqlite: osiris_events, osiris_key
    s7_osiris.py clusters   rebuild each run's live headlines and cluster them as production does (once for all arms;
                            embeddings in the experiment's own cache, Gemma's seam verdicts from a copy of production's,
                            misses asked); resumes run by run
    s7_osiris.py replay     each arm's own in-memory story database, fed every run's clusters with the clock set to it
    s7_osiris.py sort       arm E: Gemma 4 26B sorts each case's headlines into events, twenty at a time
    s7_osiris.py report     the measures for every arm (provisional until the person's corrections are in)

The paper is ~/maudlin-data/papers/osiris.md."""
import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import archive_db  # noqa: E402
import harness  # noqa: E402
from app.utils import Config  # noqa: E402

NOTES = os.path.expanduser('~/Repos/maudlin-notes/experiments/osiris')
WORK = os.path.join(harness.EXP, 's7_osiris')  # the experiment's caches: embeddings, copies of Gemma's verdicts
START, END = '2026-10-04 13:00', '2026-11-02 19:30'
LIVE_SLACK = td(minutes=30)  # Config.last_accessed: a headline seen within this of a run was on its front page
LOOKBACK = td(days=3)  # get_main_headline_df: headlines first seen in the last three days
PER_STORY = 6  # n_samples_per_cluster
ARMS = ('A', 'B', 'C')
SPLIT_SHARE = 0.7  # an event no story holds this much of is split; a story whose biggest event is under it, mixed
SPLIT_LEAST = 5
SORT_BATCH = 20
SORT_MODEL = 'gemma4:26b'

SCHEMA = """
create table if not exists osiris_cases (case_id text primary key, story text, sagas text, candidates text);
create table if not exists osiris_events (case_id text, event text, name text, first text, note text, by text,
    primary key (case_id, event, by));
create table if not exists osiris_key (case_id text, headline integer, event text, by text, at text,
    primary key (case_id, headline, by));
create table if not exists osiris_headlines (headline integer primary key, first text, outlet text, title text,
    production_story integer);
create table if not exists osiris_runs (at text primary key, headlines integer, clusters integer, done integer);
create table if not exists osiris_clusters (at text, cluster integer, headline integer, seam_root integer,
    primary key (at, headline));
create table if not exists osiris_assign (arm text, headline integer, story integer, story_first text,
    primary key (arm, headline));
create table if not exists osiris_sort (case_id text, batch integer, answer text, primary key (case_id, batch));
create index if not exists osiris_clusters_at on osiris_clusters (at);
"""


def db() -> sqlite3.Connection:
    con = archive_db.connect()
    con.executescript(SCHEMA)
    return con


def site() -> sqlite3.Connection:
    return sqlite3.connect(f'file:{os.path.join(Config.data, "data.db")}?mode=ro', uri=True)


# ---- the answer key ----

def key():
    """The drafts (by 'claude') and any corrections (corrections/<case>.json, the same shape, by 'person') into the
    archive. A correction file needs only the headlines and events it changes; the rest stand as drafted. One with
    "approved" and no key is the person approving the draft as it stands (Nov 2: "It looks good to me")."""
    con = db()
    now = dt.now().isoformat(timespec='seconds')
    for name in sorted(os.listdir(os.path.join(NOTES, 'drafts'))):
        case = name[:-5]
        d = json.load(open(os.path.join(NOTES, 'drafts', name)))
        prod = json.load(open(os.path.join(NOTES, 'cases', f'{case}.production.json')))
        heads = json.load(open(os.path.join(NOTES, 'cases', f'{case}.json')))
        con.execute('insert or replace into osiris_cases values (?, ?, ?, ?)',
                    (case, d.get('story', ''), json.dumps(prod['sagas']), json.dumps(prod.get('candidates', []))))
        for h in heads:
            con.execute('insert or replace into osiris_headlines values (?, ?, ?, ?, ?)',
                        (h['h'], h['first'], h['outlet'], h['title'], prod['production'].get(str(h['h']))))
        for by, path in (('claude', os.path.join(NOTES, 'drafts', name)),
                         ('person', os.path.join(NOTES, 'corrections', name))):
            if not os.path.exists(path):
                continue
            x = json.load(open(path))
            if by == 'person' and x.get('approved') and not x.get('key'):  # approved as drafted: the draft, as theirs
                x = {**d, **x, 'key': d['key'], 'events': d['events']}
            for e in x.get('events', []):
                con.execute('insert or replace into osiris_events values (?, ?, ?, ?, ?, ?)',
                            (case, e['id'], e['name'], e.get('first', ''), e.get('note', ''), by))
            for h, ev in x.get('key', {}).items():
                con.execute('insert or replace into osiris_key values (?, ?, ?, ?, ?)', (case, int(h), ev, by, now))
        missing = {h['h'] for h in heads} - {int(h) for h in d['key']}
        print(f'{case}: {len(heads)} headlines, {len(d["events"])} events'
              + (f', {len(missing)} unkeyed' if missing else ''), flush=True)
    con.commit()


def answer_key(con) -> dict:
    """case -> {headline: event}, the person's correction over Claude's draft"""
    out = defaultdict(dict)
    for case, h, ev in con.execute("select case_id, headline, event from osiris_key order by by = 'person'"):
        out[case][h] = ev  # the person's rows come last and win
    return out


# ---- each run's clusters ----

def run_times() -> list[str]:
    with contextlib.closing(site()) as s:
        return [a for (a,) in s.execute("select distinct substr(at, 1, 19) from story_snapshot where at >= ? and "
                                        "at <= ? order by 1", (START, END))]


def live_at(s: sqlite3.Connection, at: dt) -> pd.DataFrame:
    """The headlines production clustered at `at`: on a front page then (first seen by it, last seen within its half
    hour), first seen in the last three days, news (NEWS_ONLY), US outlets and the exempted British ones, no
    aggregators, each (outlet, url, title) once"""
    from app.analysis.newsfilter import NEWS_THRESHOLD
    from app.site.page_headlines import AGGREGATORS
    from app.utils import Country
    rows = s.execute("""select h.id, coalesce(h.processed, h.title), ag.name, ar.url, ag._country
        from headline h join article ar on ar.id = h.article_id join agency ag on ag.id = ar.agency_id
        where h.first_accessed <= ? and h.last_accessed >= ? and h.first_accessed > ?
          and (h.news_score is null or h.news_score >= ?)
        order by h.first_accessed desc, h.position asc""",
                     (str(at), str(at - LIVE_SLACK), str(at - LOOKBACK), NEWS_THRESHOLD)).fetchall()
    df = pd.DataFrame(rows, columns=['headline_id', 'title', 'agency', 'url', 'country'])
    df = df.drop_duplicates(['agency', 'url', 'title'])
    us, gb = Country.us.value, Country.gb.value
    df = df[(df['country'] == us) | ((df['country'] == gb) & df['agency'].isin(Config.exempted_foreign_media))]
    return df[~df['agency'].isin(AGGREGATORS)].reset_index(drop=True)


def clusters():
    """Each run's clusters, as cluster_and_summarize makes them up to sync_stories: likeness, the two unlinks, the
    groups, the seam cut (Gemma confirms, from a copy of production's cache), one headline an outlet, six outlets"""
    from app.analysis import clustering as cl
    from app.analysis.pipelines import default_pipeline, prepare
    os.makedirs(WORK, exist_ok=True)
    seams_path = os.path.join(WORK, 'story_seams.json')
    if not os.path.exists(seams_path):
        shutil.copy(os.path.join(Config.cache, 'story_seams.json'), seams_path)
    seams = json.load(open(seams_path))
    vectors = os.path.join(WORK, 'vectors.sqlite')
    pipeline = [*default_pipeline, ' '.join]
    con = db()
    done = {a for (a,) in con.execute('select at from osiris_runs where done = 1')}
    times = [a for a in run_times() if a not in done]
    print(f'{len(times)} runs to cluster ({len(done)} done)', flush=True)
    with contextlib.closing(site()) as s:
        for n, at in enumerate(times):
            df = live_at(s, dt.fromisoformat(at))
            if len(df) < PER_STORY:
                con.execute('insert or replace into osiris_runs values (?, ?, 0, 1)', (at, len(df)))
                continue
            df['processed'] = df['title'].apply(lambda x: prepare(x, pipeline))
            texts = df['title'].tolist()
            v = cl.ollama_embed(texts, cache=vectors, keep_days=3650).astype(np.float64)
            sim = v @ v.T
            sim = cl.unlink_money_conflicts(sim, texts)
            sim = cl.unlink_place_conflicts(sim, texts)
            groups = cl.form_clusters(sim, PER_STORY, cl.STORY_THRESHOLDS[cl.STORY_MODEL])
            roots = []
            groups, _ = cl.split_seams(groups, df['processed'].tolist(), df['agency'].tolist(), PER_STORY, texts,
                                       confirm=lambda a, b: cl.two_events(a, b, seams), roots=roots)
            df = cl.label_clusters(df, groups)
            df['seam_root'] = df['cluster'].map(dict(enumerate(roots)))
            df = df[df['cluster'] != -1]
            df = df.drop_duplicates(subset=['cluster', 'agency'], keep='first')  # all live: the first, as production
            df = df.groupby('cluster').filter(lambda x: len(x) >= PER_STORY)
            con.executemany('insert or replace into osiris_clusters values (?, ?, ?, ?)',
                            [(at, int(c), int(h), int(r) if pd.notna(r) else None)
                             for c, h, r in zip(df['cluster'], df['headline_id'], df['seam_root'])])
            con.execute('insert or replace into osiris_runs values (?, ?, ?, 1)', (at, len(texts), df['cluster'].nunique()))
            con.commit()
            if n % 10 == 0:
                json.dump(seams, open(seams_path, 'w'))
                print(f'{at}: {len(texts)} live, {df["cluster"].nunique()} stories ({n + 1}/{len(times)})', flush=True)
    json.dump(seams, open(seams_path, 'w'))


# ---- the replay ----

class Clock:
    """stories.dt with now() set to the run being replayed"""
    at = None

    @classmethod
    def install(cls, module):
        real = module.dt if not hasattr(module.dt, 'replayed') else module.dt.replayed

        class Fake(real):
            replayed = real

            @classmethod
            def now(klass, tz=None):
                return tz.localize(cls.at) if tz is not None else cls.at
        module.dt = Fake


def replay_arm(arm: str, con, runs: list[str]):
    """One arm's walk: a fresh in-memory story database fed every run's clusters, the clock at each run"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.analysis.stories as st
    import app.models as models
    from app.models import Base, Headline, Story, StoryHeadline
    # A file, not memory: sync_stories opens other sessions inside its own (splits(), merges()), and on one shared
    # in-memory connection their closing rolls back its uncommitted stories
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, f'stories-{arm}.sqlite')
    if os.path.exists(path):
        os.remove(path)
    engine = create_engine(f'sqlite:///{path}', connect_args={'timeout': 60})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    st.Session = models.Session = session
    st.SqlLock = contextlib.nullcontext()
    returns = os.path.join(WORK, 'story_returns.json')
    if not os.path.exists(returns):
        shutil.copy(st.RETURNS, returns)
    st.RETURNS = returns
    st.CARRIED_SLACK = {'A': td(days=3650),  # the older-headline rule never fires: yesterday's code
                        'C': td(days=-3650),  # every held headline counts as older: it stays (a new story still takes)
                        'B': td(minutes=30)}[arm]
    Clock.install(st)
    meta = {}
    with contextlib.closing(site()) as s:
        for n, at in enumerate(runs):
            rows = con.execute('select cluster, headline, seam_root from osiris_clusters where at = ?', (at,)).fetchall()
            if not rows:
                continue
            ids = [h for _, h, _ in rows]
            new = [i for i in dict.fromkeys(ids) if i not in meta]
            for i in range(0, len(new), 500):
                chunk = new[i:i + 500]
                for r in s.execute(f"""select h.id, coalesce(h.processed, h.title), ag.name, h.first_accessed,
                        h.vader_compound, h.afinn, h.event_score from headline h join article ar on ar.id = h.article_id
                        join agency ag on ag.id = ar.agency_id where h.id in ({','.join('?' * len(chunk))})""", chunk):
                    meta[r[0]] = r[1:]
            with session() as m:
                for i in new:
                    first = dt.fromisoformat(meta[i][2][:26])
                    m.add(Headline(id=i, article_id=i, title=meta[i][0], first_accessed=first, last_accessed=first))
                m.commit()
            df = pd.DataFrame([{'cluster': c, 'headline_id': h, 'seam_root': r, 'title': meta[h][0],
                                'agency': meta[h][1], 'vader_compound': meta[h][3] or 0.0, 'afinn': meta[h][4] or 0.0,
                                'event_score': meta[h][5] or 0.0} for c, h, r in rows])
            Clock.at = dt.fromisoformat(at)
            stories = st.sync_stories(df)
            st.fold_twins(df, stories)
            if n % 50 == 0:
                print(f'{arm} {at} ({n + 1}/{len(runs)})', flush=True)
    with session() as m:
        firsts = dict(m.query(Story.id, Story.first_seen))
        out = [(arm, h, sid, str(firsts.get(sid))) for h, sid in m.query(StoryHeadline.headline_id,
                                                                         StoryHeadline.story_id)]
    con.execute('delete from osiris_assign where arm = ?', (arm,))
    con.executemany('insert into osiris_assign values (?, ?, ?, ?)', out)
    con.commit()


def replay():
    con = db()
    runs = [a for (a,) in con.execute('select at from osiris_runs where done = 1 order by at')]
    for arm in (sys.argv[2:] or ARMS):
        replay_arm(arm, con, runs)
        print(f'{arm}: done', flush=True)


# ---- arm E: sorted by event ----

SORT_PROMPT = """You are sorting news headlines from one running story into its events, in the order they appeared.

The running story: {story}

Events so far (id: name; a few of its headlines):
{events}

New headlines (number: headline):
{headlines}

For each new headline, say which event it reports. An event is a development: a new act, decision or event by someone
in the story, or the next stage of one. Reactions, commentary, new details and the same news told again belong to the
event they are about. If a headline reports a development not in the list, give it a new event id ("new1", "new2"...)
and name it; headlines reporting the same new development share its id. "background" is about the running story but no
one development; "other" is not this story at all."""

SORT_SCHEMA = {"type": "object", "properties": {
    "assign": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"}, "event": {"type": "string"}}, "required": ["n", "event"]}},
    "new_events": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "name": {"type": "string"}}, "required": ["id", "name"]}}},
    "required": ["assign", "new_events"]}


def sort():
    from app.analysis import llm
    con = db()
    cases = con.execute('select case_id, story from osiris_cases order by case_id').fetchall()
    for n, (case, story) in enumerate(cases, 1):
        heads = con.execute('select h.headline, h.title from osiris_headlines h join osiris_key k on k.headline = '
                            "h.headline and k.case_id = ? and k.by = 'claude' order by h.first, h.headline",
                            (case,)).fetchall()
        events, members, assign = {}, defaultdict(list), {}
        for b in range(0, len(heads), SORT_BATCH):
            batch = heads[b:b + SORT_BATCH]
            got = con.execute('select answer from osiris_sort where case_id = ? and batch = ?', (case, b)).fetchone()
            if got:
                answer = json.loads(got[0])
            else:
                shown = '\n'.join(f"{e}: {name}; " + ' | '.join(members[e][:1] + members[e][-2:])
                                  for e, name in events.items())
                answer = llm.complete_json(SORT_PROMPT.format(
                    story=story, events=shown or '(none yet)',
                    headlines='\n'.join(f'{i}: {t}' for i, (_, t) in enumerate(batch, 1))),
                    SORT_SCHEMA, max_tokens=2000, model=SORT_MODEL)
                if answer is None:
                    print(f'{case} batch {b}: no answer; left unsorted', flush=True)
                    continue
                con.execute('insert or replace into osiris_sort values (?, ?, ?)', (case, b, json.dumps(answer)))
                con.commit()
            names = {x['id']: x['name'] for x in answer.get('new_events', [])}
            fresh = {}
            for x in answer.get('assign', []):
                if not 1 <= x['n'] <= len(batch):
                    continue
                h, title = batch[x['n'] - 1]
                ev = x['event']
                if ev in ('background', 'other'):
                    assign[h] = ev
                    continue
                if ev not in events:  # a new event: numbered across the whole case
                    if ev not in fresh:
                        fresh[ev] = f'g{len(events) + 1}'
                        events[fresh[ev]] = names.get(ev, ev)
                    ev = fresh[ev]
                assign[h] = ev
                members[ev].append(title)
        # each event is a story of its own; background and other headlines each sit alone
        con.executemany('insert or replace into osiris_assign values (?, ?, ?, ?)',
                        [('E', h, int(hashlib.sha1(f'{case}|{ev if ev not in ("background", "other") else h}'.encode())
                                      .hexdigest()[:12], 16), None) for h, ev in assign.items()])
        con.commit()
        print(f'{case}: {len(events)} events from {len(heads)} headlines ({n}/{len(cases)})', flush=True)


# ---- the measures ----

def measures(key: dict, story_of: dict, firsts: dict) -> dict:
    """The paper's measures for one case: key {headline: event}, story_of {headline: story}, firsts {headline: first
    seen}. Headlines without a story count as stories of one."""
    keyed = {h: e for h, e in key.items() if e not in ('background', 'other')}
    if not keyed:
        return {}
    sid = {h: story_of.get(h, f'alone-{h}') for h in keyed}
    by_story, by_event = defaultdict(list), defaultdict(list)
    for h, e in keyed.items():
        by_story[sid[h]].append(h)
        by_event[e].append(h)
    p = float(np.mean([sum(keyed[x] == keyed[h] for x in by_story[sid[h]]) / len(by_story[sid[h]]) for h in keyed]))
    r = float(np.mean([sum(sid[x] == sid[h] for x in by_event[keyed[h]]) / len(by_event[keyed[h]]) for h in keyed]))
    big_events = [hs for hs in by_event.values() if len(hs) >= SPLIT_LEAST]
    split = sum(max(Counter(sid[h] for h in hs).values()) / len(hs) < SPLIT_SHARE for hs in big_events)
    main = {s: Counter(keyed[h] for h in hs).most_common(1)[0] for s, hs in by_story.items()}
    big_stories = {s: hs for s, hs in by_story.items() if len(hs) >= SPLIT_LEAST}
    mixed = sum(main[s][1] / len(hs) < SPLIT_SHARE for s, hs in big_stories.items())
    carried = sum(keyed[h] != main[sid[h]][0] for h in keyed)
    opening = [keyed[min(hs, key=lambda h: (firsts.get(h, ''), h))] == main[s][0] for s, hs in big_stories.items()]
    return {'p': p, 'r': r, 'f': 2 * p * r / (p + r) if p + r else 0.0, 'events': len(big_events), 'split': split,
            'stories': len(big_stories), 'mixed': mixed, 'carried': carried, 'keyed': len(keyed),
            'opening': (sum(opening), len(opening)),
            'intruders': sum(1 for h, e in key.items() if e == 'other' and h in story_of)}


def report():
    con = db()
    keys = answer_key(con)
    corrected = {c for (c,) in con.execute("select distinct case_id from osiris_key where by = 'person'")}
    firsts = dict(con.execute('select headline, first from osiris_headlines'))
    # production as stored: a candidate headline outside the case's sagas has no story in it (a story of its own)
    sagas = {c: set(json.loads(s)) for c, s in con.execute('select case_id, sagas from osiris_cases')}
    prod_saga = {}
    with contextlib.closing(site()) as s:
        for h, story, saga in s.execute('select sh.headline_id, sh.story_id, st.saga_id from story_headline sh '
                                        'join story st on st.id = sh.story_id'):
            prod_saga[h] = (story, saga)
    arms = {}
    for arm, h, sid in con.execute('select arm, headline, story from osiris_assign'):
        arms.setdefault(arm, {})[h] = sid
    lines = [f'S7 key: {len(keys)} cases, {sum(len(k) for k in keys.values())} headlines; corrected by the person: '
             f'{len(corrected)} of {len(keys)}' + ('' if len(corrected) == len(keys) else ' (scores provisional)')]
    table = {}
    for arm in ['P', *sorted(arms)]:
        rows = {}
        for case, k in keys.items():
            if arm == 'P':
                story_of = {h: prod_saga[h][0] for h in k if h in prod_saga and prod_saga[h][1] in sagas[case]}
            else:
                story_of = arms[arm]
            m = measures(k, story_of, firsts)
            if m:
                rows[case] = m
        table[arm] = rows
        tot = lambda f, rows=rows: sum(m[f] for m in rows.values())  # noqa: E731
        op = (sum(m['opening'][0] for m in rows.values()), sum(m['opening'][1] for m in rows.values()))
        lines.append(f"S7 arm {arm}: precision {np.mean([m['p'] for m in rows.values()]):.2f}, recall "
                     f"{np.mean([m['r'] for m in rows.values()]):.2f}, F {np.mean([m['f'] for m in rows.values()]):.2f} "
                     f"(cases averaged); split events {tot('split')} of {tot('events')}; mixed stories {tot('mixed')} "
                     f"of {tot('stories')}; carried headlines {tot('carried')} of {tot('keyed')}; opening headline "
                     f"right {op[0]} of {op[1]}" + (f"; intruders {tot('intruders')}" if arm == 'P' else ''))
    for case in sorted(keys):
        lines.append(f'S7   {case}: ' + ', '.join(
            f"{arm} F {table[arm][case]['f']:.2f} (p {table[arm][case]['p']:.2f} r {table[arm][case]['r']:.2f})"
            for arm in table if case in table[arm])
            + f" · P intruders {table['P'][case]['intruders']}" if case in table['P'] else '')
    if 'A' in table:
        close = sum(abs(table['A'][c]['f'] - table['P'][c]['f']) <= 0.05 for c in table['P'] if c in table['A'])
        lines.append(f'S7 fidelity: A within 0.05 of P on {close} of {len(table["P"])} cases')
    if 'E' in table:
        calls = con.execute('select count(*) from osiris_sort').fetchone()[0]
        lines.append(f'S7 cost of E: {calls} calls for {sum(len(k) for k in keys.values())} headlines')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


if __name__ == '__main__':
    {'key': key, 'clusters': clusters, 'replay': replay, 'sort': sort, 'report': report}[
        sys.argv[1] if len(sys.argv) > 1 else 'report']()
