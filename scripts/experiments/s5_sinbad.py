"""S5 Sinbad: a long story split at each new development (Oct 15, the person). A live story is kept across runs by the
headlines it shares with each hour's cluster, and retitled from its newest headlines once its title is RELABEL_AGE
old: so a long-running cluster becomes one story that takes in every new development under a moving title (the Fort
Hood shooter's story, 123: ten days, 368 headlines, from the firing squad to the livestream's cancellation). The
switched-off production path (stories.SPLIT_DEVELOPMENTS) asks the model, when a titled story is due a new title,
whether the headlines since the last title report a new development or the same event told again, and splits at a
new one. Due: RELABEL_AGE old with headlines since, or its outlets doubled (a dry count, Oct 15: the livestream's
cancellation took Fort Hood from 6 outlets to 35 in an hour, and the plan to make it public came the same way; asked
only when stale, both pass as a coverage retitle unasked).

This replays that rule over every story that lived 36 hours or more, as the hourly runs saw it: the runs it was on the
front pages (its snapshots; before snapshots began, the hours its headlines came in), a title written when it began,
written again when its outlets doubled or when it was RELABEL_AGE old with headlines since, and at each new title
the question, put with production's own prompt (stories.SPLIT_PROMPT) and function (stories.same_event). A split
starts a new part from the headlines since the last title; the walk goes on in that part. Two arms:

    last    the earlier side is the 5 newest headlines up to the last title (what the title was written from), as
            production asks
    first   the earlier side is the part's first 5 headlines (its founding news): does drift add up unseen?

    s5_sinbad.py replay   gather the long stories (frozen in the state), walk both arms, asking where needed (Gemma
                          4 26B, saved every EVERY answers; resumes from the saved verdicts)
    s5_sinbad.py report   the measures, the known cases (Fort Hood, Christa Pike) and the blind set for the person

The paper is ~/maudlin-data/papers/sinbad.md."""
import hashlib
import json
import os
import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime as dt, timedelta as td

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import stories as st  # noqa: E402
from app.utils import Config  # noqa: E402

OUT = os.path.join(harness.EXP, 's5_sinbad.json')
LONG = td(hours=36)  # stories that lived this long are replayed
STEP = st.RELABEL_AGE  # 12 hours: a title this old, with headlines since, is due again
SHOWN = 5  # headlines a side, as same_event shows
LEAST = st.SPLIT_LEAST
GROWTH = st.RELABEL_GROWTH
ARMS = ('last', 'first')
EVERY = 10  # answers between saves
CAP = st.MAX_SPLIT_CHECKS
BLIND_SPLITS, BLIND_CONTROLS = 20, 10
KNOWN_SAGAS = {5: 'Christa Pike', 33: 'Fort Hood'}  # the person's known cases: left out of the blind set
# The known cases' developments, written Oct 15 before the run (the paper), each from its first headline in the story.
# 'must': the person sees a separate development there; 'may': a development a part may begin at, not counted against
KNOWN = {
    123: [('must', 'the execution to be public, then livestreamed', '2026-10-08 20:00'),
          ('must', 'Trump cancels the livestream', '2026-10-15 15:00'),
          ('may', 'the execution date set for Dec. 3', '2026-10-07 00:00'),
          ('may', 'Trump says he will make the decision', '2026-10-11 00:00'),
          ('may', 'Trump has doubts', '2026-10-12 12:02')],
    2: [('must', 'conscious and speaking', '2026-10-06 21:00'),
        ('must', 'discharged from hospital, back in prison', '2026-10-10 16:00'),
        ('must', 'the 911 calls', '2026-10-12 22:02'),
        ('may', 'the prisons chief resigns', '2026-10-03 16:00'),
        ('may', 'her sentence could be overturned', '2026-10-05 11:10'),
        ('may', 'a judge orders the evidence kept', '2026-10-07 18:00'),
        ('may', 'walking', '2026-10-08 08:00'),
        ('may', "another inmate's date pushed back", '2026-10-14 02:02')],
}
NEAR_BEFORE, NEAR_AFTER = td(hours=13), td(hours=24)  # a part beginning this near a development's start caught it


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'), indent=1)
    os.replace(OUT + '.tmp', OUT)


def t(iso: str) -> dt:
    return dt.fromisoformat(iso)


