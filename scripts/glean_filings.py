"""Glean the motifs lying on the ground (Oct 9, the person: "a lot of easy to apply motifs are lying on the ground").
The hourly filer files a claim once, when it arrives, against the motifs there then, and never looks again: the
motifs made since have never been tried against the older claims, and half the claims have one motif. This asks every
filed claim again, against today's index, the way the weak-fit alternatives do (filing_confidence.alternatives): the
learned shortlist's 12 best of the person's motifs, those it's in and those a person took it out of left out, each
scored by the confidence model (the judge's yes or no among its signals).

    python scripts/glean_filings.py score     # the GPU part: every claim's candidates and their fit, kept in OUT
    python scripts/glean_filings.py report    # how many at each fit
    python scripts/glean_filings.py apply 0.8 [--cap 3]   # add those at or over the fit as UNCHECKED filings

Applying only adds: no filing is moved or taken out. Each new filing carries its fit, so it shows in the ✅ check
tab like any other unchecked one. Motifs with no claims yet (seeds) can't be scored this way: the signals are built
from a motif's claims."""
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime as dt

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.utils import Config  # noqa: E402

OUT = os.path.join(Config.data, 'motifs', 'glean.json')
CHUNK = 50  # claims judged or scored between saves of the signals' caches


def free_gpu():
    """Unload every model Ollama holds (as transcribe.py does before Whisper)"""
    import requests as rq
    from app.analysis import llm
    try:
        for x in rq.get(f'{llm.OLLAMA_URL}/api/ps', timeout=10).json().get('models', []):
            rq.post(f'{llm.OLLAMA_URL}/api/generate', json={'model': x['name'], 'keep_alive': 0}, timeout=30)
        time.sleep(5)
    except Exception as e:  # noqa: BLE001 - the reranker falls back to the CPU
        print(f'could not free the GPU ({e})', flush=True)


def filed_claims(index: dict) -> dict[str, dict]:
    """Claim key -> one of its filings (claim, source, ref, side, date), for every claim in a live motif"""
    out = {}
    for e in mi.live(index):
        for c in e['claims']:
            out.setdefault(mi.key(c['claim']), c)
    return out


def score():
    index = mi.load()
    m, w = fc.model(), mr.weights()
    if not m or not w:
        sys.exit('no confidence model or shortlist weights')
    said_no = {k for k, ok in fc.decisions().items() if not ok}
    claims = filed_claims(index)
    scorer = fc.Scorer(index, w)
    coef = np.array([m['weights'][f] for f in fc.FEATURES])
    started = time.time()
    texts = [c['claim'] for c in claims.values()]
    print(f'{len(texts)} filed claims; preparing signals', flush=True)
    scorer.signals.prepare(texts)
    cands = {}
    for k, c in claims.items():
        cands[k] = [eid for eid in scorer.candidates(c['claim']) if (k, eid) not in said_no]
    print(f'candidates ready ({sum(map(len, cands.values()))} pairs, {time.time() - started:.0f} s); judging',
          flush=True)
    # The judge's answers live in memory until saved: a run cut short (the first, Oct 9, after 72 minutes of judging)
    # lost them all. A chunk at a time, saved after each, so a second run picks up where the first stopped
    items = [(claims[k]['claim'], [scorer.signals.at[eid] for eid in ids]) for k, ids in cands.items() if ids]
    for s in range(0, len(items), CHUNK):
        scorer.signals.judge_many(items[s:s + CHUNK], leave_out=True)
        scorer.signals.save()
        print(f'judged {min(s + CHUNK, len(items))}/{len(items)} claims ({time.time() - started:.0f} s)', flush=True)
    free_gpu()  # the judge out of the card, so the reranker runs there, not on the CPU (it did, Oct 9: too slow)
    # and made to: it picks its device when first loaded, and fell back to the CPU when anything else held the card
    # at that moment (Oct 10: 7 cores for 80 minutes, the card idle, the lease held)
    os.environ['MOTIF_RERANK_DEVICE'] = 'cuda'
    scorer.signals._reranker = None
    rows = []
    for n, (k, ids) in enumerate(cands.items()):
        if not ids:
            continue
        c = claims[k]
        p = 1 / (1 + np.exp(-(scorer.rows(c['claim'], ids, c.get('source', '')) @ coef + m['bias'])))
        rows += [{'claim': c['claim'], 'id': eid, 'fit': round(float(v), 3)} for eid, v in zip(ids, p)]
        if n % CHUNK == CHUNK - 1:
            scorer.signals.save()
            print(f'scored {n + 1}/{len(cands)} claims ({time.time() - started:.0f} s)', flush=True)
    scorer.signals.save()
    with open(OUT, 'w') as f:
        json.dump({'model': m['at'], 'at': dt.now().isoformat(timespec='seconds'), 'rows': rows}, f)
    print(f'{len(rows)} pairs scored in {time.time() - started:.0f} s, kept in {OUT}', flush=True)
    report()


def report():
    with open(OUT) as f:
        d = json.load(f)
    rows = d['rows']
    index = mi.load()
    names = {e['id']: e['name'] for e in mi.live(index)}
    for t in (0.5, 0.6, 0.7, 0.8, 0.9):
        over = [r for r in rows if r['fit'] >= t]
        print(f'fit >= {t}: {len(over)} filings on {len({r["claim"] for r in over})} claims', flush=True)
    top = Counter(r['id'] for r in rows if r['fit'] >= 0.8)
    print('motifs gaining most at 0.8:', ', '.join(f'{names.get(i, i)} {n}' for i, n in top.most_common(15)))


def apply(threshold: float, cap: int = 3):
    with open(OUT) as f:
        d = json.load(f)
    by = {}
    for r in sorted(d['rows'], key=lambda r: -r['fit']):
        if r['fit'] >= threshold and len(by.setdefault(r['claim'], [])) < cap:
            by[r['claim']].append(r)
    today = dt.now().strftime('%Y-%m-%d')
    added = 0
    with mi.locked():
        index = mi.load()
        said_no = {k for k, ok in fc.decisions().items() if not ok}
        claims = filed_claims(index)
        for claim, rs in by.items():
            k = mi.key(claim)
            src = claims.get(k)
            if src is None:
                continue  # taken out of every motif since it was scored
            for r in rs:
                e = index['entries'].get(r['id'])
                if not e or e.get('merged_into') or (k, r['id']) in said_no or k in e.get('not_claims', []) \
                        or any(mi.key(c['claim']) == k for c in e['claims']):
                    continue
                e['claims'].append({'claim': src['claim'], 'source': src.get('source', ''), 'ref': src.get('ref', ''),
                                    'side': src.get('side'), 'date': src.get('date') or today, 'fit': r['fit'],
                                    'fit_model': d['model'], 'gleaned': today})
                index['claims'][k] = sorted(set(index['claims'].get(k, [])) | {r['id']})
                added += 1
        mi.save(index)
    print(f'added {added} unchecked filings at fit >= {threshold} (at most {cap} a claim)', flush=True)


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'report'
    if what == 'score':
        score()
    elif what == 'apply':
        cap = int(sys.argv[sys.argv.index('--cap') + 1]) if '--cap' in sys.argv else 3
        apply(float(sys.argv[2]), cap)
    else:
        report()
