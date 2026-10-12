"""F20 the Blind Men and the Elephant: the claim writer shown the most varied posts (Oct 12, the person: "pick the ones
with the least embedding similarity, the most diverse set. that way if multiple sides get grouped they show up in the
claim"). Each blind man feels one part; only together do they describe the elephant. Production writes a group's
claim from ten of its posts at random (narratives.describe); here ten chosen as unlike each other as possible
(farthest point by mxbai likeness, from the post nearest the group's centre), on Isis's groups of more than ten posts:

    write     a claim from each ten (random, seeded as production; varied), the production prompt (narratives.label);
              and a third arm (added before any run, from the person's handoff of Oct 12): the varied ten with a
              multi-claim output, one to four claims each in its own side's voice with the posts that make it (the
              Chimera's split prompt, tightened): varied sampling alone may make umbrella claims worse
    about     Gemma: is each of the group's posts about the claim, one post at a time (narratives.about, its cache);
              for the split arm a post counts when it is about any of its claims
    file      each claim scored against the person's motifs as Isis files (the shortlist's 12, the confidence model)
    report    coverage, groups passing production's half-about check, the person's motifs reached, motifs past FILE
              per claim, words per claim: each arm, and the paired differences

    f20_blind_men.py write | about | file | report      under the GPU lease (leases 'blind-men-…')
The paper is ~/maudlin-data/papers/the-blind-men-and-the-elephant.md."""
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f9_isis as isis  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app import narratives  # noqa: E402
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f20_blind_men.json')
FILE = isis.FILE  # a motif when its fit is at least this
ARMS = ('random', 'varied', 'split')
SPLIT_PROMPT = """Posts people wrote, grouped together because they read alike:
{posts}

What do these posts claim? Give one to four claims. Posts that tell the same story or make the same point in different \
words are one claim; give separate claims only where posts tell a different story, accuse someone different, or take \
the other side. Each claim is one side's assertion in that side's own voice, a plain sentence as its tellers would put \
it; where posts argue, give each side's claim, never a sentence about the argument. With each, the numbers of the \
posts that make it."""
SPLIT_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "minItems": 1, "maxItems": 4, "items": {
    "type": "object", "properties": {"claim": {"type": "string", "maxLength": 300},
                                     "posts": {"type": "array", "items": {"type": "integer"}}},
    "required": ["claim", "posts"]}}}, "required": ["claims"]}


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


def varied(texts: list[str], vec: np.ndarray, n: int) -> list[str]:
    """n texts as unlike each other as can be: the one nearest the centre, then each time the one least like any taken"""
    centre = vec.mean(0)
    taken = [int(np.argmax(vec @ centre))]
    nearest = vec @ vec[taken[0]]
    while len(taken) < min(n, len(texts)):
        nearest[taken] = np.inf
        i = int(np.argmin(nearest))
        taken.append(i)
        nearest = np.maximum(nearest, vec @ vec[i])
    return [texts[i] for i in taken]


def groups() -> dict:
    """Isis's groups of more than SAMPLE distinct posts: claim -> {'posts', 'motifs', 'kind'}"""
    return {c: g for c, g in isis.saved()['groups'].items() if len(dict.fromkeys(g['posts'])) > narratives.SAMPLE}


def write():
    state = saved()
    claims = state.setdefault('claims', {})
    cache = state.setdefault('label_cache', {})
    for n, (claim, g) in enumerate(groups().items()):
        if claim in claims:
            continue
        texts = list(dict.fromkeys(g['posts']))
        ten = {'random': random.Random(n).sample(texts, narratives.SAMPLE),
               'varied': varied(texts, narratives.embed(texts), narratives.SAMPLE)}
        got = {arm: narratives.label({'examples': ten[arm]}, cache) for arm in ('random', 'varied')}
        split = llm.complete_json(SPLIT_PROMPT.format(posts='\n'.join(f'{i}. {t[:280]}' for i, t in enumerate(ten['varied'], 1))),
                                  SPLIT_SCHEMA, max_tokens=900, model=narratives.LABEL_MODEL)
        if not all(got.values()) or not split or not split.get('claims'):
            print(f'write: no answer for group {n}', flush=True)
            continue
        claims[claim] = {arm: {'shown': ten[arm], 'claims': [got[arm].get('narrative') or '']} for arm in ('random', 'varied')}
        claims[claim]['split'] = {'shown': ten['varied'], 'claims': [c['claim'] for c in split['claims'] if c.get('claim')],
                                  'posts': [c.get('posts', []) for c in split['claims'] if c.get('claim')]}
        save(state)
        print(f'write: {len(claims)} groups', flush=True)