# ---------- the long stories ----------
def gather() -> dict:
    """Every story that lived LONG or more, as the stories table has it now: {id: {label, saga, first, last,
    headlines: [[id, first seen, title]] oldest first, snaps: [[at, outlets]]}}, and when snapshots began"""
    con = sqlite3.connect(f'file:{Config.db_file_path}?mode=ro', uri=True)
    rows = con.execute('select id, label, saga_id, first_seen, last_seen from story').fetchall()
    out = {}
    for sid, label, saga, first, last in rows:
        if t(last) - t(first) < LONG:
            continue
        heads = con.execute('select h.id, h.first_accessed, h.title from story_headline sh join headline h on '
                            'h.id = sh.headline_id where sh.story_id = ? order by h.first_accessed', (sid,)).fetchall()
        snaps = con.execute('select at, outlets from story_snapshot where story_id = ? order by at', (sid,)).fetchall()
        out[str(sid)] = {'label': label, 'saga': saga, 'first': first, 'last': last,
                         'headlines': [[h, a, ' '.join((x or '').split())] for h, a, x in heads],
                         'snaps': [[a, n] for a, n in snaps]}
    parts = dict(con.execute('select saga_id, count(*) from story where saga_id is not null group by saga_id').fetchall())
    start = con.execute('select min(at) from story_snapshot').fetchone()[0]
    return {'stories': out, 'saga_parts': {str(k): v for k, v in parts.items()}, 'snap_start': start,
            'total': len(rows), 'at': dt.now().isoformat(timespec='seconds')}


def runs(story: dict, snap_start: str) -> list[tuple[dt, int | None]]:
    """The hourly runs the story was on the front pages, with its outlets then (None before snapshots began)"""
    start = t(snap_start)
    out = {}
    for _, at, _ in story['headlines']:  # before snapshots: the run each headline came in
        when = t(at)
        if when < start:
            out.setdefault(when.replace(minute=59, second=59, microsecond=0), None)
    for at, n in story['snaps']:
        out[t(at)] = n
    return sorted(out.items())


def shown(titles: list[str]) -> list[str]:
    """The headlines same_event shows: the first SHOWN distinct"""
    return list(dict.fromkeys(x.strip() for x in titles))[:SHOWN]


def walk(arm: str, story: dict, snap_start: str, ask) -> list[dict]:
    """Every question production would have put to this story: a check per stale title, with ask(check) -> True
    (the same event), False (a new development: split) or None (no answer: no split)"""
    heads = [(t(a), x) for _, a, x in story['headlines']]
    checks = []
    label = labeled_with = None
    part_start = None  # the part's headlines are those first seen after this (None: from the story's start)
    for when, outlets in runs(story, snap_start):
        if label is None:  # the story's first title
            label, labeled_with = when, outlets
            continue
        part = [(a, x) for a, x in heads if part_start is None or a > part_start]
        new = [(a, x) for a, x in part if label < a <= when]
        if not new:
            continue
        grown = bool(outlets and labeled_with and outlets >= GROWTH * labeled_with)
        stale = when - label >= STEP
        if not (stale or grown):  # no new title due
            continue
        earlier = [(a, x) for a, x in part if a <= label]
        if len(new) >= LEAST and len(earlier) >= LEAST:
            side = [x for _, x in sorted(earlier, reverse=True)] if arm == 'last' else [x for _, x in earlier]
            check = {'at': when.isoformat(), 'due': 'both' if stale and grown else 'stale' if stale else 'grown', 'since': label.isoformat(), 'part_start': part_start.isoformat()
                     if part_start else None, 'n_new': len(new), 'n_earlier': len(earlier),
                     'a': shown(side), 'b': shown([x for _, x in sorted(new, reverse=True)])}
            check['same'] = ask(check)
            checks.append(check)
            if check['same'] is False:
                part_start = label  # the headlines since the last title go on as a new part
        label, labeled_with = when, outlets
    return checks


def key_of(arm: str, sid: str, check: dict) -> str:
    return f"{arm}|{sid}|{check['since']}|{check['at']}"


def reason_of(a: list[str], b: list[str]) -> str:
    """The model's reason, from same_event's own cache (by the headlines shown)"""
    k = hashlib.sha1(json.dumps([st.SPLIT_PROMPT, a, b]).encode()).hexdigest()
    return (st.read_json(st.RETURNS, {}).get(k) or {}).get('reason', '')


