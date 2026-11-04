"""S11 Mnemosyne: filing stories into sagas instead of judging them in pairs. (Nov 4, the person, after the Prodigal
Son: "Can we think creatively about how this sort of thing is done in other circumstances", then "Ok test it".)
Production joins two stories into a saga when Gemma says "one running story" of their central headlines; within a
long race those headlines share nothing on their face (the Prodigal Son: Texas 0 of 15 pairs). Wire slugs, newspaper
morgues and the BBC's storylines file each new item into a named running story instead. Here each production story,
in the order first seen, is filed by Gemma into one of a shortlist of open sagas (shown by name, note and headlines)
or starts its own; scored against Osiris's key (S7) beside production's own sagas.

    s11_mnemosyne.py stream   the month's production stories from the Nov 3 backup: central headlines, vectors, names
    s11_mnemosyne.py file     both arms (filed, seeded), story by story (Gemma 4 26B under the lease; resumes)
    s11_mnemosyne.py report   B-cubed against the key, per arm and production; the races; wrong joins
    s11_mnemosyne.py sample   the blind read: 30 joins outside the key from each of filed and production, mixed

Data in ~/maudlin-data/archives/archives.sqlite (mnemosyne_*). The paper is ~/maudlin-data/papers/mnemosyne.md."""
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s7_osiris as o7  # noqa: E402

BACKUP = os.path.expanduser('~/maudlin-prod/backups/data-2026-11-03-sagas.db')  # before the Nov 3 hand fixes
LEAD = td(days=3)  # stories this long before the first keyed one are filed too, so the first cases have neighbours
EARLY = td(hours=12)  # a story is shown by its headlines from these first hours
SHOWN = 5  # a new story's central headlines shown
SAGA_SHOWN = 4  # a saga's headlines shown, spread over its parts, newest first
MEMORY = td(days=7)  # a saga is open this long after its last activity (production's SAGA_MEMORY)
NEAREST = 5  # open sagas shortlisted by likeness
BY_NAME = 2  # and at most this many more by a rare shared proper noun
RARE = 0.04  # a proper noun is rare when in at most this share of the last week's stories
NOTE_AT = (2, 4, 8, 16)  # a saga is named and noted when it reaches this many parts
LEAST, SAME_CASE = 4, 0.6  # a keyed story: this many keyed headlines, this share of them the case's (as S10)
NAMESAKE = [('michigan-senate', 'texas-senate'), ('michigan-senate', 'alaska-senate'), ('texas-senate', 'alaska-senate'),
            ('comey', 'fbi-officials'), ('omar-investigation', 'ice-houston'), ('trump-michigan-rally', 'rally-format')]
RACES = ('texas-senate', 'michigan-senate', 'alaska-senate')
LENIENT = {'trump-michigan-rally': 'michigan-senate'}

STATES = {'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado',
          'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
          'IL': 'Illinois', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine',
          'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
          'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
          'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon',
          'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee',
          'TX': 'Texas', 'VT': 'Vermont', 'VA': 'Virginia', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'}
# 2026: Senate class 2 and the Ohio and Florida specials; the governors' cycle. From the cycles, not looked up
SENATE = ['AL', 'AK', 'AR', 'CO', 'DE', 'GA', 'ID', 'IL', 'IA', 'KS', 'KY', 'LA', 'ME', 'MA', 'MI', 'MN', 'MS', 'MT', 'NE', 'NH', 'NJ', 'NM', 'NC', 'OK', 'OR', 'RI', 'SC', 'SD', 'TN', 'TX', 'VA', 'WV', 'WY', 'OH', 'FL']
GOVERNOR = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'FL', 'GA', 'HI', 'ID', 'IL', 'IA', 'KS', 'ME', 'MD', 'MA', 'MI', 'MN', 'NE', 'NV', 'NH', 'NM', 'NY', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'VT', 'WI', 'WY']

