"""S10 The Prodigal Son: does the saga judge let a running story's parts come home? (Nov 4, the person, of saga 125
and the Michigan saga: "Please just work on sagas and story grouping we need to fix them both".) The judge
(sagas.JUDGE_PROMPT, with JUDGE_PROMPT_B as the second wording; both must say yes) called the midterms' closing
speech "a specific campaign event" apart from the midterms, as its own wording tells it to ("separate events
involving the same person ... a general overview beside one case in it"). A reworded judge is tried against the
current one on pairs of production stories labeled from Osiris's answer key (S7).

    s10_prodigal.py pairs    the labeled pairs, from the key: one running story, or two
    s10_prodigal.py judge    both wordings on every pair (Gemma 4 26B under the lease; cached per arm)
    s10_prodigal.py report   found and wrongly joined, per arm

Data in ~/maudlin-data/archives/archives.sqlite (prodigal_*). The paper is ~/maudlin-data/papers/the-prodigal-son.md."""
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s7_osiris as o7  # noqa: E402

WORK = os.path.join(harness.EXP, 's10_prodigal')
LEAST = 4  # keyed headlines a story needs to be judged
SAME_CASE = 0.6  # a story is a case's when this share of its keyed headlines are the case's events or background
PER_CASE = 15  # one-story pairs a case, at most
CROSS = 150  # pairs of stories from two different cases (two running stories), the most alike

NEW_PROMPT = """Two groups of news headlines. Are they parts of one ongoing news story: the same case, incident, \
event, investigation, negotiation, election or campaign, followed as it develops? The groups may tell it from \
different angles or focus on different parts of it; that's still one story. So are its consequences and reactions \
(an official resigns over a failure; a board or faculty votes over how the case was handled) and its later \
developments. An election, a race or a campaign is one running story: its rallies and speeches, endorsements and \
defections, ads, debates, polls, the vote, the results and the concession are all parts of it. Different stories: \
separate cases at the same court, separate crimes by people of the same nationality, separate races in different \
places (two states' Senate races), and separate events involving the same person or place that belong to no one \
running story (a rally and an unrelated executive order signed the same week). A different focus, speaker or angle \
is never by itself a reason to call them separate.

Group 1:
{a}

Group 2:
{b}

reason: one sentence
verdict: "one running story" or "separate stories\""""

NEW_PROMPT_B = """Group 1:
{a}

Group 2:
{b}

Would a news editor file these two groups under one running story: the same case, incident, event, investigation, \
negotiation, election or campaign, whether the groups report the same development of it or different ones, \
different angles on it, or its consequences and the reactions to it? An election or a race is one running story: \
its rallies, speeches, endorsements, ads, debates, polls, the vote and the results all belong to it. Answer no if \
they are two separate cases or events, even when they share a country, a court, a kind of crime or a person, if they \
are two different races, or if one is a general overview and the other a single case in it. Focusing on different \
people, aspects or angles of one event is not a reason to answer no.

reason: one sentence
verdict: "one running story" or "separate stories\""""

SCHEMA = """
create table if not exists prodigal_pairs (a integer, b integer, same integer, kind text, case_a text, case_b text,
    titles_a text, titles_b text, primary key (a, b));
create table if not exists prodigal_verdicts (arm text, a integer, b integer, same integer, reason text,
    primary key (arm, a, b));
"""


def db() -> sqlite3.Connection:
    con = o7.db()
    con.executescript(SCHEMA)
    return con


