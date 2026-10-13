"""F9 Isis: file single posts, then let the motifs do the grouping (Oct 11, the person: "Lets try running on single
posts even and then seeing if we can reverse group by motif"). Isis gathered Osiris's scattered pieces back into one
body; here the pieces are posts. Today a group of posts comes first (paraphrase groups, app/narratives.py), then one
claim for the group, then the claim's motifs; the Chimera asks whether those groups stitch several tellings together.
Isis turns it round: each post its own claim, filed on its own, and the motifs make the groups.

On the posts behind the Chimera's claims (from Bluesky and Mastodon, filed by the person in 3+ motifs or in one):

    ask       Gemma writes each post's claim in one sentence, or none (a post that claims nothing: a joke without a
              claim, a reaction, a link)
    file      each post's claim scored against the person's motifs as the filing would (the shortlist's 12 best, the
              confidence model's chance the person keeps each); a post goes to its best motif when that's past FILE
    report    within a claim's posts, how many different motifs they go to (3+ motifs claims against one-motif ones);
              how many of the person's motifs for the claim some post reaches, and how many of the posts land in one of
              them; and the reverse groups: motifs that gather posts from several of today's groups. Also, after
              Fable (Oct 12): read at the lines 0.3 and 0.7 too; and for groups whose posts reach 2+ of the person's
              motifs, whether some post carries 2+ of them (layers of one telling) or each post one (stitched)

    f9_isis.py ask | file | report      under the GPU lease (lease 'isis-ask', 'isis-file')"""
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import f8_chimera as f8  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f9_isis.json')
MODEL = 'gemma4:26b'
FILE = 0.5  # the confidence model's chance the person keeps it, for a post to go to a motif
LINES = (0.3, 0.5, 0.7)  # the report read at these too: the model has never seen a single post (Fable)
PROMPT = """A post someone wrote:
{post}

If it claims something (says what happened, what someone is, what's really going on, or what should be done), write that \
claim in one plain sentence, as its writer would put it, the subject named. If it claims nothing (a reaction, a joke with \
no claim in it, a bare link or question), say none."""
SCHEMA = {"type": "object", "properties": {"claim": {"type": "string", "maxLength": 300}, "none": {"type": "boolean"}},
          "required": ["claim", "none"]}


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


def ask():
    index = mi.load()
    state = saved()
    groups = state.setdefault('groups', {})
    for kind, pool in f8.sample(index).items():
        for claim, motifs in pool[:f8.EACH]:
            if claim not in groups:
                posts = f8.posts_behind(claim, index)[:f8.POSTS]
                if len(posts) >= 4:
                    groups[claim] = {'kind': kind, 'motifs': motifs, 'posts': [p['text'][:600] for p in posts]}
    save(state)
    said = state.setdefault('said', {})
    todo = list(dict.fromkeys(t for g in groups.values() for t in g['posts'] if t not in said))
    print(f'ask: {len(groups)} groups, {len(todo)} posts to read', flush=True)
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        got = llm.parallel(lambda t: llm.complete_json(PROMPT.format(post=t), SCHEMA, max_tokens=150, model=MODEL), part)
        if not any(got):
            sys.exit('ask: no answer for a whole batch; Ollama down? stopping to try again')
        for t, r in zip(part, got):
            if r is not None:
                said[t] = None if r.get('none') or not (r.get('claim') or '').strip() else ' '.join(r['claim'].split())
        save(state)
        print(f'ask: {min(start + 32, len(todo))}/{len(todo)}', flush=True)


CHUNK = 50  # claims asked about between saves


def file():
    index = mi.load()
    state = saved()
    m = fc.model()
    if not m:
        sys.exit('file: no confidence model')
    coef = np.array([m['weights'][f] for f in fc.FEATURES])
    scorer = fc.Scorer(index, mr.weights())
    claims = sorted({c for c in state['said'].values() if c})
    # the filing model's questions a chunk at a time, kept after each: the hourly run stops this step every hour, and
    # prepare() keeps its answers only at the end (Oct 12-13: six tries, each lost at the hour, nothing filed)
    for i in range(0, len(claims), CHUNK):
        chunk = [c for c in claims[i:i + CHUNK] if mi.key(c) not in scorer.signals.layered]
        if chunk:
            scorer.signals.prepare(chunk)
            scorer.signals.save()
            print(f'file: asked {min(i + CHUNK, len(claims))}/{len(claims)}', flush=True)
    scorer.signals.prepare(claims, ask=False)
    filed = state.setdefault('filed', {})
    for n, c in enumerate(claims):
        if c in filed:
            continue
        ids = scorer.candidates(c)
        p = 1 / (1 + np.exp(-(scorer.rows(c, ids, 'narrative') @ coef + m['bias'])))
        filed[c] = sorted(([eid, round(float(v), 3)] for eid, v in zip(ids, p)), key=lambda x: -x[1])[:3]
        if n % 50 == 0:
            scorer.signals.save()
            save(state)
            print(f'file: {n}/{len(claims)}', flush=True)
    scorer.signals.save()
    save(state)