FILE_PROMPT = """A new news story, shown by some of its headlines, and running stories already being followed, each \
with a number.

Is the new story a part of one of the running stories: the same case, incident, investigation, negotiation, election \
race or campaign, followed as it develops? A part may be a new development, a different angle, a consequence, a \
reaction, a poll, a debate, an ad or a result. It is not a part when it only shares a person, a place, a court or a \
kind of event: separate cases at the same court, separate crimes by people of the same nationality, two different \
races, a general overview beside one case in it, or a separate event involving the same person (a rally and an \
unrelated executive order signed the same week).

New story:
{story}

Running stories:
{sagas}

reason: one sentence
choice: the number of the running story the new story is part of, or 0 if it is part of none"""

NOTE_PROMPT = """These headlines are parts of one running news story. Name the story in 2 to 6 words, the way a \
newspaper labels a running story (for example "Cornell fraternity rape case" or "Russia-Ukraine peace talks"), and \
write one sentence saying what the running story is: the case, race, investigation, negotiation or event as a whole, \
broad enough to cover its later developments, not just its latest turn. Plain, neutral words.

{headlines}"""
NOTE_SCHEMA = {"type": "object", "properties": {"name": {"type": "string", "maxLength": 80},
                                                "note": {"type": "string", "maxLength": 300}},
               "required": ["name", "note"]}

SCHEMA = """
create table if not exists mnemosyne_stories (story integer primary key, first text, last text, filed_at text,
    titles text, vector blob, nouns text, prod_saga integer);
create table if not exists mnemosyne_filed (arm text, story integer, saga text, choice integer, shortlist text,
    reason text, primary key (arm, story));
create table if not exists mnemosyne_notes (arm text, saga text, parts integer, name text, note text,
    primary key (arm, saga, parts));
create table if not exists mnemosyne_read (n integer primary key, arm text, story integer, saga text, fair integer,
    why text);
"""


def db() -> sqlite3.Connection:
    con = o7.db()
    con.executescript(SCHEMA)
    return con


def keyed(con) -> dict[int, str]:
    """Keyed production stories -> truth: the case for a case's story, 'beside:<id>' for one beside it (as S10)"""
    keys = o7.answer_key(con)
    prod = dict(con.execute('select headline, production_story from osiris_headlines'))
    by = defaultdict(lambda: defaultdict(list))
    for case, k in keys.items():
        for h, ev in k.items():
            if prod.get(h):
                by[case][prod[h]].append(ev)
    truth = {}
    for case, stories in by.items():
        for sid, evs in stories.items():
            if len(evs) < LEAST:
                continue
            mine = sum(ev != 'other' for ev in evs) / len(evs)
            if mine >= SAME_CASE:
                truth[sid] = case
            elif mine <= 1 - SAME_CASE:
                truth.setdefault(sid, f'beside:{sid}')
    return truth


