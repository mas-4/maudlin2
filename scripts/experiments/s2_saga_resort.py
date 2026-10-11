"""S2 sorting a saga's headlines into its parts again (Oct 11, the person, on saga-30: the diesel deal's part held two
days of Trump calling for Zelensky to be replaced, while that news's own part showed one hour on the front pages, "it
makes it look like an old headline is still the main headline and the new headline is dead"; and "once we've
identified x number of parts within a saga we can use k means clustering").

Each hour's clusters continue the story holding most of their headlines, so a new event joins the old story while a
few of its headlines are on front pages. Here, for each live saga, every headline it holds is sorted again:
    1. k-means on the headlines' vectors (mxbai, the stories' own; cached), k a few more than the saga's parts: by
       meaning the two events sit close (0.92), but k-means only asks which group is closer, and on saga-30 at k=5 it
       put 75 of 79 diesel-deal headlines in one group and 75 of 78 Zelensky ones in two others (a keyword key)
    2. groups under MIN_GROUP headlines join their nearest
    3. in order of when each broke, a group Gemma 26B calls the same event updated (S1's definition: new details,
       condition, reactions and commentary are updates; someone's new action, statement or decision, or a new outcome,
       is a new event) as an earlier group joins it. S1: Gemma agrees with the answer key on 78%, Nimble 60%. (The
       first run used the stories' return judge, stories.same_event: it split one event by angle, the FlyDubai hero
       pilot's interview and the co-pilot's Oman ban each a part of their own; the second asked each earlier group in
       turn, and false merges added up: Pike's ventilator news into the prison chief's resignation. Now only the
       nearest earlier group is asked)
    4. a group the saga judge (sagas.saga_verdict, both wordings) says isn't part of the running story is flagged
       (the first run made Trump's Columbus Day remarks a part of the diesel deal's saga; the second removed such
       groups and took real parts out too, so the person decides)
    5. each part keeps the group holding most of its own first headlines, so it stays the event it began as (the first
       run gave the FlyDubai attack's part the later investigation news, and the attack itself a new part); a larger
       part wins a contested group; other groups are new parts
A dry run: prints each live saga's parts now and as sorted again, and keeps them in EXP for the person to see.

    s2_saga_resort.py [saga id ...]"""
import json
import os
import sqlite3
import sys
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s1_story_splits as s1  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import sagas as sg  # noqa: E402
from app.analysis import stories as st  # noqa: E402
from app.analysis.clustering import ollama_embed  # noqa: E402
from app.utils import Config  # noqa: E402

OUT = os.path.join(harness.EXP, 's2_saga_resort.json')
st.RETURNS = os.path.join(harness.EXP, 's2_same_event.json')  # the judges' verdicts kept here, not in production's
sg.JUDGMENTS = os.path.join(harness.EXP, 's2_saga_judgments.json')
UPDATES = os.path.join(harness.EXP, 's2_updates.json')  # step 3's verdicts, by the headlines shown
FIRST = 5  # a part's first headlines, which say what event it began as
LIVE_DAYS = 3  # sagas with a part on front pages this recently
EXTRA = 2  # k-means groups beyond the saga's parts
MIN_GROUP = 5  # headlines: a smaller group joins its nearest
SHOWN = 5  # central headlines shown to the judge per group


def sagas(ids: list[int] | None = None) -> dict[int, dict]:
    """{saga: {name, parts: {story: label}, headlines: [{story, title, text, seen}]}}, one row per distinct title"""
    db = sqlite3.connect(f'file:{os.path.join(Config.data, "data.db")}?mode=ro', uri=True)
    if not ids:
        ids = [i for (i,) in db.execute("select distinct saga_id from story where saga_id is not null and "
                                         f"last_seen > datetime('now', '-{LIVE_DAYS} days')")]
    out = {}
    for sid in ids:
        name = db.execute('select name from saga where id = ?', (sid,)).fetchone()[0]
        parts = dict(db.execute('select id, label from story where saga_id = ? order by first_seen', (sid,)))
        rows = db.execute('''select sh.story_id, h.title, h.processed, h.first_accessed from story_headline sh
                             join story s on s.id = sh.story_id join headline h on h.id = sh.headline_id
                             where s.saga_id = ? and h.processed is not null order by h.first_accessed''', (sid,))
        seen, hs = set(), []
        for story, title, text, at in rows:
            t = ' '.join(title.split())
            if t not in seen:
                seen.add(t)
                hs.append({'story': story, 'title': t, 'text': text, 'seen': at})
        out[sid] = {'name': name, 'parts': parts, 'headlines': hs}
    return out


def central(idx: list[int], X: np.ndarray) -> list[int]:
    c = X[idx].mean(0)
    return [idx[i] for i in np.argsort(-(X[idx] @ c))[:SHOWN]]


def is_update(earlier: list[str], later: list[str], day: str) -> bool | None:
    """Gemma's call: the later group reports the earlier one's event updated, not a new event (S1's prompt)"""
    import hashlib
    key = hashlib.sha1(json.dumps([earlier, later]).encode()).hexdigest()
    cache = json.load(open(UPDATES)) if os.path.exists(UPDATES) else {}
    if key not in cache:
        a = llm.complete_json(s1.PROMPT.format(before=s1.block(earlier), day=day, new=s1.block(later),
                                               definition=s1.DEFINITION), s1.SCHEMA, max_tokens=500, model=st.RETURN_MODEL)
        if not a:
            return None
        cache[key] = {**a, 'earlier': earlier, 'later': later}
        json.dump(cache, open(UPDATES, 'w'))
    return not cache[key]['new']


