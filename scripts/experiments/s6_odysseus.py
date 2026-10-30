"""S6 Odysseus: a new development, or the same news told again? (Oct 30, the person of Christa Pike: "there are a lot
more than 4 stories in that saga"). Sinbad (S5) replayed the switched-off split (stories.SPLIT_DEVELOPMENTS) over
every long story; of 20 splits judged blind only 7 were real developments: the model called retellings, new details,
reactions and condition updates new. This replays Sinbad's walk over the same frozen stories, production arm only,
with a reworded question (ODYSSEUS_PROMPT) and a day's minimum before a part splits; and asks Sinbad's 30 judged
questions again with it.

    s6_odysseus.py replay   walk the stories, asking where due (Gemma 4 26B via stories.same_event, cached by
                            prompt and headlines; resumes from the saved verdicts), then Sinbad's 30 again
    s6_odysseus.py report   the measures, the known cases, Sinbad's 30 against their verdicts, the fresh blind set

The paper is ~/maudlin-data/papers/odysseus.md."""
import json
import os
import random
import sys
from collections import Counter
from datetime import timedelta as td

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s5_sinbad as s5  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import stories as st  # noqa: E402

OUT = os.path.join(harness.EXP, 's6_odysseus.json')
# Sinbad's state as production keeps it: its frozen stories and the blind verdicts (Oct 30, in production's copy)
SINBAD = os.path.expanduser('~/maudlin-data/motifs/experiments/s5_sinbad.json')
ARM = 'last'
MIN_PART = td(hours=24)  # a part is not split until it has run this long from its first headline
BLIND_SPLITS, BLIND_CONTROLS = 20, 10
EVERY = 10

ODYSSEUS_PROMPT = """Two groups of headlines from one running news story: its earlier headlines, and its newest, from \
the last twelve hours or so.

Earlier:
{a}

Newest:
{b}

Do the newest headlines report a new development, or the earlier news told again?

A new development is something that newly happened in the story: a new act, decision or event by someone in it (an \
arrest, a charge, a ruling, a vote, a resignation or firing, a deal signed or closed, a new filing, a new attack, \
someone in the story reversing course or apologizing), or the next stage of an event (a storm making landfall, the next \
game in a series, a release from hospital).

The earlier news told again includes: the same event reported by other outlets or in other words; new details, \
figures or a death toll about the same event; the people in it named or profiled; reactions, criticism, defence or \
commentary from anyone; analysis, explainers and what-to-know pieces; updates on someone's condition or recovery; \
statements made at the same hearing or event.

Go by what most headlines in the newest group report: a stray headline doesn't change the answer. When in doubt, \
answer the same event.

reason: one sentence
verdict: "the same event" or "different events\""""


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'), indent=1)
    os.replace(OUT + '.tmp', OUT)


def sinbad() -> dict:
    return json.load(open(SINBAD))


def reason_of(a, b) -> str:
    import hashlib
    k = hashlib.sha1(json.dumps([ODYSSEUS_PROMPT, a, b]).encode()).hexdigest()
    return (st.read_json(st.RETURNS, {}).get(k) or {}).get('reason', '')


def ask_model(a, b):
    return st.same_event(a, b, prompt=ODYSSEUS_PROMPT)


def young(story: dict, check: dict) -> bool:
    """The part has run under MIN_PART from its first headline at the question's last title"""
    start = s5.t(check['part_start']) if check['part_start'] else s5.t(story['headlines'][0][1])
    return s5.t(check['since']) - start < MIN_PART


def replay():
    S5 = sinbad()
    state = saved()
    verdicts = state.setdefault('verdicts', {})
    walks = state.setdefault('walks', {})
    asked = 0
    todo = sorted(S5['stories'], key=int)
    for n, sid in enumerate(todo, 1):
        story = S5['stories'][sid]

        def ask(check, sid=sid, story=story):
            nonlocal asked
            if young(story, check):
                check['young'] = True
                return True  # not asked: the part is under a day old
            k = s5.key_of(ARM, sid, check)
            if k not in verdicts:
                same = ask_model(check['a'], check['b'])
                if same is None:
                    return None
                verdicts[k] = {'same': same, 'reason': reason_of(check['a'], check['b'])}
                asked += 1
                if asked % EVERY == 0:
                    save(state)
            return verdicts[k]['same']
        walks[sid] = s5.walk(ARM, story, S5['snap_start'], ask)
        if n % 10 == 0 or n == len(todo):
            save(state)
            checks = [c for w in walks.values() for c in w if not c.get('young')]
            print(f"replay: {n}/{len(todo)} stories, {len(checks)} questions, "
                  f"{sum(c['same'] is False for c in checks)} splits ({asked} asked this try)", flush=True)
    # Sinbad's 30 judged questions, asked again as they were shown
    again = state.setdefault('sinbad_again', {})
    for x in S5['blind']:
        if x['key'] in again:
            continue
        _, c = s5.find(S5, x['key'])
        same = ask_model(c['a'], c['b'])
        if same is not None:
            again[x['key']] = same
    save(state)
    missing = sum(c['same'] is None for w in walks.values() for c in w) + len(S5['blind']) - len(again)
    if missing:
        sys.exit(f'replay: {missing} questions without an answer; Ollama down? the next try asks them again')