def stream():
    """The month's production stories, each with its central headlines from its first hours, its vector, its proper
    nouns and its production saga (ended sagas followed to where they went)"""
    import app.analysis.sagas as sg
    con = db()
    truth = keyed(con)
    src = sqlite3.connect(f'file:{BACKUP}?mode=ro', uri=True)
    firsts = [r[0] for s in truth for r in src.execute('select first_seen from story where id = ?', (s,))]
    start = (dt.fromisoformat(min(firsts)[:19]) - LEAD).isoformat(' ')
    end = (dt.fromisoformat(max(firsts)[:19]) + td(days=1)).isoformat(' ')
    ended = dict(src.execute('select saga_id, to_saga from saga_ended where to_saga is not null'))

    def final(saga):
        seen = set()
        while saga in ended and saga not in seen:
            seen.add(saga)
            saga = ended[saga]
        return saga

    stories = src.execute('select id, first_seen, last_seen, saga_id from story where first_seen between ? and ? '
                          'order by first_seen', (start, end)).fetchall()
    missing = set(truth) - {s for s, *_ in stories}
    print(f'{len(stories)} stories {start} to {end}; keyed {len(truth)}, outside the window {len(missing)}', flush=True)
    rows = []
    for i, (sid, first, last, saga) in enumerate(stories):
        hs = src.execute('select h.title, h.first_accessed from story_headline sh join headline h on h.id = '
                         'sh.headline_id where sh.story_id = ? order by h.first_accessed', (sid,)).fetchall()
        cut = (dt.fromisoformat(first[:19]) + EARLY).isoformat(' ')
        early = [t for t, at in hs if at <= cut] or [t for t, _ in hs[:SHOWN * 2]]
        early = list({t.strip().casefold(): t.strip() for t in reversed(early)}.values())[::-1]  # one of each, any case
        if not early:
            continue
        v = sg.embed(early)
        v = v / np.linalg.norm(v, axis=1, keepdims=True)
        c = v.mean(axis=0)
        c = c / np.linalg.norm(c)
        shown = sg.central(early, v, SHOWN)
        filed_at = min(dt.fromisoformat(first[:19]) + EARLY, dt.fromisoformat(last[:19])).isoformat(' ')
        rows.append((sid, first[:19], last[:19], filed_at, json.dumps(shown), c.astype(np.float32).tobytes(),
                     json.dumps(sorted(sg.proper_nouns(early))), final(saga) if saga else None))
        if (i + 1) % 100 == 0:
            print(f'stream {i + 1}/{len(stories)}', flush=True)
    con.execute('delete from mnemosyne_stories')
    con.executemany('insert into mnemosyne_stories values (?, ?, ?, ?, ?, ?, ?, ?)', rows)
    con.commit()
    print(f'{len(rows)} stories streamed', flush=True)


def seeds() -> list[dict]:
    out = []
    for st in SENATE:
        name = f'{STATES[st]} U.S. Senate race'
        out.append({'id': f'seed-senate-{st}', 'state': STATES[st], 'name': f'2026 {name}',
                    'note': f'The 2026 election for a U.S. Senate seat from {STATES[st]}: its candidates, campaign, '
                            f'polls, ads, debates, scandals, the vote and the result.'})
    for st in GOVERNOR:
        out.append({'id': f'seed-governor-{st}', 'state': STATES[st], 'name': f'2026 {STATES[st]} governor race',
                    'note': f'The 2026 election for governor of {STATES[st]}: its candidates, campaign, polls, ads, '
                            f'debates, scandals, the vote and the result.'})
    return out


class Saga:
    def __init__(self, sid: str, name: str = '', note: str = '', seed_state: str = '', vector=None):
        self.id, self.name, self.note, self.state = sid, name, note, seed_state
        self.parts: list[dict] = []
        self.vectors = [] if vector is None else [vector]
        self.active = None  # the last activity: a part's last seen, as far as the clock has reached

    def open_at(self, now: dt) -> bool:
        return bool(self.state) or (self.active is not None and now - self.active <= MEMORY)

    def likeness(self, v) -> float:
        return max((float(u @ v) for u in self.vectors), default=-1.0)

    def shown(self) -> list[str]:
        """SAGA_SHOWN headlines spread over the parts, newest part first"""
        out, parts = [], self.parts[::-1]
        for k in range(SAGA_SHOWN):
            for p in parts:
                if k < len(p['titles']) and len(out) < SAGA_SHOWN:
                    out.append(p['titles'][k])
            if len(out) >= SAGA_SHOWN:
                break
        return out


