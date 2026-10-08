"""Does a Gemma yes/no judge (with its probability) sort the person's filing decisions better than the similarity
features? Each of the 728 decided (claim, motif) pairs in the person's done motifs is put to gemma4:26b; P(yes) from
the first answer token's log-probabilities. Saved as it goes (resumable)."""
import json
import math
import os
import sys
import time

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join('/home/mas/maudlin-data/motifs/experiments', 'judge_test.json')
MODEL = 'gemma4:26b'
PROMPT = """Our motif index files claims people make about politics and public life under motifs: recurring shapes of \
story, named as reusable framings, so the same story told about other people or another year lands in the same motif.

Motif: {name}
What it covers: {note}
Some claims filed under it:
{examples}

Claim: {claim}

Is this claim an instance of this motif: the same shape of story, as its tellers tell it, not just the same topic, \
person or word? Answer yes or no."""


def p_yes(prompt: str) -> float | None:
    r = rq.post('http://localhost:11434/api/chat', timeout=300, json={
        'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}], 'think': False, 'stream': False,
        'logprobs': True, 'top_logprobs': 10, 'options': {'temperature': 0, 'num_predict': 1}})
    r.raise_for_status()
    lp = (r.json().get('logprobs') or [{}])[0]
    yes = no = -math.inf
    for t in lp.get('top_logprobs') or []:
        w = t['token'].strip().lower()
        if w.startswith('yes'):
            yes = max(yes, t['logprob'])
        elif w.startswith('no'):
            no = max(no, t['logprob'])
    if yes == -math.inf and no == -math.inf:
        return None
    return 1 / (1 + math.exp(no - yes)) if yes > -math.inf and no > -math.inf else (1.0 if yes > no else 0.0)


def main(limit: int | None = None):
    index = mi.load()
    E = index['entries']
    pairs = fc.labeled(index)
    done = json.load(open(OUT)) if os.path.exists(OUT) else {}
    vec = mr.Vectors()
    started, n = time.time(), 0
    for claim, eid, source, kept in pairs[:limit]:
        k = f'{mi.key(claim)}|{eid}'
        if k in done:
            continue
        e = E[eid]
        own = [c['claim'] for c in e['claims'] if mi.key(c['claim']) != mi.key(claim)]
        if own:
            sims = vec(own) @ vec([claim])[0]
            own = [own[i] for i in np.argsort(-sims)[:3]]
        prompt = PROMPT.format(name=e['name'], note=e.get('note') or '(no note yet)',
                               examples='\n'.join(f'- {c}' for c in own) or '(none yet)', claim=claim)
        done[k] = {'p': p_yes(prompt), 'kept': kept, 'claim': claim, 'id': eid, 'source': source}
        n += 1
        if n % 20 == 0:
            json.dump(done, open(OUT, 'w'))
            print(f'{len(done)}/{len(pairs)} ({(time.time() - started) / n:.2f} s each)', flush=True)
    json.dump(done, open(OUT, 'w'))
    print(f'done: {len(done)}', flush=True)
    return len(done) >= len(pairs[:limit])


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
