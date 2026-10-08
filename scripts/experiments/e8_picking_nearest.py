"""E8 The picking prompt with nearest claims only (docs/filing-experiments.md): today's side-by-side prompt
(motif_index.REUSE_PROMPT, each motif as "Name (note)"), each motif shown with its three claims nearest the claim
instead of its latest three; the same 120 confirmed claims and shortlists as E0.4 (notes_test.json), against its
saved answers for today's prompt. Resumable."""
import json
import os
import sys
from datetime import datetime

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
from notes_test import OUT, truth_sets  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

if __name__ == '__main__':
    with open(OUT) as f:
        saved = json.load(f)
    index = mi.load()
    entries, truth, text = truth_sets(index)
    vec = mr.Vectors()
    w = mr.weights()
    today = datetime.now().strftime('%B %-d, %Y')
    rows = saved['judge']
    for i, (k, r) in enumerate(rows.items()):
        if 'nearest' in r or k not in text:
            continue
        claim = text[k]
        F = mr.facts(entries, claim, vec, leave_out=True)
        s = F @ np.array([w['weights'][f] for f in mr.FACTS]) + w['bias']
        shown = [int(j) for j in np.argsort(-s)[:12]]
        q = vec([claim])[0]
        schema = {"type": "object", "properties": {
            "reason": {"type": "string", "maxLength": 1000},
            "fits": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": len(shown)}}},
            "required": ["reason", "fits"]}
        for label in ('latest', 'nearest'):  # both on the same shortlist (the weights have retrained since E0.4)
            parts = []
            for n, m in enumerate(shown, 1):
                own = [c['claim'] for c in entries[m]['claims'] if mi.key(c['claim']) != k]
                pick3 = own[-3:] if label == 'latest' else ([own[j] for j in np.argsort(-(vec(own) @ q))[:3]] if own else [])
                parts.append(f'{n}. {mi.described(entries[m])}\n' + '\n'.join(f'   - {c[:160]}' for c in pick3))
            a = llm.complete_json(mi.REUSE_PROMPT.format(today=today, claim=claim, options='\n'.join(parts)), schema,
                                  max_tokens=900, model=mi.JUDGE_MODEL) or {}
            r[f'{label}_ids'] = [entries[shown[n - 1]]['id'] for n in dict.fromkeys(a.get('fits', []))
                                 if isinstance(n, int) and 1 <= n <= len(shown)]
        r['truth_ids'] = sorted(entries[m]['id'] for m in truth[k])
        r['shortlisted_ids'] = sorted(entries[m]['id'] for m in truth[k] if m in shown)
        r['nearest'] = True
        with open(OUT + '.tmp', 'w') as f:
            json.dump(saved, f)
        os.replace(OUT + '.tmp', OUT)
        if i % 10 == 0:
            print(f'E8 {i}/{len(rows)}', flush=True)
    done = [r for r in rows.values() if r.get('nearest')]
    reach = sum(len(r['shortlisted_ids']) for r in done)
    for label in ('latest', 'nearest'):
        found = sum(len(set(r[f'{label}_ids']) & set(r['truth_ids'])) for r in done)
        picks = sum(len(r[f'{label}_ids']) for r in done)
        print(f"E8 {label} 3 claims: found {found} of {reach} of the person's motifs in the shortlist ({found / max(reach, 1):.0%}); "
              f"{picks - found} of {picks} picks not theirs ({(picks - found) / max(picks, 1):.0%})", flush=True)
    print('DONE', flush=True)
