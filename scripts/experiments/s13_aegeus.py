"""S13 Aegeus: a running story known by a token set at its birth. (Nov 6, the person, on Eurycleia: "it just applies
to midterms instead of generalizing", then "Yeah sure test it".) Eurycleia joined a race's parts by the race each
story names, from a hand-written list; Mnemosyne let the model name sagas, but its names grew into catch-alls. Here
each story, in order, is asked once which open label it is a part of, or to write a new label for the running thing
it belongs to (never a field, never one turn), or none; a label is never rewritten. Stories that share a label join,
on top of production's sagas. Scored against Osiris's key (S7) and a new key of 14 non-election running stories
(aegeus_key, Claude's close reading) on Mnemosyne's stream (S11).

    s13_aegeus.py label    each story labelled (Gemma 4 26B under the lease; resumes)
    s13_aegeus.py report   B-cubed per key and arm: production, tied, moved, labels alone, and Eurycleia's moved
    s13_aegeus.py sample   the blind read: 40 labels outside the keys, and 30 label joins beside 30 of production's

Data in ~/maudlin-data/archives/archives.sqlite (aegeus_*). The paper is ~/maudlin-data/papers/aegeus.md."""
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import timedelta as td

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import s11_mnemosyne as m11  # noqa: E402
import s12_eurycleia as e12  # noqa: E402

MEMORY = td(days=14)  # a label is open this long after its newest part (a running story goes quiet for a week)
NEAREST = 6  # open labels shortlisted by likeness
BY_NAME = 2  # and at most this many more by a rare shared proper noun
NAMESAKE = e12.NAMESAKE + [('ukraine-talks', 'ukraine-air-war'), ('pike', 'fort-hood')]
BIGGEST = 33  # half again production's biggest saga (22)
LABELS_READ, JOINS_READ = 40, 30
READS = os.path.expanduser('~/maudlin-data/motifs/experiments/reads')  # not the lab copy, which a refresh wipes

PROMPT = """A new news story, shown by some of its headlines:

{story}

Running stories already being followed, each with its label and the newest headline in it:

{labels}

Is the new story a part of one of these running stories: the same case, race, investigation, trial, war or \
conflict, negotiation, outbreak, disaster, scandal, appointment or protest movement, followed as it develops? A part \
may be a new development, a consequence, a reaction, a poll, a debate or a result. It is not a part when it only \
shares a person, a place or a kind of event.

If it is a part of one, answer its number. If not, answer 0 and write a label for the running story it belongs to: \
name the running thing as a whole, the way it will still be called when later developments come (for example \
"Maui wildfires", "Boeing door-plug investigation", "2022 Pennsylvania Senate race", "Gaza ceasefire talks"). Name \
one case, never a whole field ("the midterms", "the Trump administration", "the Middle East", "crime"), and never \
just this story's own turn. If the story is one-off news that belongs to no running story, answer 0 and the label \
"none".

reason: one sentence
choice: the number, or 0
label: when choice is 0, the new label or "none"; otherwise empty"""

SCHEMA = """
create table if not exists aegeus_key (story integer primary key, kind text, "case" text, by text, why text);
create table if not exists aegeus_labels (story integer primary key, choice integer, lid text, label text,
    shortlist text, reason text);
create table if not exists aegeus_read (n integer primary key, kind text, arm text, story integer, about text,
    fair integer, why text);
"""


def db():
    con = m11.db()
    con.executescript(SCHEMA)
    return con


def _norm(label: str) -> str:
    return ' '.join(label.casefold().strip(' ."\'').split())


class Label:
    def __init__(self, lid: str, text: str):
        self.id, self.text = lid, text
        self.parts: list[dict] = []
        self.vectors: list = []
        self.active = None

    def likeness(self, v) -> float:
        return max((float(u @ v) for u in self.vectors), default=-1.0)

    def nouns(self) -> set[str]:
        return {n for p in self.parts for n in p['nouns']}

    def newest(self) -> str:
        return self.parts[-1]['titles'][0]


def _ask(story: dict, shortlist: list[Label]) -> tuple[int, str, str] | None:
    from app.analysis import llm, local_models
    lines = [f'{n}. {lb.text} (newest: "{lb.newest()}")' for n, lb in enumerate(shortlist, 1)]
    prompt = PROMPT.format(story='\n'.join(f'- {t}' for t in story['titles']),
                           labels='\n'.join(lines) or '(none open)')
    schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                               "choice": {"type": "integer", "enum": list(range(len(shortlist) + 1))},
                                               "label": {"type": "string", "maxLength": 100}},
              "required": ["reason", "choice", "label"]}
    answer = llm.complete_json(prompt, schema, max_tokens=400, model=local_models.BIG)
    if not answer or answer.get('choice') not in schema['properties']['choice']['enum']:
        return None
    return int(answer['choice']), (answer.get('label') or '').strip(), answer.get('reason', '')