# ---------- the replay ----------
def replay():
    state = saved()
    if 'stories' not in state:
        state.update(gather())
        save(state)
        print(f"stories: {len(state['stories'])} of {state['total']} lived {LONG.total_seconds() / 3600:.0f} hours or "
              f"more", flush=True)
    verdicts = state.setdefault('verdicts', {})  # check key -> {'same', 'reason'}
    asked = 0
    for arm in ARMS:
        walks = state.setdefault('walks', {}).setdefault(arm, {})
        todo = sorted(state['stories'], key=int)
        for n, sid in enumerate(todo, 1):
            story = state['stories'][sid]

            def ask(check, arm=arm, sid=sid):
                nonlocal asked
                k = key_of(arm, sid, check)
                if k not in verdicts:
                    same = st.same_event(check['a'], check['b'], prompt=st.SPLIT_PROMPT)
                    if same is None:
                        return None  # not kept: asked again on a later try
                    verdicts[k] = {'same': same, 'reason': reason_of(check['a'], check['b'])}
                    asked += 1
                    if asked % EVERY == 0:
                        save(state)
                return verdicts[k]['same']
            walks[sid] = walk(arm, story, state['snap_start'], ask)
            if n % 10 == 0 or n == len(todo):
                save(state)
                checks = sum(len(w) for w in walks.values())
                splits = sum(c['same'] is False for w in walks.values() for c in w)
                print(f'replay {arm}: {n}/{len(todo)} stories, {checks} questions, {splits} splits '
                      f'({asked} asked this try)', flush=True)
    missing = sum(c['same'] is None for w in state['walks'].values() for ws in w.values() for c in ws)
    save(state)
    if missing:
        sys.exit(f'replay: {missing} questions without an answer; Ollama down? the next try asks them again')


# ---------- the report ----------
def parts_of(story: dict, checks: list[dict]) -> list[dict]:
    """The parts the story would have been: each with its first headline time and its first headlines"""
    bounds = [None] + [t(c['since']) for c in checks if c['same'] is False]
    heads = [(t(a), x) for _, a, x in story['headlines']]
    out = []
    for i, b in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else None
        inside = [(a, x) for a, x in heads if (b is None or a > b) and (end is None or a <= end)]
        if inside:
            out.append({'from': inside[0][0].isoformat(), 'to': inside[-1][0].isoformat(), 'headlines': len(inside),
                        'first': [x for _, x in inside[:3]]})
    return out


def known_case(sid: str, story: dict, checks: list[dict]) -> tuple[list[str], dict]:
    """Each listed development: its start, and whether a part began near it; and the splits near none of them"""
    begins = [t(c['since']) for c in checks if c['same'] is False]
    lines, near_any = [], set()
    tally = Counter()
    for kind, what, start in KNOWN[int(sid)]:
        hit = t(start)
        near = [b for b in begins if hit - NEAR_BEFORE <= b <= hit + NEAR_AFTER]
        near_any |= set(near)
        tally[(kind, bool(near))] += 1
        lines.append(f"    {kind} {what} (from {hit:%b %d %H:%M}): {'a part begins ' + near[0].strftime('%b %d %H:%M') if near else 'no part'}")
    stray = [b for b in begins if b not in near_any]
    lines.append(f"    splits near none of these: {len(stray)}" + (' (' + ', '.join(f'{b:%b %d %H:%M}' for b in stray) + ')'
                                                                 if stray else ''))
    return lines, {'must caught': tally[('must', True)], 'must': tally[('must', True)] + tally[('must', False)],
                   'stray': len(stray), 'parts': len(begins) + 1}


def blind_set(state: dict, seed: int = 15) -> list[dict]:
    """BLIND_SPLITS of the production arm's splits and BLIND_CONTROLS of its 'same' answers, from stories outside the
    known sagas, mixed; drawn once"""
    rnd = random.Random(seed)
    pool = {True: [], False: []}
    for sid, checks in state['walks']['last'].items():
        if state['stories'][sid]['saga'] in KNOWN_SAGAS:
            continue
        for c in checks:
            if c['same'] is not None:
                pool[c['same']].append(key_of('last', sid, c))
    picked = rnd.sample(sorted(pool[False]), min(BLIND_SPLITS, len(pool[False]))) + \
        rnd.sample(sorted(pool[True]), min(BLIND_CONTROLS, len(pool[True])))
    rnd.shuffle(picked)
    return [{'key': k, 'n': n} for n, k in enumerate(picked, 1)]


def find(state: dict, key: str) -> tuple[str, dict] | None:
    arm, sid, since, at = key.split('|')
    for c in state['walks'][arm].get(sid, []):
        if c['since'] == since and c['at'] == at:
            return sid, c
    return None