def _ask_file(story: dict, shortlist: list[Saga]) -> tuple[int, str] | None:
    from app.analysis import llm, local_models
    lines = []
    for n, sg_ in enumerate(shortlist, 1):
        head = f'{n}. {sg_.name}: {sg_.note}' if sg_.name else f'{n}. (not yet named)'
        lines.append(head + ''.join(f'\n   - {t}' for t in sg_.shown()))
    prompt = FILE_PROMPT.format(story='\n'.join(f'- {t}' for t in story['titles']), sagas='\n'.join(lines))
    schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 1000},
                                               "choice": {"type": "integer", "enum": list(range(len(shortlist) + 1))}},
              "required": ["reason", "choice"]}
    answer = llm.complete_json(prompt, schema, max_tokens=500, model=local_models.BIG)
    if not answer or answer.get('choice') not in schema['properties']['choice']['enum']:
        return None
    return int(answer['choice']), answer.get('reason', '')


def _ask_note(titles: list[str]) -> dict | None:
    from app.analysis import llm, local_models
    answer = llm.complete_json(NOTE_PROMPT.format(headlines='\n'.join(f'- {t}' for t in titles)), NOTE_SCHEMA,
                               max_tokens=300, model=local_models.BIG)
    if not answer or not answer.get('name') or not answer.get('note'):
        return None
    return {'name': answer['name'].strip(), 'note': answer['note'].strip()}


def run_arm(con, arm: str, stories: list[dict], rare_nouns):
    import app.analysis.sagas as sg
    sagas: dict[str, Saga] = {}
    if arm == 'seeded':
        for sd in seeds():
            v = sg.embed([f"{sd['name']}. {sd['note']}"])[0]
            sagas[sd['id']] = Saga(sd['id'], sd['name'], sd['note'], sd['state'], v / np.linalg.norm(v))
    done = {s: (saga, choice, reason) for s, saga, choice, reason in
            con.execute('select story, saga, choice, reason from mnemosyne_filed where arm = ?', (arm,))}
    notes = {(saga, parts): (name, note) for saga, parts, name, note in
             con.execute('select saga, parts, name, note from mnemosyne_notes where arm = ?', (arm,))}
    asked = 0
    for i, st in enumerate(stories):
        now = st['filed_at']
        for s_ in sagas.values():  # the clock moves on: parts' activity up to now
            for p in s_.parts:
                seen = min(p['last'], now)
                s_.active = seen if s_.active is None else max(s_.active, seen)
        if st['id'] in done:
            saga_id = done[st['id']][0]
        else:
            open_ = [s_ for s_ in sagas.values() if s_.open_at(now)]
            near = sorted(open_, key=lambda s_: -s_.likeness(st['vector']))
            shortlist = [s_ for s_ in near if not s_.state][:NEAREST]
            mine = rare_nouns(st['nouns'], now)
            by_name = sorted((s_ for s_ in open_ if s_ not in shortlist and not s_.state and
                              mine & s_.nouns()), key=lambda s_: -len(mine & s_.nouns()))[:BY_NAME]
            shortlist += by_name
            text = ' '.join(st['titles'])
            shortlist += [s_ for s_ in open_ if s_.state and re.search(rf'\b{s_.state}\b', text)]
            choice, reason = 0, 'nothing open'
            if shortlist:
                got = _ask_file(st, shortlist)
                asked += 1
                if got is None:
                    print(f'{arm}: no answer for story {st["id"]}; left for the next try', flush=True)
                    return False
                choice, reason = got
            saga_id = shortlist[choice - 1].id if choice else f's{st["id"]}'
            con.execute('insert or replace into mnemosyne_filed values (?, ?, ?, ?, ?, ?)',
                        (arm, st['id'], saga_id, choice, json.dumps([s_.id for s_ in shortlist]), reason))
            con.commit()
        if saga_id not in sagas:
            sagas[saga_id] = Saga(saga_id)
        s_ = sagas[saga_id]
        s_.parts.append(st)
        s_.vectors.append(st['vector'])
        s_.active = min(st['last'], now) if s_.active is None else max(s_.active, min(st['last'], now))
        n = len(s_.parts)
        if n in NOTE_AT and not s_.state:
            if (saga_id, n) not in notes:
                titles = [t for p in s_.parts for t in p['titles'][:3]][-24:]
                got = _ask_note(titles)
                asked += 1
                if got is None:
                    print(f'{arm}: no note for saga {saga_id}; left for the next try', flush=True)
                    return False
                con.execute('insert or replace into mnemosyne_notes values (?, ?, ?, ?, ?)',
                            (arm, saga_id, n, got['name'], got['note']))
                con.commit()
                notes[(saga_id, n)] = (got['name'], got['note'])
            s_.name, s_.note = notes[(saga_id, n)]
        if (i + 1) % 10 == 0:
            print(f'{arm} {i + 1}/{len(stories)} ({asked} asked this try)', flush=True)
    return True