def about():
    state = saved()
    cache = state.setdefault('about_cache', {})
    every = groups()
    for n, (claim, arms) in enumerate(state['claims'].items()):
        posts = list(dict.fromkeys(every[claim]['posts']))
        for arm in ARMS:  # each post asked about each claim alone (narratives.about's own cache keys)
            if 'about' not in arms[arm] and any(arms[arm]['claims']):
                arms[arm]['about'] = [[narratives.about({'examples': [p]}, c, cache) for p in posts]
                                      for c in arms[arm]['claims'] if c]
        if n % 5 == 0:
            save(state)
            print(f'about: {n + 1}/{len(state["claims"])}', flush=True)
    save(state)


def file():
    state = saved()
    index = mi.load()
    m = fc.model()
    if not m:
        sys.exit('file: no confidence model')
    coef = np.array([m['weights'][f] for f in fc.FEATURES])
    scorer = fc.Scorer(index, mr.weights())
    texts = sorted({c for arms in state['claims'].values() for a in arms.values() for c in a['claims'] if c})
    scorer.signals.prepare(texts)
    for arms in state['claims'].values():
        for arm in ARMS:
            if 'filed' in arms[arm]:
                continue
            arms[arm]['filed'] = []
            for c in arms[arm]['claims']:
                ids = scorer.candidates(c) if c else []
                p = 1 / (1 + np.exp(-(scorer.rows(c, ids, 'narrative') @ coef + m['bias']))) if ids else []
                arms[arm]['filed'].append(sorted(([eid, round(float(v), 3)] for eid, v in zip(ids, p)), key=lambda x: -x[1]))
        save(state)
    scorer.signals.save()


def interval(diffs: list[float]) -> tuple[float, float]:
    rnd = np.random.default_rng(14)
    d = np.array(diffs)
    means = [d[rnd.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    return round(float(np.percentile(means, 2.5)), 3), round(float(np.percentile(means, 97.5)), 3)


def report():
    state = saved()
    every = groups()
    rows = []
    for claim, arms in state['claims'].items():
        if not all('about' in arms[a] and 'filed' in arms[a] for a in ARMS):
            continue
        g, row = every[claim], {'kind': every[claim]['kind']}
        for arm in ARMS:
            votes = np.array(arms[arm]['about'], dtype=float)  # claims x posts
            covered = float(votes.max(0).mean()) if votes.size else 0.0  # about any of its claims
            pasts = [[eid for eid, v in f if v >= FILE] for f in arms[arm]['filed']]
            texts = [c for c in arms[arm]['claims'] if c]
            row[arm] = {'about': covered, 'pass': float(covered >= narratives.ABOUT_SHARE),
                        'yours': len(set().union(*map(set, pasts)) & set(g['motifs'])),
                        'motifs': float(np.mean([len(x) for x in pasts])) if pasts else 0.0,
                        'claims': len(texts), 'words': float(np.mean([len(c.split()) for c in texts])) if texts else 0.0}
        rows.append(row)
    out = {'groups': len(rows)}
    for part, rs in (('all', rows), ('3+ motifs', [r for r in rows if r['kind'] == '3+ motifs']),
                     ('one motif', [r for r in rows if r['kind'] == 'one motif'])):
        if not rs:
            continue
        out[part] = {'n': len(rs)}
        for measure in ('about', 'pass', 'yours', 'motifs', 'claims', 'words'):
            out[part][measure] = {arm: round(float(np.mean([r[arm][measure] for r in rs])), 3) for arm in ARMS}
            for arm in ('varied', 'split'):  # each against the random ten, paired
                diffs = [r[arm][measure] - r['random'][measure] for r in rs]
                out[part][measure][f'{arm} gain'] = round(float(np.mean(diffs)), 3)
                out[part][measure][f'{arm} interval'] = interval(diffs)
    state['report'] = out
    save(state)
    a = out['all']
    arms = lambda m, f: ' / '.join(format(a[m][arm], f) for arm in ARMS)  # noqa: E731
    line = (f"F20 the Blind Men and the Elephant, {out['groups']} groups of 10+ posts, random ten / varied ten / varied "
            f"ten split into 1-4 claims: posts about a claim {arms('about', '.0%')} (varied "
            f"{a['about']['varied gain']:+.1%}, {a['about']['varied interval'][0]:+.1%} to {a['about']['varied interval'][1]:+.1%}; "
            f"split {a['about']['split gain']:+.1%}, {a['about']['split interval'][0]:+.1%} to {a['about']['split interval'][1]:+.1%}); "
            f"groups passing the half-about check {arms('pass', '.0%')}; the person's motifs reached {arms('yours', '.2f')}; "
            f"motifs past {FILE} a claim {arms('motifs', '.2f')}; claims {arms('claims', '.1f')}; words a claim {arms('words', '.1f')}")
    for part in ('3+ motifs', 'one motif'):
        if part in out:
            line += (f"; {part} ({out[part]['n']}): about varied {out[part]['about']['varied gain']:+.1%}, split "
                     f"{out[part]['about']['split gain']:+.1%}")
    print(line, flush=True)
    harness.note(line)


def main():
    {'write': write, 'about': about, 'file': file, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
