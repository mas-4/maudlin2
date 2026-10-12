"""F20 the Blind Men and the Elephant: the claim writer shown the most varied posts (Oct 12, the person: "pick the ones
with the least embedding similarity, the most diverse set. that way if multiple sides get grouped they show up in the
claim"). Each blind man feels one part; only together do they describe the elephant. Production writes a group's
claim from ten of its posts at random (narratives.describe); here ten chosen as unlike each other as possible
(farthest point by mxbai likeness, from the post nearest the group's centre), on Isis's groups of more than ten posts:

    write     a claim from each ten (random, seeded as production; varied), the production prompt (narratives.label)
    about     Gemma: is each of the group's posts about the claim, one post at a time (narratives.about)
    file      each claim scored against the person's motifs as Isis files (the shortlist's 12, the confidence model)
    report    coverage, the person's motifs reached, motifs past FILE, words: each arm, and the paired difference

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
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f20_blind_men.json')
FILE = isis.FILE  # a motif when its fit is at least this
ARMS = ('random', 'varied')


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
        got = {arm: narratives.label({'examples': ten[arm]}, cache) for arm in ARMS}
        if not all(got.values()):
            print(f'write: no answer for group {n}', flush=True)
            continue
        claims[claim] = {arm: {'shown': ten[arm], 'claim': got[arm].get('narrative') or ''} for arm in ARMS}
        save(state)
        print(f'write: {len(claims)} groups', flush=True)


def about():
    state = saved()
    cache = state.setdefault('about_cache', {})
    every = groups()
    for n, (claim, arms) in enumerate(state['claims'].items()):
        posts = list(dict.fromkeys(every[claim]['posts']))
        for arm in ARMS:
            if 'about' not in arms[arm] and arms[arm]['claim']:
                arms[arm]['about'] = narratives.about({'examples': posts}, arms[arm]['claim'], cache)
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
    texts = sorted({a['claim'] for arms in state['claims'].values() for a in arms.values() if a['claim']})
    scorer.signals.prepare(texts)
    for arms in state['claims'].values():
        for arm in ARMS:
            c = arms[arm]['claim']
            if 'filed' in arms[arm] or not c:
                continue
            ids = scorer.candidates(c)
            p = 1 / (1 + np.exp(-(scorer.rows(c, ids, 'narrative') @ coef + m['bias'])))
            arms[arm]['filed'] = sorted(([eid, round(float(v), 3)] for eid, v in zip(ids, p)), key=lambda x: -x[1])
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
            past = [eid for eid, v in arms[arm]['filed'] if v >= FILE]
            row[arm] = {'about': arms[arm]['about'], 'yours': len(set(past) & set(g['motifs'])), 'motifs': len(past),
                        'words': len(arms[arm]['claim'].split())}
        rows.append(row)
    out = {'groups': len(rows)}
    for part, rs in (('all', rows), ('3+ motifs', [r for r in rows if r['kind'] == '3+ motifs']),
                     ('one motif', [r for r in rows if r['kind'] == 'one motif'])):
        if not rs:
            continue
        out[part] = {'n': len(rs)}
        for measure in ('about', 'yours', 'motifs', 'words'):
            diffs = [r['varied'][measure] - r['random'][measure] for r in rs]
            out[part][measure] = {'random': round(float(np.mean([r['random'][measure] for r in rs])), 3),
                                  'varied': round(float(np.mean([r['varied'][measure] for r in rs])), 3),
                                  'gain': round(float(np.mean(diffs)), 3), 'interval': interval(diffs)}
    state['report'] = out
    save(state)
    a = out['all']
    line = (f"F20 the Blind Men and the Elephant, {out['groups']} groups of 10+ posts, a claim from ten varied posts "
            f"against ten at random: posts about the claim {a['about']['random']:.0%} to {a['about']['varied']:.0%} "
            f"({a['about']['gain']:+.1%}, {a['about']['interval'][0]:+.1%} to {a['about']['interval'][1]:+.1%}); the "
            f"person's motifs reached {a['yours']['random']:.2f} to {a['yours']['varied']:.2f} ({a['yours']['gain']:+.2f}); "
            f"motifs past {FILE} {a['motifs']['random']:.2f} to {a['motifs']['varied']:.2f}; words "
            f"{a['words']['random']:.1f} to {a['words']['varied']:.1f}")
    for part in ('3+ motifs', 'one motif'):
        if part in out:
            line += f"; {part} ({out[part]['n']}): about {out[part]['about']['gain']:+.1%}, yours {out[part]['yours']['gain']:+.2f}"
    print(line, flush=True)
    harness.note(line)


def main():
    {'write': write, 'about': about, 'file': file, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
