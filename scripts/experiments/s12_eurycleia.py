"""S12 Eurycleia: a story known by the race it names. (Nov 5, the person, after Mnemosyne: "Sure. I mean we have yet
to solve this problem".) The Prodigal Son found the pairwise judge can't join a long race's parts, which don't look
alike; Mnemosyne held races together by filing into named sagas, but grew a catch-all that swallowed the campaign.
Here production's sagas stay as they are, and each story is asked once which single 2026 Senate or governor race it
is mainly about, if any; stories of one race join that race's saga. Scored against Osiris's key (S7) on Mnemosyne's
stream (S11).

    s12_eurycleia.py tag      each story of the stream tagged with a race or none (Gemma 4 26B under the lease; resumes)
    s12_eurycleia.py report   B-cubed against the key (strict and lenient), per arm: production, moved, tied
    s12_eurycleia.py sample   the blind read: 40 tags, and 30 joins the tags made beside 30 of production's, mixed

Data in ~/maudlin-data/archives/archives.sqlite (eurycleia_*). The paper is ~/maudlin-data/papers/eurycleia.md."""
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s11_mnemosyne as m11  # noqa: E402

RACES = {f'{st}-senate': f'{m11.STATES[st]} U.S. Senate race' for st in m11.SENATE}
RACES |= {f'{st}-governor': f'{m11.STATES[st]} governor race' for st in m11.GOVERNOR}
NONE = 'none'
LEAST_TOLD = 2  # a race named by fewer stories makes no saga
NAMESAKE = [('michigan-senate', 'texas-senate'), ('michigan-senate', 'alaska-senate'), ('texas-senate', 'alaska-senate'),
            ('comey', 'fbi-officials'), ('omar-investigation', 'ice-houston')]
TAGS_READ, JOINS_READ = 40, 30

TAG_PROMPT = """These headlines from different news outlets cover one news story:

{story}

Is this story mainly about one 2026 U.S. election race for Senate or governor? A race's parts are its candidates' \
campaigns, polls, ads, debates, endorsements and scandals, a rally held for one of its candidates, the vote and the \
result. Answer "none" when the story is about several races, the elections as a whole, a figure campaigning across \
states, or no election.

The races:
{races}

Give a short reason, then the race's code or "none"."""

SCHEMA = """
create table if not exists eurycleia_tags (story integer primary key, race text, reason text);
create table if not exists eurycleia_read (n integer primary key, kind text, arm text, story integer, about text,
    fair integer, why text);
"""


def db():
    con = m11.db()
    con.executescript(SCHEMA)
    return con


def _ask(titles: list[str]) -> tuple[str, str] | None:
    from app.analysis import llm, local_models
    races = '\n'.join(f'- {code}: {name}' for code, name in RACES.items())
    prompt = TAG_PROMPT.format(story='\n'.join(f'- {t}' for t in titles), races=races)
    schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 300},
                                               "race": {"type": "string", "enum": [*RACES, NONE]}},
              "required": ["reason", "race"]}
    answer = llm.complete_json(prompt, schema, max_tokens=200, model=local_models.BIG)
    if not answer or answer.get('race') not in schema['properties']['race']['enum']:
        return None
    return answer['race'], answer.get('reason', '')


def tag():
    con = db()
    stories = m11.load_stories(con)
    done = {s for (s,) in con.execute('select story from eurycleia_tags')}
    asked = 0
    for i, st in enumerate(stories):
        if st['id'] not in done:
            got = _ask(st['titles'])
            if got is None:
                print(f'no answer for story {st["id"]}; left for the next try', flush=True)
                sys.exit(1)
            con.execute('insert or replace into eurycleia_tags values (?, ?, ?)', (st['id'], *got))
            con.commit()
            asked += 1
        if (i + 1) % 10 == 0:
            print(f'tag {i + 1}/{len(stories)} ({asked} asked this try)', flush=True)
    print(f'tag {len(stories)}/{len(stories)} done', flush=True)


def arms(con) -> dict[str, dict[int, str]]:
    """story -> saga for production, moved (a tagged story leaves its saga for its race's) and tied (sagas holding
    stories of one race merged whole)"""
    prod = dict(con.execute('select story, prod_saga from mnemosyne_stories'))
    tags = dict(con.execute('select story, race from eurycleia_tags'))
    told = Counter(r for r in tags.values() if r != NONE)
    raced = {s: r for s, r in tags.items() if r != NONE and told[r] >= LEAST_TOLD}

    def home(s):
        return f'p{prod[s]}' if prod[s] else f's{s}'
    production = {s: home(s) for s in prod}
    moved = {s: f'race:{raced[s]}' if s in raced else home(s) for s in prod}
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for s, r in raced.items():
        parent[find(home(s))] = find(f'race:{r}')
    tied = {s: find(home(s)) for s in prod}
    return {'production': production, 'moved': moved, 'tied': tied}