def pairs():
    """Production stories in the key's cases, each the case's (its events or background) or not ('other'); pairs in
    one case both the case's are one running story; a case's story beside an 'other' one, or the main stories of two
    cases sharing a name (two Senate races), are two"""
    con = db()
    keys = o7.answer_key(con)
    titles = dict(con.execute('select headline, title from osiris_headlines'))
    prod = dict(con.execute('select headline, production_story from osiris_headlines'))
    stories = defaultdict(lambda: defaultdict(list))  # case -> story -> [(headline, event)]
    for case, k in keys.items():
        for h, ev in k.items():
            if prod.get(h):
                stories[case][prod[h]].append((h, ev))
    members, others = defaultdict(list), defaultdict(list)
    for case, by in stories.items():
        for sid, hs in by.items():
            if len(hs) < LEAST:
                continue
            mine = sum(ev != 'other' for _, ev in hs) / len(hs)
            if mine >= SAME_CASE:
                members[case].append(sid)
            elif mine <= 1 - SAME_CASE:
                others[case].append(sid)
    story_titles = defaultdict(list)
    for case, by in stories.items():
        for sid, hs in by.items():
            story_titles[sid] += [titles[h] for h, _ in hs]
    import app.analysis.sagas as sg
    vec = {}
    for sid, ts in story_titles.items():
        v = sg.embed(ts)
        v = v / np.linalg.norm(v, axis=1, keepdims=True)
        c = v.mean(axis=0)
        vec[sid] = c / np.linalg.norm(c)
    rows = []
    for case, ss in members.items():  # at most PER_CASE pairs a case, the least alike first (the hard ones)
        inside = sorted(combinations(sorted(set(ss)), 2), key=lambda p: float(vec[p[0]] @ vec[p[1]]))
        for a, b in inside[:PER_CASE]:
            rows.append((a, b, 1, 'one story', case, case))
    # Stories of two different cases are two running stories: the most alike such pairs (the hard ones)
    cross = sorted(((float(vec[a] @ vec[b]), min(a, b), max(a, b), ca, cb)
                    for ca, cb in combinations(sorted(members), 2) for a in members[ca] for b in members[cb]),
                   reverse=True)
    for _, a, b, ca, cb in cross[:CROSS]:
        rows.append((a, b, 0, 'other case', ca, cb))
        for a in ss:
            for b in others.get(case, []):
                rows.append((min(a, b), max(a, b), 0, 'beside it', case, case))
    biggest = {c: max(ss, key=lambda s: len(stories[c][s])) for c, ss in members.items() if ss}
    namesake = [('michigan-senate', 'texas-senate'), ('michigan-senate', 'alaska-senate'), ('texas-senate', 'alaska-senate'),
                ('trump-michigan-rally', 'rally-format'), ('comey', 'fbi-officials'), ('omar-investigation', 'ice-houston')]
    for ca, cb in namesake:
        if ca in biggest and cb in biggest:
            a, b = sorted((biggest[ca], biggest[cb]))
            rows.append((a, b, 0, 'namesake', ca, cb))
    rows = list({(a, b): (a, b, s, k, ca, cb) for a, b, s, k, ca, cb in rows}.values())
    con.execute('delete from prodigal_pairs')
    con.executemany('insert or replace into prodigal_pairs values (?, ?, ?, ?, ?, ?, ?, ?)',
                    [(a, b, s, k, ca, cb, json.dumps(story_titles[a]), json.dumps(story_titles[b]))
                     for a, b, s, k, ca, cb in rows])
    con.commit()
    print(f'{len(rows)} pairs: {dict(Counter((k, s) for _, _, s, k, _, _ in rows))}', flush=True)


def judge():
    import app.analysis.sagas as sg
    os.makedirs(WORK, exist_ok=True)
    con = db()
    rows = con.execute('select a, b, titles_a, titles_b from prodigal_pairs').fetchall()
    old = (sg.JUDGE_PROMPT, sg.JUDGE_PROMPT_B)
    arms = {'current': old, 'election': (NEW_PROMPT, NEW_PROMPT_B)}
    done = {(arm, a, b) for arm, a, b in con.execute('select arm, a, b from prodigal_verdicts')}
    n = 0
    for arm, (pa, pb) in arms.items():
        sg.JUDGE_PROMPT, sg.JUDGE_PROMPT_B = pa, pb
        sg.JUDGMENTS = os.path.join(WORK, f'judgments-{arm}.json')
        for a, b, ta, tb in rows:
            if (arm, a, b) in done:
                continue
            ta, tb = json.loads(ta), json.loads(tb)
            va, vb = sg.embed(ta), sg.embed(tb)
            va = va / np.linalg.norm(va, axis=1, keepdims=True)
            vb = vb / np.linalg.norm(vb, axis=1, keepdims=True)
            same = sg.saga_verdict(sg.central(ta, va), sg.central(tb, vb))
            if same is None:
                continue
            con.execute('insert or replace into prodigal_verdicts values (?, ?, ?, ?, ?)', (arm, a, b, int(same), ''))
            con.commit()
            n += 1
            if n % 20 == 0:
                print(f'{arm} {n}/{2 * len(rows)}', flush=True)
    sg.JUDGE_PROMPT, sg.JUDGE_PROMPT_B = old


def report():
    con = db()
    truth = {(a, b): (s, k) for a, b, s, k in con.execute('select a, b, same, kind from prodigal_pairs')}
    lines = [f'S10 pairs: {len(truth)}; one story {sum(s for s, _ in truth.values())}; '
             f'{dict(Counter(k for _, k in truth.values()))}']
    for arm in ('current', 'election'):
        got = {(a, b): s for a, b, s in con.execute('select a, b, same from prodigal_verdicts where arm = ?', (arm,))}
        pos = [p for p, (s, _) in truth.items() if s and p in got]
        neg = [p for p, (s, _) in truth.items() if not s and p in got]
        found = sum(got[p] for p in pos)
        wrong = sum(got[p] for p in neg)
        by = {k: (sum(got[p] for p, (s, kk) in truth.items() if kk == k and p in got),
                  sum(1 for p, (s, kk) in truth.items() if kk == k and p in got)) for k in ('beside it', 'namesake', 'other case')}
        lines.append(f'S10 {arm}: found {found} of {len(pos)} ({found / max(1, len(pos)):.0%}); wrongly joined {wrong} of '
                     f'{len(neg)} (' + ', '.join(f'{k} {by[k][0]} of {by[k][1]}' for k in by) + ')')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


if __name__ == '__main__':
    {'pairs': pairs, 'judge': judge, 'report': report}[sys.argv[1] if len(sys.argv) > 1 else 'report']()