def label():
    con = db()
    stories = m11.load_stories(con)
    rare = m11.rarity(stories)
    done = dict(con.execute('select story, lid from aegeus_labels'))
    texts = dict(con.execute('select lid, label from aegeus_labels where lid = \'l\' || story'))
    labels: dict[str, Label] = {}
    asked = 0
    for i, st in enumerate(stories):
        now = st['filed_at']
        for lb in labels.values():  # the clock moves on: parts' activity up to now
            for p in lb.parts:
                seen = min(p['last'], now)
                lb.active = seen if lb.active is None else max(lb.active, seen)
        if st['id'] in done:
            lid = done[st['id']]
        else:
            open_ = [lb for lb in labels.values() if lb.active is not None and now - lb.active <= MEMORY]
            shortlist = sorted(open_, key=lambda lb: -lb.likeness(st['vector']))[:NEAREST]
            mine = rare(st['nouns'], now)
            shortlist += sorted((lb for lb in open_ if lb not in shortlist and mine & lb.nouns()),
                                key=lambda lb: -len(mine & lb.nouns()))[:BY_NAME]
            got = _ask(st, shortlist)
            asked += 1
            if got is None:
                print(f'no answer for story {st["id"]}; left for the next try', flush=True)
                sys.exit(1)
            choice, text, reason = got
            if choice:
                lid = shortlist[choice - 1].id
            elif text and _norm(text) not in ('none', 'n/a', ''):
                same = [lb for lb in open_ if _norm(lb.text) == _norm(text)]  # a label spelled as an open one is it
                lid = same[0].id if same else f'l{st["id"]}'
            else:
                lid = None
            con.execute('insert or replace into aegeus_labels values (?, ?, ?, ?, ?, ?)',
                        (st['id'], choice, lid, text, json.dumps([lb.id for lb in shortlist]), reason))
            con.commit()
            if lid == f'l{st["id"]}':
                texts[lid] = text
        if lid:
            if lid not in labels:
                labels[lid] = Label(lid, texts[lid])
            lb = labels[lid]
            lb.parts.append(st)
            lb.vectors.append(st['vector'])
            seen = min(st['last'], now)
            lb.active = seen if lb.active is None else max(lb.active, seen)
        if (i + 1) % 10 == 0:
            print(f'label {i + 1}/{len(stories)} ({asked} asked this try)', flush=True)
    print(f'label {len(stories)}/{len(stories)} done', flush=True)


def arms(con) -> dict[str, dict[int, str]]:
    prod = dict(con.execute('select story, prod_saga from mnemosyne_stories'))
    lids = {s: lid for s, lid in con.execute('select story, lid from aegeus_labels') if lid}
    told = Counter(lids.values())
    shared = {s: lid for s, lid in lids.items() if told[lid] >= 2}

    def home(s):
        return f'p{prod[s]}' if prod[s] else f's{s}'
    production = {s: home(s) for s in prod}
    alone = {s: shared.get(s, f's{s}') for s in prod}
    moved = {s: shared.get(s, home(s)) for s in prod}
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for s, lid in shared.items():
        parent[find(home(s))] = find(lid)
    tied = {s: find(home(s)) for s in prod}
    out = {'production': production, 'tied': tied, 'moved': moved, 'labels alone': alone}
    if con.execute('select count(*) from eurycleia_tags').fetchone()[0] == len(prod):
        out['eurycleia'] = e12.arms(con)['moved']
    return out


def keys(con) -> dict[str, dict[int, str]]:
    stories = dict(con.execute('select story, prod_saga from mnemosyne_stories'))
    old = {s: m11.LENIENT.get(c, c) for s, c in m11.keyed(con).items() if s in stories}
    new = {s: c for s, c in con.execute('select story, "case" from aegeus_key') if s in stories}
    assert not set(old) & set(new), 'the keys overlap'
    return {'osiris': old, 'new': new, 'both': old | new}