def tally(state: dict, line: float) -> dict:
    """The report's numbers with a post going to its best motif when the fit is at least `line`."""
    said, filed = state['said'], state['filed']

    def motifs_of(post: str) -> list[str]:  # every motif past the line among the post's top 3, best first
        c = said.get(post)
        return [eid for eid, v in (filed.get(c) or []) if v >= line] if c else []
    spread = defaultdict(list)  # kind -> distinct motifs a group's posts go to
    reach, onto, claimless, unfiled = [], [], [], []
    layered = stitched = 0  # groups whose posts reach 2+ of the person's motifs: in one post, or only across posts
    gather = defaultdict(set)  # motif -> the groups whose posts it gathers
    for claim, g in state['groups'].items():
        posts = [t for t in g['posts'] if t in said]
        claimless.append(np.mean([said[t] is None for t in posts]) if posts else 0)
        tops = [motifs_of(t) for t in posts]
        placed = [m[0] for m in tops if m]
        unfiled.append(1 - len(placed) / max(1, sum(1 for t in posts if said.get(t))))
        spread[g['kind']].append(len(set(placed)))
        if placed:
            reach.append(len(set(placed) & set(g['motifs'])) / len(g['motifs']))
            onto.append(np.mean([x in g['motifs'] for x in placed]))
        theirs = [set(m) & set(g['motifs']) for m in tops]
        if len(set().union(*theirs, set())) >= 2:
            if any(len(x) >= 2 for x in theirs):
                layered += 1
            else:
                stitched += 1
        for x in placed:
            gather[x].add(claim)
    return {'line': line, 'groups': {k: len(v) for k, v in spread.items()},
            'distinct motifs a group': {k: round(float(np.mean(v)), 2) for k, v in spread.items()},
            'claimless posts': round(float(np.mean(claimless)), 3),
            'claimless by kind': {k: round(float(np.mean([c for c, g in zip(claimless, state['groups'].values())
                                                          if g['kind'] == k])), 3) for k in spread},
            'claims unfiled': round(float(np.mean(unfiled)), 3),
            "person's motifs reached": round(float(np.mean(reach)), 3) if reach else 0,
            "posts onto the person's motifs": round(float(np.mean(onto)), 3) if onto else 0,
            'layered groups': layered, 'stitched groups': stitched,
            'motifs gathering 2+ groups': sum(1 for gs in gather.values() if len(gs) >= 2), 'motifs reached': len(gather),
            'biggest gatherings': Counter({m: len(g) for m, g in gather.items()}).most_common(10)}


def report():
    state = saved()
    out = tally(state, FILE)
    out['at other lines'] = {str(x): {k: v for k, v in tally(state, x).items() if k != 'biggest gatherings'}
                             for x in LINES if x != FILE}
    state['report'] = out
    save(state)
    reached, landed = out["person's motifs reached"], out["posts onto the person's motifs"]
    line = (f"F9 Isis: {sum(out['groups'].values())} groups of posts, each post filed on its own; "
            f"{out['claimless posts']:.0%} of posts claim nothing, {out['claims unfiled']:.0%} of the rest go to no motif; "
            f"a group's posts go to {out['distinct motifs a group'].get('3+ motifs', 0)} different motifs where the person "
            f"filed its claim in 3+, {out['distinct motifs a group'].get('one motif', 0)} where in one; the posts reach "
            f"{reached:.0%} of the person's motifs for the claim, and {landed:.0%} of the posts filed land in one of them; "
            f"{out['motifs gathering 2+ groups']} of {out['motifs reached']} motifs gather posts from 2+ groups (the "
            f"reverse grouping); of groups whose posts reach 2+ of the person's motifs, {out['layered groups']} have a "
            f"post carrying 2+ (layers of one telling), {out['stitched groups']} only across posts (stitched)")
    for x, t in out['at other lines'].items():
        reached, landed = t["person's motifs reached"], t["posts onto the person's motifs"]
        line += f"; at {x}: reach {reached:.0%}, onto {landed:.0%}, unfiled {t['claims unfiled']:.0%}"
    print(line, flush=True)
    harness.note(line)


def main():
    {'ask': ask, 'file': file, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
