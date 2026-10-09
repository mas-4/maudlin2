"""G2 group descriptions (Oct 9). The group proposer (motif_proposals.GROUP_PROMPT, Gemma 4 26B) sees a group as its
name and its members; groups now can carry a description (the checker's 📝), none written yet. Here: for each of the
person's groups with at least MIN members, its members split in two; a description drafted by Gemma from one half
(what they have in common, a sentence or two), and the other half asked about, with as many of the nearest motifs
outside the group (by meaning), the same question two ways: 'members' (today, the first half listed) and
'members+description'. Then the halves swap. Measured: how often a member is said to belong and an outsider not
(the outsiders' 'no' is noisy: the person may simply not have grouped them yet). Resumable; caches in EXP."""
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402

OUT = os.path.join(harness.EXP, 'g2_group_descriptions.json')
MIN = 4
WAYS = ['members', 'members+description']

DRAFT = """A person grouped these motifs of our index of recurring story shapes (rumors and narratives about politics \
and public life) together as "{group}":
{members}

In one or two sentences, what do they have in common, the way the person grouping them would put it: what makes a \
motif belong here? Not a list of the members."""
DRAFT_SCHEMA = {"type": "object", "properties": {"description": {"type": "string", "maxLength": 400}},
                "required": ["description"]}
WITH = """A group of motifs a person made in our index of rumor and narrative shapes, "{group}": {description}
Some of its members:
{members}

Does this motif belong in the group, the way its members go together?
{motif}

reason: a sentence
belongs: true or false"""


def plan(index):
    """[(group id, the half listed, the half asked, outsiders asked)] for each group and each way round"""
    from app.narratives import embed
    entries = [e for e in mi.live(index) if e['claims']]
    vecs = embed([mi.described(e) for e in entries])
    vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    at = {e['id']: i for i, e in enumerate(entries)}
    out = []
    rnd = random.Random(9)
    for gid in sorted(index.get('groups', {})):
        members = [e['id'] for e in entries if gid in mi.person_groups(e)]
        if len(members) < MIN:
            continue
        rnd.shuffle(members)
        halves = [members[:len(members) // 2], members[len(members) // 2:]]
        center = vecs[[at[m] for m in members]].mean(0)
        near = [entries[int(i)]['id'] for i in np.argsort(-(vecs @ center)) if entries[int(i)]['id'] not in members]
        for k in (0, 1):
            listed, asked = halves[k], halves[1 - k]
            out.append((gid, listed, asked, near[k * len(asked):(k + 1) * len(asked)]))
    return out


def main():
    index = mi.load()
    E = index['entries']
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    drafts, answers = saved.setdefault('drafts', {}), saved.setdefault('answers', {})
    jobs = plan(index)
    print(f'{len(jobs)} halves of {len({j[0] for j in jobs})} groups', flush=True)
    listing = lambda ids: '\n'.join(f'- {mi.described(E[i])}' for i in ids)  # noqa: E731
    todo = [(f'{g}|{"/".join(sorted(listed))}', g, listed) for g, listed, _, _ in jobs]
    todo = [t for t in todo if t[0] not in drafts]
    for (k, g, listed), a in zip(todo, llm.parallel(lambda t: llm.complete_json(DRAFT.format(
            group=index['groups'][t[1]]['name'], members=listing(t[2])), DRAFT_SCHEMA, max_tokens=300, model=mp.MODEL), todo)):
        if a and a.get('description'):
            drafts[k] = ' '.join(a['description'].split())
    json.dump(saved, open(OUT, 'w'))
    asks = []
    for g, listed, asked, outside in jobs:
        dk = f'{g}|{"/".join(sorted(listed))}'
        for i in asked + outside:
            for way in WAYS:
                key = f'{way}|{dk}|{i}'
                if key not in answers and (way == 'members' or dk in drafts):
                    asks.append((key, way, g, listed, i, dk, i in asked))
    for s in range(0, len(asks), 32):
        part = asks[s:s + 32]

        def one(x):
            key, way, g, listed, i, dk, _ = x
            name = index['groups'][g]['name']
            p = (mp.GROUP_PROMPT.format(group=name, members=listing(listed), motif=mp.shown(E[i])) if way == 'members'
                 else WITH.format(group=name, description=drafts[dk], members=listing(listed), motif=mp.shown(E[i])))
            return llm.complete_json(p, mp.GROUP_SCHEMA, max_tokens=400, model=mp.MODEL)
        for x, a in zip(part, llm.parallel(one, part)):
            if a is not None:
                answers[x[0]] = {'belongs': bool(a.get('belongs')), 'member': x[6]}
        json.dump(saved, open(OUT, 'w'))
        print(f'asked {len(answers)}/{len(answers) + len(asks) - s - len(part)}', flush=True)
    lines = [f'G2 group descriptions, {len({j[0] for j in jobs})} groups of {MIN}+ of the person\'s members, '
             f'each half asked with the other half listed:']
    for way in WAYS:
        got = [v for k, v in answers.items() if k.startswith(way + '|')]
        mem = [v['belongs'] for v in got if v['member']]
        out = [not v['belongs'] for v in got if not v['member']]
        lines.append(f'  {way}: members said to belong {np.mean(mem):.1%} (n {len(mem)}), nearest outsiders kept out '
                     f'{np.mean(out):.1%} (n {len(out)}), balanced {np.mean([np.mean(mem), np.mean(out)]):.1%}')
    for k, d in list(drafts.items())[:6]:
        lines.append(f'  e.g. {index["groups"][k.split("|")[0]]["name"]}: {d[:200]}')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