def resort(saga: dict) -> list[dict]:
    """The saga's headlines in groups: [{headlines: [i], story: id or None, leaves: bool}], in order of when each
    broke"""
    hs = saga['headlines']
    X = ollama_embed([h['text'] for h in hs])
    k = min(len(saga['parts']) + EXTRA, max(1, len(hs) // MIN_GROUP))
    labels = KMeans(k, n_init=20, random_state=0).fit_predict(X) if k > 1 else np.zeros(len(hs), int)
    groups = [list(np.flatnonzero(labels == g)) for g in range(k)]
    # small groups into their nearest
    while len(groups) > 1 and min(len(g) for g in groups) < MIN_GROUP:
        small = min(range(len(groups)), key=lambda i: len(groups[i]))
        g = groups.pop(small)
        c = X[g].mean(0)
        near = max(range(len(groups)), key=lambda i: float(X[groups[i]].mean(0) @ c))
        groups[near] += g
    groups.sort(key=np.median)  # rows are in order of first sighting
    merged = []
    for g in groups:  # only the nearest earlier group is asked (asking each in turn compounded false merges: run 2)
        day = hs[int(np.median(g))]['seen'][:10]
        c = X[g].mean(0)
        m = max(merged, key=lambda m: float(X[m].mean(0) @ c), default=None)
        if m is not None and is_update([hs[i]['title'] for i in central(m, X)], [hs[i]['title'] for i in central(g, X)], day):
            m += g
        else:
            merged.append(list(g))
    # a group the saga judge says isn't part of the running story is only flagged (run 2 let it remove groups: it took
    # out the Cornell defence's motion to remove the special prosecutor, and both halves of the Oct 7 saga)
    leaves = set()
    if len(merged) > 1:
        for n, g in enumerate(merged):
            rest = [i for j, m in enumerate(merged) if j != n for i in m]
            if sg.saga_verdict([hs[i]['title'] for i in central(g, X)],
                               [hs[i]['title'] for i in central(rest, X)]) is False:
                leaves.add(n)
    # each part keeps the group holding most of its first headlines; the larger part wins a contested group
    group_of = {i: n for n, g in enumerate(merged) for i in g}
    rows_of = {}
    for i, h in enumerate(hs):
        rows_of.setdefault(h['story'], []).append(i)
    story_at = {}
    for story, rows in sorted(rows_of.items(), key=lambda kv: -len(kv[1])):
        votes = Counter(group_of[i] for i in rows[:FIRST])
        for n, _ in votes.most_common():
            if n not in story_at:
                story_at[n] = story
                break
    out = [{'headlines': sorted(int(i) for i in g), 'story': story_at.get(n), 'leaves': False, 'doubt': n in leaves}
           for n, g in enumerate(merged)]
    out.sort(key=lambda o: hs[o['headlines'][0]]['seen'])
    return out


def show(sid: int, saga: dict, groups: list[dict]):
    hs = saga['headlines']
    now = Counter(h['story'] for h in hs)
    lines = [f"\n=== saga-{sid} {saga['name']}: {len(hs)} headlines, {len(saga['parts'])} parts now, {len(groups)} sorted again"]
    lines.append('  now:')
    for story, label in saga['parts'].items():
        lines.append(f"    {story:>4} {now[story]:>4}  {label}")
    lines.append('  sorted again:')
    for g in groups:
        idx = g['headlines']
        frm = Counter(hs[i]['story'] for i in idx)
        span = f"{hs[idx[0]]['seen'][5:13]} to {hs[idx[-1]]['seen'][5:13]}"
        name = ('(the saga judge doubts it belongs) ' if g.get('doubt') else '') + ('LEAVES THE SAGA' if g['leaves'] else saga['parts'].get(g['story'], 'NEW PART') if g['story'] else 'NEW PART')
        lines.append(f"    {g['story'] or ('out' if g['leaves'] else 'new'):>4} {len(idx):>4}  {span}  (from {dict(frm)})  "
                     f"{'' if g['leaves'] else 'was: '}{name}")
        step = max(1, len(idx) // 4)
        for i in idx[::step][:4]:
            lines.append(f"            - {hs[i]['title'][:110]}")
    kept = {g['story'] for g in groups}
    gone = [f"{story} ({saga['parts'][story][:50]})" for story in saga['parts'] if story not in kept and now[story]]
    if gone:
        lines.append(f"  parts left with no group of their own (their headlines all move): {', '.join(gone)}")
    print('\n'.join(lines), flush=True)


def main():
    ids = [int(a) for a in sys.argv[1:]] or None
    found = sagas(ids)
    saved = {}
    for sid, saga in sorted(found.items(), key=lambda kv: -len(kv[1]['headlines'])):
        groups = resort(saga)
        show(sid, saga, groups)
        saved[sid] = {'name': saga['name'], 'parts': saga['parts'],
                      'groups': [{'story': g['story'], 'leaves': g['leaves'], 'titles': [saga['headlines'][i]['title'] for i in g['headlines']],
                                  'from': dict(Counter(saga['headlines'][i]['story'] for i in g['headlines']))}
                                 for g in groups]}
        json.dump(saved, open(OUT, 'w'), indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
