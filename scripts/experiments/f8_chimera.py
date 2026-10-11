"""F8 the Chimera: are claims from people's posts several tellings stitched into one? (Oct 11, the person: "I am worried
claims themselves are often too shoved together; we sometimes surface multiple motifs from the posts under a single
claim".) A narrative claim is one sentence the model writes for a whole paraphrase group (app/narratives.py: posts
linked as mutual neighbours above a likeness, the links chained into groups, then 10 of the posts read). Chaining can
join posts that tell different things, and the claim names only what the 10 shown share. The sign of it: claims from
posts sit in 3+ motifs 32% of the time, against 12-17% for the shows, the fact-checkers and the Focus Group.

For narrative claims the person filed in 3+ motifs (stitched, maybe) and in exactly one (the control), Gemma reads up to
POSTS of the claim's posts and lists each distinct claim at least two of them make, with which posts make it. Then, for a
claim it splits, which of its sub-claims tells each of the person's motifs (or none, or all of them):

    split           how often a claim comes apart into 2+ claims, each from 2+ posts: the 3+ motifs against the one
    spread          of the 3+ motif claims split, how often the motifs land on different sub-claims (stitched tellings)
                    rather than all on one (one telling with several layers: an archetype, a plot and a value at once)

    f8_chimera.py ask | report      under the GPU lease (lease 'chimera-ask')"""
import glob
import json
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'f8_chimera.json')
MODEL = 'gemma4:26b'
POSTS = 40
EACH = 80  # claims of each kind
SPLIT_PROMPT = """Posts people wrote, grouped together because they read alike:
{posts}

List each distinct claim at least two of these posts make, with the numbers of the posts that make it. Posts that tell \
the same story or make the same point in different words are one claim; list separate claims only where posts tell a \
different story, accuse someone different, or make a different point. Plain one-sentence claims, as their tellers \
would put them."""
SPLIT_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "maxItems": 8, "items": {
    "type": "object", "properties": {"claim": {"type": "string", "maxLength": 300},
                                     "posts": {"type": "array", "items": {"type": "integer"}}},
    "required": ["claim", "posts"]}}}, "required": ["claims"]}
TELLS_PROMPT = """Claims found in a group of posts:
{claims}

Motifs (recurring story shapes) a folklorist filed the group under:
{motifs}

For each motif, which claim tells it: the claim's number, 0 if none does, or -1 if every claim does alike."""


def tells_schema(n: int) -> dict:
    return {"type": "object", "properties": {"tells": {"type": "array", "minItems": n, "maxItems": n,
                                                       "items": {"type": "integer"}}}, "required": ["tells"]}


def posts_behind(claim: str, index: dict) -> list[dict]:
    """Every post still kept in the paraphrase group a narrative claim came from (as the checker finds it)"""
    from app.narratives import FOLDER, posts_of
    words = mi.originals(claim, index)
    filed = next((c for e in mi.live(index) for c in e['claims'] if c['claim'] == claim), {})
    reports = sorted(glob.glob(os.path.join(FOLDER, 'report-*.json')), reverse=True)
    ref = filed.get('ref', '').replace('-', '').replace('T', '-').replace(':', '')
    for path in [r for r in reports if os.path.basename(r)[7:20].replace('-', '', 2) == ref] + reports:
        try:
            report = json.load(open(path))
        except (OSError, ValueError):
            continue
        group = next((g for g in report.get('found', []) if (g.get('label') or {}).get('narrative') in words), None)
        if group:
            return posts_of(group.get('keys') or [])
    return []


def sample(index: dict) -> dict[str, list[tuple[str, list[str]]]]:
    by = defaultdict(set)
    for e in mi.live(index):
        if 'done' not in e:
            continue
        for c in e['claims']:
            if c.get('source') == 'narrative':
                by[c['claim']].add(e['id'])
    rnd = random.Random(8)
    out = {}
    for kind, test in (('3+ motifs', lambda n: n >= 3), ('one motif', lambda n: n == 1)):
        pool = sorted(c for c, ms in by.items() if test(len(ms)))
        rnd.shuffle(pool)
        out[kind] = [(c, sorted(by[c])) for c in pool]
    return out


def ask():
    index = mi.load()
    state = json.load(open(OUT)) if os.path.exists(OUT) else {}
    got = state.setdefault('claims', {})
    names = {e['id']: e for e in mi.live(index)}
    for kind, pool in sample(index).items():
        done = sum(1 for v in got.values() if v['kind'] == kind)
        for claim, motifs in pool:
            if done >= EACH:
                break
            if claim in got:
                continue
            posts = posts_behind(claim, index)[:POSTS]
            if len(posts) < 4:
                continue
            shown = '\n'.join(f'{n}. {p["text"][:280]}' for n, p in enumerate(posts, 1))
            r = llm.complete_json(SPLIT_PROMPT.format(posts=shown), SPLIT_SCHEMA, max_tokens=1200, model=MODEL)
            if r is None:
                sys.exit('ask: no answer; Ollama down? stopping to try again')
            subs = [s for s in r.get('claims', []) if len(set(s.get('posts') or [])) >= 2]
            row = {'kind': kind, 'motifs': motifs, 'posts': len(posts), 'subs': subs}
            if kind == '3+ motifs' and len(subs) >= 2:
                listed = '\n'.join(f'{n}. {s["claim"]}' for n, s in enumerate(subs, 1))
                ms = '\n'.join(f'- {names[m]["name"]}: {(names[m].get("note") or "")[:200]}' for m in motifs)
                t = llm.complete_json(TELLS_PROMPT.format(claims=listed, motifs=ms), tells_schema(len(motifs)),
                                      max_tokens=100, model=MODEL)
                row['tells'] = (t or {}).get('tells')
            got[claim] = row
            done += 1
            json.dump(state, open(OUT, 'w'))
            print(f'ask: {kind} {done}/{EACH}', flush=True)


def report():
    got = json.load(open(OUT))['claims']
    split = {k: [len(v['subs']) >= 2 for v in got.values() if v['kind'] == k] for k in ('3+ motifs', 'one motif')}
    spread, layered = 0, 0
    for v in got.values():
        tells = [t for t in (v.get('tells') or []) if t > 0]
        if v['kind'] == '3+ motifs' and len(v['subs']) >= 2 and tells:
            if len(set(tells)) >= 2:
                spread += 1
            else:
                layered += 1
    n_subs = [len(v['subs']) for v in got.values() if v['kind'] == '3+ motifs' and len(v['subs']) >= 2]
    line = (f"F8 the Chimera: claims from posts split by Gemma into 2+ claims (each from 2+ posts): those in 3+ motifs "
            f"{np.mean(split['3+ motifs']):.0%} of {len(split['3+ motifs'])}, those in one motif "
            f"{np.mean(split['one motif']):.0%} of {len(split['one motif'])}; of the 3+ split "
            f"({np.mean(n_subs) if n_subs else 0:.1f} claims each), the motifs land on different claims in {spread}, "
            f"all on one in {layered}")
    print(line, flush=True)
    harness.note(line)


def main():
    {'ask': ask, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