def _nouns(self) -> set[str]:
    return {n for p in self.parts for n in p['nouns']}


Saga.nouns = _nouns


def load_stories(con) -> list[dict]:
    out = []
    for sid, first, last, filed_at, titles, vec, nouns, prod in con.execute(
            'select story, first, last, filed_at, titles, vector, nouns, prod_saga from mnemosyne_stories'):
        out.append({'id': sid, 'first': dt.fromisoformat(first), 'last': dt.fromisoformat(last),
                    'filed_at': dt.fromisoformat(filed_at), 'titles': json.loads(titles),
                    'vector': np.frombuffer(vec, dtype=np.float32), 'nouns': set(json.loads(nouns)),
                    'prod': prod})
    out.sort(key=lambda s: (s['filed_at'], s['id']))
    return out


def rarity(stories: list[dict]):
    """rare(nouns, now): those of the nouns in at most RARE of the stories first seen in the week before now"""
    def rare(nouns, now):
        week = [s for s in stories if now - MEMORY <= s['first'] <= now]
        if not week:
            return set(nouns)
        return {n for n in nouns if sum(n in s['nouns'] for s in week) / len(week) <= RARE}
    return rare


def file_():
    con = db()
    stories = load_stories(con)
    rare = rarity(stories)
    for arm in ('filed', 'seeded'):
        if not run_arm(con, arm, stories, rare):
            sys.exit(1)
        print(f'{arm} done: {len(stories)}/{len(stories)}', flush=True)


def bcubed(pred: dict, truth: dict) -> tuple[float, float, float]:
    by_pred, by_truth = defaultdict(set), defaultdict(set)
    for s in truth:
        by_pred[pred[s]].add(s)
        by_truth[truth[s]].add(s)
    p = np.mean([len(by_pred[pred[s]] & by_truth[truth[s]]) / len(by_pred[pred[s]]) for s in truth])
    r = np.mean([len(by_pred[pred[s]] & by_truth[truth[s]]) / len(by_truth[truth[s]]) for s in truth])
    return p, r, 2 * p * r / (p + r)