def report():
    con = db()
    stories = dict(con.execute('select story, prod_saga from mnemosyne_stories'))
    tags = dict(con.execute('select story, race from eurycleia_tags'))
    if len(tags) < len(stories):
        print(f'{len(tags)} of {len(stories)} tagged; not scored', flush=True)
        return
    truth = {s: c for s, c in m11.keyed(con).items() if s in stories}
    lenient = {s: m11.LENIENT.get(c, c) for s, c in truth.items()}
    cases = Counter(c for c in truth.values() if not c.startswith('beside'))
    told = Counter(r for r in tags.values() if r != NONE)
    lines = [f'S12 {sum(told.values())} of {len(tags)} stories tagged with a race, {len(told)} races; most told: ' +
             ', '.join(f'{r} {n}' for r, n in told.most_common(8))]
    lines.append('S12 keyed tags: ' + ', '.join(f'{c} ' + '/'.join(f'{r}:{n}' for r, n in Counter(
        tags[s] for s, c2 in truth.items() if c2 == c).most_common(3)) for c in sorted(cases)))
    for arm, pred in arms(con).items():
        p, r, f = m11.bcubed(pred, truth)
        lp, lr, lf = m11.bcubed(pred, lenient)
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
        ids = list(truth)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if pred[a] == pred[b] and lenient[a] != lenient[b]:
                    wrong[tuple(sorted((truth[a].split(':')[0], truth[b].split(':')[0])))] += 1
        sizes = Counter(pred.values())
        lines.append(f'S12 {arm}: strict P {p:.3f} R {r:.3f} F {f:.3f}; lenient P {lp:.3f} R {lr:.3f} F {lf:.3f}; '
                     'races held ' + ', '.join(f'{c} {held[c]:.0%}' for c in m11.RACES if c in held) +
                     f'; namesake sagas {namesake or "none"}; biggest saga {max(sizes.values())}')
        lines.append(f'S12 {arm} held by case: ' + ', '.join(f'{c} {v:.0%}' for c, v in sorted(held.items())))
        lines.append(f'S12 {arm} wrong pairs (lenient): ' +
                     (', '.join(f'{a}~{b} {n}' for (a, b), n in wrong.most_common(8)) or 'none'))
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def sample():
    """The blind read: TAGS_READ tagged stories outside the key (is it mainly about that race?), and JOINS_READ joins
    the tags made beside JOINS_READ of production's (is the story part of its saga's running story?), mixed"""
    con = db()
    truth = m11.keyed(con)
    stories = m11.load_stories(con)
    by_id = {s['id']: s for s in stories}
    order = {s['id']: i for i, s in enumerate(stories)}
    tags = dict(con.execute('select story, race from eurycleia_tags'))
    both = arms(con)
    rng = random.Random(12)
    tagged = sorted(s for s, r in tags.items() if r != NONE and s not in truth)
    picks = [('tag', '', s, tags[s], []) for s in rng.sample(tagged, min(TAGS_READ, len(tagged)))]
    for arm, pred in (('production', both['production']), ('moved', both['moved'])):
        members = defaultdict(list)
        for s in sorted(pred, key=order.get):
            members[pred[s]].append(s)
        joins = [(s, ms[:ms.index(s)]) for saga, ms in members.items() for s in ms[1:] if s not in truth and
                 (saga.startswith('race:') if arm == 'moved' else saga.startswith('p'))]
        for s, before in rng.sample(joins, min(JOINS_READ, len(joins))):
            picks.append(('join', arm, s, pred[s], before[-3:]))
    tag_picks, join_picks = [p for p in picks if p[0] == 'tag'], [p for p in picks if p[0] == 'join']
    rng.shuffle(join_picks)
    con.execute('delete from eurycleia_read')
    out = ['# Tags: is the story mainly about this race?']
    n = 0
    for kind, arm, s, about, before in tag_picks + join_picks:
        n += 1
        con.execute('insert into eurycleia_read values (?, ?, ?, ?, ?, null, null)', (n, kind, arm, s, str(about)))
        if kind == 'join' and n == len(tag_picks) + 1:
            out.append('# Joins: is the new story part of the earlier parts\' running story?')
        if kind == 'tag':
            out.append(f'## {n}\nRace: {RACES[about]}\nStory: ' + ' | '.join(by_id[s]['titles'][:4]))
        else:
            out.append(f'## {n}\nNew: ' + ' | '.join(by_id[s]['titles'][:3]) + '\nEarlier parts:\n' +
                       '\n'.join('- ' + ' | '.join(by_id[b]['titles'][:3]) for b in before))
    con.commit()
    path = os.path.join(harness.EXP, 's12_eurycleia_read.md')
    with open(path, 'w') as fh:
        fh.write('\n\n'.join(out) + '\n')
    print(f'{n} items to read in {path}', flush=True)


if __name__ == '__main__':
    {'tag': tag, 'report': report, 'sample': sample}[sys.argv[1] if len(sys.argv) > 1 else 'report']()
