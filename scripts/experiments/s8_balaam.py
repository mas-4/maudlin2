"""S8 Balaam: does a show tell a claim, report it, or argue against it? (Nov 2, the person: "I would like to try the
other experiments"). The motif, show and aisle pages say a claim "came up on" a show, "told, reported or argued
against. We don't yet mark which", and 5,313 of the index's 8,733 filings are show claims. Balaam, sent to curse and
made to bless: the same words put to the opposite use.

    s8_balaam.py sample    200 filed show claims, by speaker (50 host, 50 guest, 50 clip, 25 caller, 25 unmarked), each
                           with its quote and the four minutes of transcript around it; 40 of them marked for the
                           person; the readers' batches written to maudlin-notes/experiments/balaam/items-NN.json
    s8_balaam.py key       the readers' drafts (drafts/*.json), Claude's close reading of the 40 (close.json: the person
                           handed it over, Nov 2), the news-register rule applied to the drafts (rule.json) and any answers of the person's (person.json) into balaam_key
    s8_balaam.py arms      R (circulation's prompt as it is, the quote alone), Q (a show prompt: the quote, the speaker
                           and the minutes around it) and N (Q on Nimble 9B); answers kept, resumable
    s8_balaam.py report    the hypotheses, on the person's answer where there is one and the readers' elsewhere
The paper is ~/maudlin-data/papers/balaam.md. Data in archives.sqlite, tables balaam_*."""
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime as dt

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import archive_db  # noqa: E402
from app.analysis import circulation, llm, local_models  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

NOTES = os.path.expanduser('~/Repos/maudlin-notes/experiments/balaam')
STRATA = {'host': 50, 'guest': 50, 'clip': 50, 'caller': 25, '': 25}
PERSON = 8  # of each stratum, for the person to read blind
BATCH = 50
AROUND = 120  # seconds of transcript either side of the quote
FOUND = 0.5  # share of the quote's words a window must hold to count as found
SEED = 8
STANCES = ['telling it', 'reporting it', 'arguing against it', 'about it, not taking a side', 'unclear']
FOLD_R = {'telling it': 'telling it', 'arguing against it': 'arguing against it',
          'about the news, not the claim': 'about it, not taking a side', 'something else': 'unclear'}
SPEAKER_WORD = {'host': "one of the show's hosts", 'guest': 'a guest the hosts interview',
                'caller': 'a listener calling in', 'clip': 'a recording the show plays (a speech, another show)',
                '': 'not marked'}
Q_PROMPT = """A show we follow: {show}. Our reader marked the speaker as {speaker}.

The transcript around the moment (made by machine, no speaker names):
{context}

The quote our reader took: "{quote}"
The claim it was written as: {claim}

What does the show do with the claim? Judge by the speaker; for a played clip, by how the show presents it (hosts
often play a clip and then knock it down).
"telling it": states, repeats or spreads it as true or likely, in their own voice.
"reporting it": relays that others say it, as news, without taking it up or knocking it down.
"arguing against it": disputes, mocks or debunks it, including playing a clip in order to rebut it.
"about it, not taking a side": asks or discusses it (an interview question, "some say") without a stance.
"unclear": the transcript doesn't show."""
Q_SCHEMA = {"type": "object", "properties": {"stance": {"type": "string", "enum": STANCES}}, "required": ["stance"]}
ARMS = {'R': (circulation.PROMPT, circulation.SCHEMA, local_models.BIG),
        'Q': (Q_PROMPT, Q_SCHEMA, local_models.BIG),
        'N': (Q_PROMPT, Q_SCHEMA, local_models.DECIDER)}
SCHEMA = """
create table if not exists balaam_items (id integer primary key, claim text, quote text, speaker text, show text,
    lean text, url text, date text, context text, found real, person integer);
create table if not exists balaam_key (id integer, by text, stance text, why text, at text, primary key (id, by));
create table if not exists balaam_answers (arm text, id integer, stance text, model text, at text,
    primary key (arm, id));
"""
WORD = re.compile(r"[a-z0-9']+")


def db() -> sqlite3.Connection:
    con = archive_db.connect()
    con.executescript(SCHEMA)
    return con


def site() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{os.path.join(Config.data, 'data.db')}?mode=ro", uri=True)


