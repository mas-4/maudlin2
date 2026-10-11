"""S1 when a story's news is a new story (Oct 11, the person: the diesel deal and Trump's call for Ukraine to replace
Zelensky "seem like 2 different stories; our sagas could be richer if we don't fold them together"). A story is kept
for days because each hour's cluster continues the story holding most of its headlines, so new articles about a new
event join the old story whenever a few of its headlines are still on front pages. By meaning alone the two don't
separate (the Zelensky headlines sit 0.92 from the deal's: they still say "diesel deal"), so a yes or no: do the new
articles report a new event (someone's new action, statement or decision, or a new outcome), or the same one updated?
The person's line (Oct 11): Pike on a ventilator, Pike discharged and the prison chief resigning are three stories;
handcuffs removed and walking and eating are updates.

Stages:
    s1_story_splits.py draft    every day-to-day transition in the long stories; Gemma 26B's call on each (the draft
                                answer key for the person to correct)
    s1_story_splits.py judge    Nimble 9B's yes or no on each, and Gemma's, against the person's answers
Resumable; caches in EXP."""
import json
import os
import random
import sqlite3
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import d1_definition_swap as d1  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402
from app.utils import Config  # noqa: E402

OUT = os.path.join(harness.EXP, 's1_story_splits.json')
SHOWN = 8  # headlines on each side
MIN_NEW = 15  # new articles a day needs to count as a transition (89 in 50 stories on Oct 11)
DEFINITION = ("A new event is someone's new action, statement or decision that is itself reported as news (Trump "
              "calls for Ukraine to replace Zelensky; Zelensky answers him; the prison chief resigns), or a new "
              "outcome (the inmate is discharged from hospital). The same event updated is new details, status, "
              "numbers or condition (still on a ventilator; handcuffs removed; walking and eating), commentary, "
              "analysis and explainers.")
PROMPT = """A news story's earlier headlines:
{before}

New articles that joined it on {day}:
{new}

{definition}

Do the new articles report a new event, which would be a story of its own (the next part of the saga), or the same
event updated?

reason: a sentence
new: true for a new event
event: the new event in a few words, or \"\""""
SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 400}, "new": {"type": "boolean"},
                                           "event": {"type": "string", "maxLength": 120}},
          "required": ["reason", "new", "event"]}
QUESTION = f'Do the new articles report a new event, a story of its own, rather than the same event updated? {DEFINITION}'


def transitions() -> list[dict]:
    """[{key, story, label, day, before: [titles], new: [titles]}]: each later day of a story with MIN_NEW new
    articles (not ones first seen earlier and re-headlined), against the story's headlines from before that day"""
    db = sqlite3.connect(f'file:{os.path.join(Config.data, "data.db")}?mode=ro', uri=True)
    rows = db.execute('''select sh.story_id, s.label, h.first_accessed, h.title, a.first_accessed
                         from story_headline sh join story s on s.id = sh.story_id join headline h on h.id = sh.headline_id
                         join article a on a.id = h.article_id order by h.first_accessed''').fetchall()
    by = defaultdict(list)
    label = {}
    for sid, lab, seen, title, art in rows:
        by[sid].append((seen, ' '.join(title.split()), art[:10] == seen[:10]))
        label[sid] = lab
    out = []
    for sid, hs in by.items():
        days = sorted({s[:10] for s, _, _ in hs})
        for d in days[1:]:
            new = list(dict.fromkeys(t for s, t, fresh in hs if s[:10] == d and fresh))
            before = list(dict.fromkeys(t for s, t, _ in hs if s[:10] < d))
            if len(new) >= MIN_NEW:
                rnd = random.Random(f'{sid}|{d}')
                out.append({'key': f'{sid}|{d}', 'story': sid, 'label': label[sid], 'day': d,
                            'before': before[-SHOWN:], 'new': sorted(rnd.sample(new, min(SHOWN, len(new))))})
    return out


def block(titles: list[str]) -> str:
    return '\n'.join(f'- {t[:200]}' for t in titles)


def draft(saved, ts):
    got = saved.setdefault('gemma', {})
    todo = [t for t in ts if t['key'] not in got]
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        for t, a in zip(part, llm.parallel(lambda t: llm.complete_json(PROMPT.format(
                before=block(t['before']), day=t['day'], new=block(t['new']), definition=DEFINITION), SCHEMA,
                max_tokens=500, model=ms.JUDGE_MODEL), part)):
            if a:
                got[t['key']] = a
        json.dump(saved, open(OUT, 'w'))
        print(f'drafted {len(got)}/{len(ts)}', flush=True)


def judge(saved, ts):
    from sklearn.metrics import roc_auc_score
    got = saved.setdefault('nimble', {})
    todo = [t for t in ts if t['key'] not in got]
    states = [(t['key'], f"Earlier headlines:\n{block(t['before'])}\n\nNew articles on {t['day']}:\n{block(t['new'])}")
              for t in todo]
    for (k, _), v in zip(states, llm.parallel(lambda x: d1.nimble(x[1], QUESTION), states)):
        if v is not None:
            got[k] = v
    json.dump(saved, open(OUT, 'w'))
    person = saved.get('person', {})
    ks = [t['key'] for t in ts if t['key'] in person and t['key'] in got and t['key'] in saved.get('gemma', {})]
    if not ks:
        print('no answers from the person yet', flush=True)
        return
    y = np.array([person[k] for k in ks], dtype=bool)
    nim = np.array([got[k] for k in ks])
    gem = np.array([saved['gemma'][k]['new'] for k in ks], dtype=bool)
    lines = [f'S1 new event or update, {len(ks)} transitions the person answered ({int(y.sum())} new events):',
             f'  Gemma 26B (the draft): agrees on {np.mean(gem == y):.0%}; new events found {np.mean(gem[y]):.0%}, '
             f'updates called new {np.mean(gem[~y]):.0%}',
             f'  Nimble 9B: AUC {roc_auc_score(y, nim):.3f}; at 0.5 agrees on {np.mean((nim >= 0.5) == y):.0%}']
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def main():
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    ts = transitions()
    print(f'{len(ts)} transitions in {len({t["story"] for t in ts})} stories', flush=True)
    if 'judge' in sys.argv:
        judge(saved, ts)
    else:
        draft(saved, ts)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