def report():
    con = db()
    n = con.execute('select count(*) from mnemosyne_stories').fetchone()[0]
    got = con.execute('select count(*) from aegeus_labels').fetchone()[0]
    if got < n:
        print(f'{got} of {n} labelled; not scored', flush=True)
        return
    lids = [lid for (lid,) in con.execute('select lid from aegeus_labels')]
    told = Counter(x for x in lids if x)
    texts = dict(con.execute('select lid, label from aegeus_labels where lid = \'l\' || story'))
    lines = [f'S13 {n} stories: {sum(1 for x in lids if x)} labelled, {lids.count(None)} none; {len(told)} labels, '
             f'{sum(1 for v in told.values() if v >= 2)} shared by 2+; most told: ' +
             '; '.join(f'{texts[lid]} {k}' for lid, k in told.most_common(8))]
    ks = keys(con)
    for arm, pred in arms(con).items():
        sizes = Counter(pred.values())
        lines.append(f'S13 {arm}: biggest saga {max(sizes.values())}' +
                     (' (over the bound)' if max(sizes.values()) > BIGGEST else ''))
        for kname, truth in ks.items():
            p, r, f = m11.bcubed(pred, truth)
            cases = Counter(c for c in truth.values() if not c.startswith('beside'))
            held = {c: Counter(pred[s] for s, c2 in truth.items() if c2 == c).most_common(1)[0][1] / k
                    for c, k in cases.items()}
            namesake = [f'{ca}+{cb}' for ca, cb in NAMESAKE for saga in {pred[s] for s in truth}
                        if sum(1 for s, c in truth.items() if c == ca and pred[s] == saga) >= 2 and
                        sum(1 for s, c in truth.items() if c == cb and pred[s] == saga) >= 2]
            lines.append(f'S13 {arm} on {kname}: P {p:.3f} R {r:.3f} F {f:.3f}; namesake sagas {namesake or "none"}')
            if kname != 'both':
                lines.append(f'S13 {arm} on {kname} held: ' + ', '.join(f'{c} {v:.0%}' for c, v in sorted(held.items())))
            if kname == 'both':
                wrong = Counter()
                ids = list(truth)
                for i, a in enumerate(ids):
                    for b in ids[i + 1:]:
                        if pred[a] == pred[b] and truth[a] != truth[b]:
                            wrong[tuple(sorted((truth[a].split(':')[0], truth[b].split(':')[0])))] += 1
                lines.append(f'S13 {arm} wrong pairs: ' +
                             (', '.join(f'{a}~{b} {k}' for (a, b), k in wrong.most_common(8)) or 'none'))
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def sample():
    """The blind read: LABELS_READ labels outside the keys, each shown with its stories (is it one running thing, at
    the right grain?), and JOINS_READ joins the labels made in the tied arm beside JOINS_READ of production's (is the
    story part of the earlier parts' running story?), mixed, arm hidden"""
    con = db()
    stories = m11.load_stories(con)
    by_id = {s['id']: s for s in stories}
    order = {s['id']: i for i, s in enumerate(stories)}
    keyed = set(keys(con)['both'])
    prod = {s['id']: s['prod'] for s in stories}
    lids = {s: lid for s, lid in con.execute('select story, lid from aegeus_labels') if lid}
    texts = dict(con.execute('select lid, label from aegeus_labels where lid = \'l\' || story'))
    members = defaultdict(list)
    for s in sorted(lids, key=order.get):
        members[lids[s]].append(s)
    rng = random.Random(13)
    free = sorted(lid for lid, ms in members.items() if not keyed & set(ms))
    label_picks = [('label', '', lid) for lid in rng.sample(free, min(LABELS_READ, len(free)))]
    # a label join: a story beside earlier stories of its label that production didn't put in its saga
    label_joins = []
    for lid, ms in members.items():
        for k, s in enumerate(ms[1:], 1):
            before = [b for b in ms[:k] if not (prod[s] and prod[b] == prod[s])]
            if s not in keyed and before:
                label_joins.append((s, before))
    prod_members = defaultdict(list)
    for s in sorted((s for s in prod if prod[s]), key=order.get):
        prod_members[prod[s]].append(s)
    prod_joins = [(s, ms[:ms.index(s)]) for ms in prod_members.values() for s in ms[1:] if s not in keyed]
    join_picks = [('join', 'labels', s, before) for s, before in rng.sample(label_joins, min(JOINS_READ, len(label_joins)))]
    join_picks += [('join', 'production', s, before) for s, before in rng.sample(prod_joins, min(JOINS_READ, len(prod_joins)))]
    rng.shuffle(join_picks)
    con.execute('delete from aegeus_read')
    out = ['# Labels: does each name one running thing, at the right grain (not a field, not one turn)?']
    n = 0
    for _, _, lid in label_picks:
        n += 1
        con.execute('insert into aegeus_read values (?, ?, ?, ?, ?, null, null)', (n, 'label', '', None, lid))
        out.append(f'## {n}\nLabel: {texts[lid]}\nStories:\n' +
                   '\n'.join('- ' + ' | '.join(by_id[s]['titles'][:2]) for s in members[lid][:8]) +
                   (f'\n- (and {len(members[lid]) - 8} more)' if len(members[lid]) > 8 else ''))
    out.append('# Joins: is the new story part of the earlier parts\' running story?')
    for _, arm, s, before in join_picks:
        n += 1
        con.execute('insert into aegeus_read values (?, ?, ?, ?, ?, null, null)', (n, 'join', arm, s, ''))
        out.append(f'## {n}\nNew: ' + ' | '.join(by_id[s]['titles'][:3]) + '\nEarlier parts:\n' +
                   '\n'.join('- ' + ' | '.join(by_id[b]['titles'][:3]) for b in before[-3:]))
    con.commit()
    os.makedirs(READS, exist_ok=True)
    path = os.path.join(READS, 's13_aegeus_read.md')
    with open(path, 'w') as fh:
        fh.write('\n\n'.join(out) + '\n')
    print(f'{n} items to read in {path}', flush=True)


if __name__ == '__main__':
    {'label': label, 'report': report, 'sample': sample}[sys.argv[1] if len(sys.argv) > 1 else 'report']()