def report():
    state = saved()
    lines = []
    S = state['stories']
    for arm in ARMS:
        walks = state['walks'][arm]
        checks = [c for w in walks.values() for c in w]
        nsplit = {sid: sum(c['same'] is False for c in w) for sid, w in walks.items()}
        parts = Counter(min(n + 1, 5) for n in nsplit.values())
        split_stories = [n + 1 for n in nsplit.values() if n]
        lines.append(f"S5 {'the production arm (earlier: the newest up to the last title)' if arm == 'last' else 'the founding arm (earlier: the part’s first headlines)'}: "
                     f"{len(S)} long stories of {state['total']}; {len(checks)} questions, "
                     f"{sum(c['same'] is False for c in checks)} splits; {len(split_stories)} stories split "
                     f"({len(split_stories) / len(S):.0%}), into {np.mean(split_stories) if split_stories else 0:.1f} parts on "
                     f"average; parts per story: " + ', '.join(f"{k if k < 5 else '5+'}: {parts[k]}" for k in sorted(parts)))
        # the cost: questions per hourly run (runs within a few minutes are one)
        per_run = Counter(t(c['at']).strftime('%m-%d %H') for c in checks)
        hours = (max(t(s['last']) for s in S.values()) - min(t(s['first']) for s in S.values())).total_seconds() / 3600
        counts = np.array(list(per_run.values()) + [0] * max(0, int(hours) - len(per_run)))
        over = sum(max(0, v - CAP) for v in per_run.values())
        lines.append(f"S5   cost: {len(checks)} questions over {hours / 24:.1f} days ({len(checks) / max(hours / 24, 1):.0f} a "
                     f"day); a run asks {counts.mean():.2f} on average, at most {counts.max()}; 99th percentile "
                     f"{np.percentile(counts, 99):.0f}; a cap of {CAP} a run would put off {over} "
                     f"({sum(v > CAP for v in per_run.values())} of the {len(per_run)} runs that ask over it)")
        due = Counter(c.get('due') for c in checks if c['same'] is False)
        lines.append("S5   splits by what made the title due: " + ', '.join(f'{k} {n}' for k, n in due.most_common())
                     + f" (growth alone or with age: {(due['grown'] + due['both']) / max(1, sum(due.values())):.0%})")
        # the sagas: parts now and after
        sagas = Counter()
        for sid, n in nsplit.items():
            if S[sid]['saga'] is not None and n:
                sagas[S[sid]['saga']] += n
        if sagas:
            lines.append(f"S5   sagas: {len(sagas)} sagas gain parts: " + '; '.join(
                f"{KNOWN_SAGAS.get(g, f'saga {g}')} {state['saga_parts'].get(str(g), '?')} -> "
                f"{state['saga_parts'].get(str(g), 0) + n}" for g, n in sagas.most_common(12)))
        unsaga = sum(1 for sid, n in nsplit.items() if n and S[sid]['saga'] is None)
        lines.append(f"S5   stories in no saga that split (a saga made for their parts): {unsaga}")
        # the known cases
        total = Counter()
        for sid in ('123', '2'):
            if sid not in S:
                lines.append(f'S5   story {sid}: not among the long stories')
                continue
            got, tally = known_case(sid, S[sid], walks.get(sid, []))
            total.update(tally)
            lines.append(f"S5   {KNOWN_SAGAS.get(S[sid]['saga'], sid)} (story {sid}): "
                         f"{tally['parts']} parts")
            lines += ['S5 ' + g for g in got]
            for p in parts_of(S[sid], walks.get(sid, [])):
                lines.append(f"S5       {t(p['from']):%b %d %H:%M}-{t(p['to']):%b %d %H:%M} ({p['headlines']}): {p['first'][0][:90]}")
        lines.append(f"S5   known cases: {total['must caught']} of {total['must']} must-developments begin a part; "
                     f"{total['stray']} splits near no listed development")
    # the arms against each other: the stories each splits
    a, b = (state['walks'][x] for x in ARMS)
    sa = {sid for sid, w in a.items() if any(c['same'] is False for c in w)}
    sb = {sid for sid, w in b.items() if any(c['same'] is False for c in w)}
    lines.append(f'S5 the arms: stories split by both {len(sa & sb)}, the production arm alone {len(sa - sb)}, '
                 f'the founding arm alone {len(sb - sa)}')
    # the person's blind verdicts
    if 'blind' not in state:
        state['blind'] = blind_set(state)
        save(state)
    got = state.get('person', {})
    judged = [(x, got.get(x['key'])) for x in state['blind']]
    split = [(x, v) for x, v in judged if find(state, x['key'])[1]['same'] is False]
    ctl = [(x, v) for x, v in judged if find(state, x['key'])[1]['same'] is True]
    two = sum(v == 'two' for _, v in split)
    sure = sum(v in ('two', 'one') for _, v in split)
    lines.append(f"S5 your blind verdicts: {sum(v is not None for _, v in judged)} of {len(judged)} judged; on the "
                 f"{len(split)} proposed splits {two} two developments of {sure} called"
                 f"{f' (precision {two / sure:.0%})' if sure else ''}; on the {len(ctl)} controls "
                 f"{sum(v == 'two' for _, v in ctl)} two developments of {sum(v in ('two', 'one') for _, v in ctl)} called")
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def main():
    {'replay': replay, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
