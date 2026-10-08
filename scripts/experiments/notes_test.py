"""Two tests of leaning on the person's scope notes rather than motif names (Oct 8; the person: "the names are almost
fancy little jokes, the description is important").

1. shortlist: motif_retriever.FACTS vs FACTS + 'note alone' (the note's embedding against the claim's), each claim
   held out of training (grouped folds) and of its motifs; how many of the person's motifs for it are in the top 8 / 12.
2. judge: motif_index.REUSE_PROMPT as now vs a prompt that defines each motif by its note (the name a nickname) and
   shows its three claims nearest this one, on a sample of confirmed claims with the same shortlist; recall of the
   person's motifs among the picks, and how many picks were not theirs. Resumable (judge part saved per claim)."""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

HERE = '/home/mas/maudlin-data/motifs/experiments'
OUT = os.path.join(HERE, 'notes_test.json')

NOTE_PROMPT = """Today is {today}. A claim people are telling or arguing over:
{claim}

Motifs in our index of recurring rumor and narrative shapes. Each is defined by its description; its name is only a \
nickname, often a playful one, so don't match on the name. Under each, the claims filed under it most like this one:
{options}

Which of these motifs is this claim clearly another instance of: the same kind of story as the motif's description \
says, told about other people, places or years? A shared topic, person or place alone isn't enough. Most claims fit \
one or two; if none fits clearly, give none.

reason: a sentence or two
fits: the numbers of the motifs it clearly fits (none to three)"""


def truth_sets(index):
    entries = [e for e in mi.live(index) if e['claims'] and e.get('done')]
    truth, text = defaultdict(set), {}
    for n, e in enumerate(entries):
        for c in e['claims']:
            if c.get('checked') == 'yes':
                truth[mi.key(c['claim'])].add(n)
                text[mi.key(c['claim'])] = c['claim']
    return entries, truth, text


def note_alone(entries, claim, vec):
    q = vec([claim])[0]
    return vec([e.get('note') or e['name'] for e in entries]) @ q


def shortlist_test():
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    index = mi.load()
    entries, truth, text = truth_sets(index)
    vec = mr.Vectors()
    keys = list(truth)
    F = {k: mr.facts(entries, text[k], vec, leave_out=True) for k in keys}
    N = {k: note_alone(entries, text[k], vec) for k in keys}
    out = {}
    for label, build in (('today', lambda k: F[k]), ('+ note alone', lambda k: np.column_stack([F[k], N[k]]))):
        hits8 = hits12 = total = 0
        for tr, te in GroupKFold(5).split(keys, groups=keys):
            X = np.concatenate([build(keys[i]) for i in tr])
            y = np.concatenate([[m in truth[keys[i]] for m in range(len(entries))] for i in tr])
            mu, sd = X.mean(0), X.std(0) + 1e-9
            model = LogisticRegression(max_iter=2000, class_weight='balanced').fit((X - mu) / sd, y)
            for i in te:
                s = model.decision_function((build(keys[i]) - mu) / sd)
                order = list(np.argsort(-s))
                hits8 += len(truth[keys[i]] & set(order[:8]))
                hits12 += len(truth[keys[i]] & set(order[:12]))
                total += len(truth[keys[i]])
        out[label] = {'top 8': round(hits8 / total, 3), 'top 12': round(hits12 / total, 3), 'filings': total}
        print('shortlist', label, out[label], flush=True)
    return out


def judge_test(sample=120, seed=3):
    index = mi.load()
    entries, truth, text = truth_sets(index)
    vec = mr.Vectors()
    w = mr.weights()
    rng = np.random.default_rng(seed)
    keys = sorted(truth)
    keys = [keys[i] for i in rng.permutation(len(keys))[:sample]]
    done = json.load(open(OUT)) if os.path.exists(OUT) else {}
    done.setdefault('judge', {})
    today = datetime.now().strftime('%B %-d, %Y')
    for k in keys:
        if k in done['judge']:
            continue
        claim = text[k]
        F = mr.facts(entries, claim, vec, leave_out=True)
        s = F @ np.array([w['weights'][f] for f in mr.FACTS]) + w['bias']
        shown = [int(i) for i in np.argsort(-s)[:12]]
        q = vec([claim])[0]
        res = {}
        for label in ('today', 'notes'):
            parts = []
            for n, m in enumerate(shown, 1):
                e = entries[m]
                own = [c['claim'] for c in e['claims'] if mi.key(c['claim']) != k]
                if label == 'today':
                    parts.append(f'{n}. {mi.described(e)}\n' + '\n'.join(f'   - {c[:160]}' for c in own[-3:]))
                else:
                    near = [own[i] for i in np.argsort(-(vec(own) @ q))[:3]] if own else []
                    parts.append(f'{n}. {e.get("note") or "(no description yet)"} (nicknamed “{e["name"]}”)\n'
                                 + '\n'.join(f'   - {c[:160]}' for c in near))
            prompt = (mi.REUSE_PROMPT if label == 'today' else NOTE_PROMPT).format(today=today, claim=claim, options='\n'.join(parts))
            schema = {"type": "object", "properties": {
                "reason": {"type": "string", "maxLength": 1000},
                "fits": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": len(shown)}}},
                "required": ["reason", "fits"]}
            a = llm.complete_json(prompt, schema, max_tokens=900, model=mi.JUDGE_MODEL) or {}
            res[label] = [shown[n - 1] for n in dict.fromkeys(a.get('fits', [])) if isinstance(n, int) and 1 <= n <= len(shown)]
        done['judge'][k] = {'truth': sorted(truth[k]), 'in_shortlist': sorted(truth[k] & set(shown)), **res}
        json.dump(done, open(OUT, 'w'))
        print(f"judge {len(done['judge'])}/{len(keys)}", flush=True)
    for label in ('today', 'notes'):
        rows = [done['judge'][k] for k in keys if k in done['judge']]
        found = sum(len(set(r[label]) & set(r['truth'])) for r in rows)
        reach = sum(len(r['in_shortlist']) for r in rows)
        picks = sum(len(r[label]) for r in rows)
        print(f'judge {label}: found {found} of {reach} of the person\'s motifs in the shortlist ({found / max(reach, 1):.0%}); '
              f'{picks - found} of {picks} picks not theirs ({(picks - found) / max(picks, 1):.0%})', flush=True)


if __name__ == '__main__':
    if 'shortlist' in sys.argv:
        r = shortlist_test()
        d = json.load(open(OUT)) if os.path.exists(OUT) else {}
        d['shortlist'] = r
        json.dump(d, open(OUT, 'w'))
    if 'judge' in sys.argv:
        judge_test()