def blind_set(state: dict, S5: dict, seed: int = 30) -> list[dict]:
    """BLIND_SPLITS of Odysseus's splits and BLIND_CONTROLS of its asked 'same' answers, outside Sinbad's blind 30 and
    the known sagas, mixed; drawn once"""
    rnd = random.Random(seed)
    used = {x['key'] for x in S5['blind']}
    pool = {True: [], False: []}
    for sid, checks in state['walks'].items():
        if S5['stories'][sid]['saga'] in s5.KNOWN_SAGAS:
            continue
        for c in checks:
            k = s5.key_of(ARM, sid, c)
            if c['same'] is not None and not c.get('young') and k not in used:
                pool[c['same']].append(k)
    picked = rnd.sample(sorted(pool[False]), min(BLIND_SPLITS, len(pool[False]))) + \
        rnd.sample(sorted(pool[True]), min(BLIND_CONTROLS, len(pool[True])))
    rnd.shuffle(picked)
    return [{'key': k, 'n': n} for n, k in enumerate(picked, 1)]


def find(state: dict, key: str):
    _, sid, since, at = key.split('|')
    for c in state['walks'].get(sid, []):
        if c['since'] == since and c['at'] == at:
            return sid, c
    return None


def report():
    S5, state = sinbad(), saved()
    S = S5['stories']
    walks = state['walks']
    lines = []
    asked = [c for w in walks.values() for c in w if not c.get('young')]
    nsplit = {sid: sum(c['same'] is False for c in w) for sid, w in walks.items()}
    split_stories = [n + 1 for n in nsplit.values() if n]
    parts = Counter(min(n + 1, 5) for n in nsplit.values())
    lines.append(f"S6 reach: {len(S)} long stories; {len(asked)} questions asked "
                 f"({sum(c.get('young', False) for w in walks.values() for c in w)} skipped as under a day), "
                 f"{sum(c['same'] is False for c in asked)} splits; {len(split_stories)} stories split "
                 f"({len(split_stories) / len(S):.0%}), {np.mean(split_stories) if split_stories else 0:.1f} parts on "
                 f"average; 5+ parts: {parts[5]} ({parts[5] / len(S):.1%}); by parts: "
                 + ', '.join(f"{k if k < 5 else '5+'}: {parts[k]}" for k in sorted(parts)))
    hours = (max(s5.t(s['last']) for s in S.values()) - min(s5.t(s['first']) for s in S.values())).total_seconds() / 3600
    lines.append(f"S6 cost: {len(asked) / max(hours / 24, 1):.0f} questions a day")
    total = Counter()
    for sid in ('123', '2'):
        got, tally = s5.known_case(sid, S[sid], walks.get(sid, []))
        total.update(tally)
        lines.append(f"S6 {s5.KNOWN_SAGAS.get(S[sid]['saga'], sid)} (story {sid}): {tally['parts']} parts")
        lines += ['S6 ' + g for g in got]
        for p in s5.parts_of(S[sid], walks.get(sid, [])):
            lines.append(f"S6     {s5.t(p['from']):%b %d %H:%M}-{s5.t(p['to']):%b %d %H:%M} ({p['headlines']}): {p['first'][0][:90]}")
    lines.append(f"S6 known cases: {total['must caught']} of {total['must']} must-developments begin a part; "
                 f"{total['stray']} splits near none")
    # Sinbad's judged 30, asked again
    again, person = state.get('sinbad_again', {}), S5.get('person', {})
    by = Counter()
    for x in S5['blind']:
        _, c = s5.find(S5, x['key'])
        kind = 'control' if c['same'] else {'two': 'real', 'one': 'wrong', 'unsure': 'unsure'}.get(person.get(x['key']), 'unjudged')
        by[(kind, again.get(x['key']) is False)] += 1
    lines.append(f"S6 Sinbad's 30 asked again: of the 12 wrong splits {by[('wrong', True)]} still split; of the 7 real "
                 f"{by[('real', True)]} still split; of the 10 controls {by[('control', True)]} split; unsure "
                 f"{by[('unsure', True)]} of {by[('unsure', True)] + by[('unsure', False)]} split")
    # the fresh blind set
    if 'blind' not in state:
        state['blind'] = blind_set(state, S5)
        save(state)
    got = state.get('person', {})
    judged = [(x, got.get(x['key'])) for x in state['blind']]
    split = [(x, v) for x, v in judged if find(state, x['key'])[1]['same'] is False]
    ctl = [(x, v) for x, v in judged if find(state, x['key'])[1]['same'] is True]
    two = sum(v == 'two' for _, v in split)
    sure = sum(v in ('two', 'one') for _, v in split)
    lines.append(f"S6 fresh blind verdicts: {sum(v is not None for _, v in judged)} of {len(judged)} judged; on the "
                 f"{len(split)} proposed splits {two} two developments of {sure} called"
                 f"{f' (precision {two / sure:.0%})' if sure else ''}; on the {len(ctl)} controls "
                 f"{sum(v == 'two' for _, v in ctl)} two developments of {sum(v in ('two', 'one') for _, v in ctl)} called")
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


if __name__ == '__main__':
    {'replay': replay, 'report': report}[sys.argv[1] if len(sys.argv) > 1 else 'report']()