def context(segments: list[dict], quote: str) -> tuple[str, float]:
    """The transcript within AROUND seconds of where the quote is best found, and how much of the quote was found"""
    want = set(WORD.findall(quote.lower()))
    if not want or not segments:
        return '', 0.0
    best, at = 0.0, 0
    for i in range(len(segments)):
        words = set(WORD.findall(' '.join(s['text'] for s in segments[i:i + 3]).lower()))
        score = len(want & words) / len(want)
        if score > best:
            best, at = score, i
    mid = segments[at]['start']
    text = ' '.join(s['text'].strip() for s in segments if s['end'] >= mid - AROUND and s['start'] <= mid + AROUND)
    return text, round(best, 2)


def sample():
    filed = {}
    for e in mi.live(mi.load()):
        for c in e['claims']:
            if c.get('source') == 'shows' and c.get('ref'):
                filed[(c['ref'], mi.key(c['claim']))] = c['claim']
    s = site()
    rows = s.execute("""select c.url, c.claim, c.quote, coalesce(c.speaker, ''), e.show, e.lean, e.date
        from show_claim c join show_episode e on e.url = c.url where c.quote is not null and c.quote <> ''""").fetchall()
    pool = defaultdict(list)
    seen = set()
    for url, claim, quote, speaker, show, lean, date in rows:
        k = (url, mi.key(claim))
        if k in filed and k not in seen:
            seen.add(k)
            pool[speaker if speaker in STRATA else ''].append((url, claim, quote, speaker, show, lean, date))
    rng = random.Random(SEED)
    segments = {}

    def transcript(url: str) -> list[dict]:
        if url not in segments:
            got = s.execute('select t.segments from side_item i join side_transcript t on t.item_id = i.id '
                            'where i.url = ? order by t.created desc limit 1', (url,)).fetchone()
            segments[url] = json.loads(got[0] or '[]') if got else []
        return segments[url]
    con = db()
    con.execute('delete from balaam_items')
    items = []
    for speaker, n in STRATA.items():
        got = 0
        for url, claim, quote, sp, show, lean, date in rng.sample(pool[speaker], len(pool[speaker])):
            text, found = context(transcript(url), quote)
            if found < FOUND:
                continue
            items.append((claim, quote, sp, show, lean, url, date, text, found, int(got < PERSON)))
            got += 1
            if got == n:
                break
        print(f'{speaker or "unmarked"}: {got} of {n} (pool {len(pool[speaker])})')
    s.close()
    rng.shuffle(items)
    con.executemany('insert into balaam_items (id, claim, quote, speaker, show, lean, url, date, context, found, '
                    'person) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [(i + 1, *r) for i, r in enumerate(items)])
    con.commit()
    os.makedirs(NOTES, exist_ok=True)
    out = [{'id': i + 1, 'show': r[3], 'lean': r[4], 'speaker': r[2] or 'not marked', 'claim': r[0], 'quote': r[1],
            'transcript': r[7]} for i, r in enumerate(items)]
    for b in range(0, len(out), BATCH):
        with open(os.path.join(NOTES, f'items-{b // BATCH + 1:02d}.json'), 'w') as f:
            json.dump(out[b:b + BATCH], f, ensure_ascii=False, indent=1)
    print(f'{len(items)} items; {sum(r[9] for r in items)} for the person')


def key():
    con = db()
    at = dt.now().isoformat(timespec='seconds')
    n = Counter()
    drafts = os.path.join(NOTES, 'drafts')
    for name in sorted(os.listdir(drafts)) if os.path.isdir(drafts) else []:
        for r in json.load(open(os.path.join(drafts, name))):
            con.execute('insert or replace into balaam_key values (?, ?, ?, ?, ?)',
                        (r['id'], 'claude', r['stance'], r.get('why', ''), at))
            n['claude'] += 1
    for by, name in (('rule', 'rule.json'), ('close', 'close.json'), ('person', 'person.json')):
        path = os.path.join(NOTES, name)
        if os.path.exists(path):
            for r in json.load(open(path)):
                con.execute('insert or replace into balaam_key values (?, ?, ?, ?, ?)',
                            (r['id'], by, r['stance'], r.get('why', ''), at))
                n[by] += 1
    bad = con.execute(f"select count(*) from balaam_key where stance not in ({','.join('?' * len(STANCES))})",
                      STANCES).fetchone()[0]
    con.commit()
    print(dict(n), f'{bad} answers outside the five stances')


def arms():
    con = db()
    items = con.execute('select id, claim, quote, speaker, show, context from balaam_items order by id').fetchall()
    for arm, (prompt, schema, model) in ARMS.items():
        done = {i for (i,) in con.execute('select id from balaam_answers where arm = ?', (arm,))}
        for n, (i, claim, quote, speaker, show, text) in enumerate(items):
            if i in done:
                continue
            if arm == 'R':
                p = prompt.format(claim=claim, post=quote[:400])
            else:
                p = prompt.format(show=show, speaker=SPEAKER_WORD.get(speaker or '', 'not marked'), context=text,
                                  quote=quote, claim=claim)
            answer = llm.complete_json(p, schema, max_tokens=40, model=model)
            if not answer:
                continue
            stance = FOLD_R.get(answer['stance'], answer['stance']) if arm == 'R' else answer['stance']
            con.execute('insert or replace into balaam_answers values (?, ?, ?, ?, ?)',
                        (arm, i, stance, model, dt.now().isoformat(timespec='seconds')))
            con.commit()
            if n % 20 == 0:
                print(f'{arm}: {n}/{len(items)}', flush=True)


def report():
    con = db()
    items = {r[0]: r for r in con.execute('select id, speaker, person from balaam_items')}
    rows = con.execute('select id, by, stance from balaam_key').fetchall()
    claude = {i: s for i, b, s in rows if b == 'claude'}
    rule = {i: s for i, b, s in rows if b == 'rule'}  # the news-register rule applied to the drafts (rule.json)
    close = {i: s for i, b, s in rows if b == 'close'}  # Claude's own close reading of the 40, for the person (Nov 2)
    person = {i: s for i, b, s in rows if b == 'person'}
    truth = {**claude, **rule, **close, **person}
    for name, second in (('the close reading', close), ('the person', person)):
        both = [i for i in second if i in claude]
        if both:
            same = sum(claude[i] == second[i] for i in both)
            print(f'Readers: the drafts and {name} agree on {same} of {len(both)} ({same / len(both):.0%})')
            for i in both:
                if claude[i] != second[i]:
                    print(f'  {i}: drafts {claude[i]}, {name} {second[i]}')
    if not truth:
        print('No key yet')
        return
    kinds = Counter(truth.values())
    side = sum(kinds[s] for s in ('arguing against it', 'reporting it'))
    print(f'Key: {len(truth)} claims ({len(close)} closely read, {len(person)} by the person) {dict(kinds)}')
    print(f'1. It matters: arguing against or reporting {side} of {len(truth)} ({side / len(truth):.0%}); needs 15%')
    share = {}
    for sp in STRATA:
        ids = [i for i in truth if (items[i][1] or '') == sp]
        if ids:
            share[sp] = sum(truth[i] == 'arguing against it' for i in ids) / len(ids)
            print(f'   {sp or "unmarked"}: {len(ids)}, arguing against {share[sp]:.0%}, '
                  f'{dict(Counter(truth[i] for i in ids))}')
    hg = [i for i in truth if items[i][1] in ('host', 'guest')]
    hg_share = sum(truth[i] == 'arguing against it' for i in hg) / max(1, len(hg))
    print(f'2. Clips: arguing against {share.get("clip", 0):.0%} of clips, {hg_share:.0%} of host and guest claims '
          f'(needs twice)')
    answers = defaultdict(dict)
    for arm, i, s in con.execute('select arm, id, stance from balaam_answers'):
        answers[arm][i] = s
    hard = [i for i in truth if truth[i] in ('arguing against it', 'reporting it')]
    arguing = [i for i in truth if truth[i] == 'arguing against it']
    acc = {}
    for arm in ARMS:
        a = answers.get(arm, {})
        def right(i, a=a, arm=arm):
            want = truth[i]
            return a.get(i) == ('telling it' if arm == 'R' and want == 'reporting it' else want)
        ids = [i for i in truth if i in a]
        if not ids:
            continue
        acc[arm] = (sum(map(right, ids)) / len(ids),
                    sum(map(right, [i for i in hard if i in a])) / max(1, len([i for i in hard if i in a])),
                    sum(map(right, [i for i in arguing if i in a])) / max(1, len([i for i in arguing if i in a])))
        print(f'3/4. {arm}: {acc[arm][0]:.0%} of {len(ids)}; arguing or reporting {acc[arm][1]:.0%}; arguing '
              f'{acc[arm][2]:.0%} (R reads reporting as telling)')
    if 'Q' in acc and 'R' in acc:
        print(f'   Q over R on arguing against: {acc["Q"][2] - acc["R"][2]:+.0%} (needs +10)')
    if 'Q' in acc and 'N' in acc:
        print(f'   N against Q overall: {acc["N"][0] - acc["Q"][0]:+.0%} (within 3 points)')


if __name__ == '__main__':
    {'sample': sample, 'key': key, 'arms': arms, 'report': report}[sys.argv[1]]()