def report():
    con = db()
    truth = keyed(con)
    stories = dict(con.execute('select story, prod_saga from mnemosyne_stories'))
    truth = {s: c for s, c in truth.items() if s in stories}
    arms = {'production': {s: (f'p{stories[s]}' if stories[s] else f's{s}') for s in stories}}
    for arm in ('filed', 'seeded'):
        got = dict(con.execute('select story, saga from mnemosyne_filed where arm = ?', (arm,)))
        if len(got) == len(stories):
            arms[arm] = got
        else:
            print(f'{arm}: {len(got)} of {len(stories)} filed; not scored', flush=True)
    lenient = {s: LENIENT.get(c, c) for s, c in truth.items()}
    cases = Counter(c for c in truth.values() if not c.startswith('beside'))
    lines = [f'S11 keyed stories {len(truth)} ({sum(cases.values())} of 15 cases, '
             f'{len(truth) - sum(cases.values())} beside them) in a stream of {len(stories)}']
    for arm, pred in arms.items():
        p, r, f = bcubed(pred, truth)
        lp, lr, lf = bcubed(pred, lenient)
        held = {}
        for case in cases:
            mine = [pred[s] for s, c in truth.items() if c == case]
            held[case] = Counter(mine).most_common(1)[0][1] / len(mine)
        namesake = []
        for ca, cb in NAMESAKE:
            for saga in set(pred.values()):
                na = sum(1 for s, c in truth.items() if c == ca and pred[s] == saga)
                nb = sum(1 for s, c in truth.items() if c == cb and pred[s] == saga)
                if na >= 2 and nb >= 2:
                    namesake.append(f'{ca}+{cb}')
        wrong = Counter()
        keyed_ids = list(truth)
        for i, a in enumerate(keyed_ids):
            for b in keyed_ids[i + 1:]:
                if pred[a] == pred[b] and truth[a] != truth[b]:
                    wrong[tuple(sorted((truth[a].split(':')[0], truth[b].split(':')[0])))] += 1
        sizes = Counter(Counter(pred.values()).values())
        multi = sum(n for k, n in sizes.items() if k > 1)
        lines.append(f'S11 {arm}: P {p:.3f} R {r:.3f} F {f:.3f}; lenient F {lf:.3f}; races held ' +
                     ', '.join(f'{c} {held[c]:.0%}' for c in RACES if c in held) +
                     f'; namesake sagas {namesake or "none"}; sagas of 2+ parts {multi}, biggest {max(sizes)}')
        lines.append(f'S11 {arm} held by case: ' + ', '.join(f'{c} {v:.0%}' for c, v in sorted(held.items())))
        lines.append(f'S11 {arm} wrong pairs: ' + (', '.join(f'{a}~{b} {n}' for (a, b), n in wrong.most_common(8))
                                                    or 'none'))
    for arm in ('filed', 'seeded'):
        n = con.execute('select count(*) from mnemosyne_filed where arm = ? and choice > 0', (arm,)).fetchone()[0]
        notes = con.execute('select count(*) from mnemosyne_notes where arm = ?', (arm,)).fetchone()[0]
        lines.append(f'S11 {arm}: {n} stories filed into an open saga, {notes} names and notes written')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def sample():
    """The blind read: 30 joins outside the key from each of filed and production (a story beside an earlier part of
    its saga), mixed, arm hidden; written to mnemosyne_read and to a file for reading"""
    con = db()
    truth = keyed(con)
    stories = load_stories(con)
    by_id = {s['id']: s for s in stories}
    order = {s['id']: i for i, s in enumerate(stories)}
    filed = dict(con.execute("select story, saga from mnemosyne_filed where arm = 'filed'"))
    arms = {'production': {s['id']: s['prod'] for s in stories if s['prod']}, 'filed': filed}
    rng = random.Random(11)
    picks = []
    for arm, pred in arms.items():
        members = defaultdict(list)
        for s in sorted(pred, key=order.get):
            members[pred[s]].append(s)
        joins = [(s, ms[:ms.index(s)]) for ms in members.values() for s in ms[1:] if s not in truth]
        for s, before in rng.sample(joins, min(30, len(joins))):
            picks.append((arm, s, pred[s], before[-3:]))
    rng.shuffle(picks)
    con.execute('delete from mnemosyne_read')
    out = []
    for n, (arm, s, saga, before) in enumerate(picks, 1):
        con.execute('insert into mnemosyne_read values (?, ?, ?, ?, null, null)', (n, arm, s, str(saga)))
        out.append(f'## {n}\nNew: ' + ' | '.join(by_id[s]['titles'][:3]) + '\nEarlier parts:\n' +
                   '\n'.join('- ' + ' | '.join(by_id[b]['titles'][:3]) for b in before))
    con.commit()
    path = os.path.join(harness.EXP, 's11_mnemosyne_read.md')
    with open(path, 'w') as fh:
        fh.write('\n\n'.join(out) + '\n')
    print(f'{len(picks)} joins to read in {path}', flush=True)


if __name__ == '__main__':
    {'stream': stream, 'file': file_, 'report': report, 'sample': sample}[sys.argv[1] if len(sys.argv) > 1
                                                                          else 'report']()
