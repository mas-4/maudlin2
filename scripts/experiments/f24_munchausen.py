"""F24 Baron Munchausen: a telling, not a report (Oct 18; the person: "I feel like I'm having to heavily police the
sure claims ... it's going to let 1 in 10 bad matches through"). The Baron told tall tales; a claim that only reports
the news its subject is in tells no motif, and the confidence model can't tell the two apart: the nine sure claims the
person held on Oct 18 sat at fits of 0.98-0.999, most of them plain reports in an editorial motif.

Two report-or-telling signals added to the confidence model (app/analysis/filing_confidence.py), and bulk passes of the
sure fold counted for less:

    Hermagoras   Gemma 4 26B's speech act and stasis for each claim (the labels of f4_abstract_tellings.py, reused
                 where asked; the rest asked for these two only): the claim is a report; its speech act and stasis
                 agree with the commonest among its motif's other claims
    Nimble       the decision model asked whether the claim is a plain report of events (its probability)
    bulk         decisions made in a batch of more than 100 ✓ steps, all past the sure line then, weighted 0.3: the
                 old sure fold's passes of 230 at once (Oct 10); a page of the ✅ sure tab (at most 100, 10-30 in use)
                 is looked over (the person: "if i pass 10 at a time they're inspected")

The paper is ~/maudlin-data/papers/munchausen.md (hypotheses and the decision rule written before the run).

    f24_munchausen.py freeze    the Oct 18 sure claims (clean, and needing the person) kept as they stand
    f24_munchausen.py ask       under the GPU lease: Gemma's labels and Nimble's answer for every claim in a motif;
                                resumes from what it saved
    f24_munchausen.py report    the arms held out, the Oct 18 claims scored again, and the decision rule"""
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts')
from app.analysis import curation_db, llm  # noqa: E402
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

DB = os.path.join(harness.EXP, 'f24_munchausen.sqlite')
F4 = os.path.join(harness.EXP, 'f4_abstract.sqlite')
DAY = '2026-10-18'
MODEL = 'gemma4:26b'
NIMBLE = 'nimble:9b'
BULK_AT, BULK_WEIGHT = 101, 0.3  # more steps than the ✅ sure tab's largest page
CHUNK = 50  # claims asked, then saved
SPEECH = ['warning', 'accusation', 'mockery', 'lament', 'boast', 'praise', 'demand', 'report']
STASIS = ['fact', 'definition', 'quality', 'jurisdiction']
PROMPT = """A claim people are telling or arguing over:
{claim}

stasis: what the telling contends: fact (did it happen?), definition (what is it, really?), quality (was it right, \
justified, good or bad?), or jurisdiction (who should judge or act?).
speech: what the teller is doing: warning, accusation, mockery, lament, boast, praise, demand, or report."""
SCHEMA = {"type": "object", "properties": {"stasis": {"type": "string", "enum": STASIS},
                                           "speech": {"type": "string", "enum": SPEECH}},
          "required": ["stasis", "speech"]}
REPORT_Q = ('Is this a plain report of events, rather than someone telling, arguing or judging something? Yes if it '
            'only says what happened or will happen; no if it asserts what something means, accuses, praises, mocks, '
            'warns or passes on a story about someone.')


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute('create table if not exists labels (key text primary key, claim text, stasis text, speech text, '
                'source text)')
    con.execute('create table if not exists nimble (key text primary key, claim text, p real)')
    con.execute('create table if not exists frozen (day text, kind text, key text, claim text, ids text, '
                'primary key (day, kind, key))')
    return con


def freeze():
    """The day's sure claims as the checker's tally sees them now, before the person decides the held ones"""
    import validate
    con = connect()
    got = validate.sure_tally_claims().get(DAY, {})
    for kind in ('clean', 'needed'):
        for k, v in got.get(kind, {}).items():
            con.execute('insert or replace into frozen values (?, ?, ?, ?, ?)', (DAY, kind, k, v['claim'], json.dumps(sorted(v['ids']))))
    con.commit()
    print({kind: len(got.get(kind, {})) for kind in ('clean', 'needed')})


def frozen(con) -> dict:
    out = {'clean': {}, 'needed': {}}
    for kind, k, claim, ids in con.execute('select kind, key, claim, ids from frozen where day = ?', (DAY,)):
        out[kind][k] = {'claim': claim, 'ids': json.loads(ids)}
    return out


def claims_to_ask(index: dict, con) -> list[str]:
    seen = {}
    for e in mi.live(index):
        for c in e['claims']:
            seen.setdefault(mi.key(c['claim']), c['claim'])
    for v in frozen(con)['needed'].values():
        seen.setdefault(mi.key(v['claim']), v['claim'])
    return list(seen.values())


def ask():
    index, con = mi.load(), connect()
    claims = claims_to_ask(index, con)
    have = {k for (k,) in con.execute('select key from labels')}
    if os.path.exists(F4):  # Hermagoras's own labels, from the full prompt
        f4 = sqlite3.connect(F4)
        for claim, stasis, speech in f4.execute('select claim, stasis, speech from asked where speech is not null'):
            k = mi.key(claim)
            if k not in have and stasis in STASIS and speech in SPEECH:
                con.execute('insert or replace into labels values (?, ?, ?, ?, ?)', (k, claim, stasis, speech, 'f4'))
                have.add(k)
        con.commit()
    todo = [c for c in claims if mi.key(c) not in have]
    print(f'Labels: {len(claims) - len(todo)} of {len(claims)} claims have them; asking {len(todo)}', flush=True)
    for n in range(0, len(todo), CHUNK):
        part = todo[n:n + CHUNK]
        answers = llm.parallel(lambda c: llm.complete_json(PROMPT.format(claim=c), SCHEMA, max_tokens=60, model=MODEL), part)
        for c, a in zip(part, answers):
            if a and a.get('speech') in SPEECH and a.get('stasis') in STASIS:
                con.execute('insert or replace into labels values (?, ?, ?, ?, ?)', (mi.key(c), c, a['stasis'], a['speech'], 'f24'))
        con.commit()
        print(f'Labels: asked {min(n + CHUNK, len(todo))}/{len(todo)}', flush=True)
    have = {k for (k,) in con.execute('select key from nimble')}
    todo = [c for c in claims if mi.key(c) not in have]

    def report(c):
        r = rq.post(f'{llm.OLLAMA_URL}/v1/systemone', timeout=300, json={
            'model': NIMBLE, 'state': f'Claim: {c}', 'questions': {'report': {'type': 'noul', 'instructions': REPORT_Q}}})
        r.raise_for_status()
        a = r.json()['answers']['report']
        return float(a.get('noul', a.get('probability')) if isinstance(a, dict) else a)
    for n in range(0, len(todo), CHUNK):
        part = todo[n:n + CHUNK]
        for c, p in zip(part, llm.parallel(report, part)):
            if p is not None:
                con.execute('insert or replace into nimble values (?, ?, ?)', (mi.key(c), c, p))
        con.commit()
        print(f'Nimble: asked {min(n + CHUNK, len(todo))}/{len(todo)}', flush=True)


def provenance() -> dict:
    """(claim key, motif id) -> True when the person's last word on the filing came in a bulk pass"""
    out = {}
    for r in curation_db.actions():
        a, before = r['action'], r.get('before') or {}
        fits, sure_at = before.get('fits') or {}, before.get('sure_at')
        steps = (a.get('steps') or []) if a.get('action') == 'batch' else [a]
        yes = [x for x in steps if isinstance(x, dict) and x.get('action') == 'check' and x.get('answer') == 'yes']
        bulk = (len(yes) >= BULK_AT and len(yes) == len(steps) and sure_at is not None
                and all((fits.get(f"{mi.key(x['claim'])}|{x['id']}") or 0) >= sure_at for x in yes))
        decided = {}
        fc._decided(a, decided)
        for pair in decided:
            out[pair] = bulk
    return out


def build(index: dict, con) -> dict:
    """Production's training matrix (filing_confidence.train) with each row's pair, and the Oct 18 pairs' rows"""
    w = mr.weights()
    scorer = fc.Scorer(index, w)
    pairs = fc.labeled(index)
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    day = frozen(con)
    source_of = {mi.key(c['claim']): c.get('source', '') for e in mi.live(index) for c in e['claims']}
    extra = [(v['claim'], source_of.get(k, ''), [i for i in v['ids'] if i in scorer.at]) for kind in day for k, v in day[kind].items()]
    scorer.signals.prepare([c for c, _ in by_claim] + [c for c, _, _ in extra])
    col = fc.FEATURES.index('motifs of the claim')
    X, y, keys = [], [], []
    for (claim, source), items in by_claim.items():
        rows = scorer.rows(claim, [eid for eid, _ in items], source)
        now = scorer.motifs_of.get(mi.key(claim), set())
        for row, (eid, ok) in zip(rows, items):
            row[col] = len(now | {eid})
            X.append(row)
            y.append(ok)
            keys.append((mi.key(claim), eid))
    D = {}
    for claim, source, ids in extra:
        if ids:
            D.update({(mi.key(claim), eid): row for eid, row in zip(ids, scorer.rows(claim, ids, source))})
    scorer.signals.save()
    X = np.array(X)
    from app.analysis import reranker_teach
    if scorer.signals.rerank_tag != 'base':  # as train(): scores by rerankers that never saw each claim
        held, rc = reranker_teach.held_out(), fc.FEATURES.index('rerank')
        for i, (k, e) in enumerate(keys):
            if f'{k}|{e}' in held:
                X[i, rc] = fc.logit(np.array([held[f'{k}|{e}']]))[0]
    return {'X': X, 'y': np.array(y, dtype=bool), 'keys': keys, 'day': day, 'day_rows': D}


def extra_features(keys: list, index: dict, con) -> dict[str, np.ndarray]:
    labels = {k: (st, sp) for k, st, sp in con.execute('select key, stasis, speech from labels')}
    nim = dict(con.execute('select key, p from nimble').fetchall())
    claims_of = defaultdict(list)
    for e in mi.live(index):
        for c in e['claims']:
            claims_of[e['id']].append(mi.key(c['claim']))

    def commonest(eid, leave, i):
        got = Counter(labels[k][i] for k in claims_of.get(eid, []) if k != leave and k in labels)
        return got.most_common(1)[0][0] if got else None
    H, N = [], []
    for k, eid in keys:
        st, sp = labels.get(k, (None, None))
        H.append([float(sp == 'report'), float(sp is not None and sp == commonest(eid, k, 1)),
                  float(st is not None and st == commonest(eid, k, 0))])
        N.append([nim.get(k, 0.5)])
    return {'H': np.array(H), 'N': np.array(N)}


def fit_w(X, y, w):
    from sklearn.linear_model import LogisticRegression
    mu, sd = X.mean(0), X.std(0) + 1e-9
    return LogisticRegression(max_iter=2000, C=0.5).fit((X - mu) / sd, y, sample_weight=w), mu, sd


def held_out(X, y, groups, w, folds: int = 5) -> np.ndarray:
    from sklearn.model_selection import GroupKFold
    p = np.zeros(len(y))
    for tr, te in GroupKFold(folds).split(X, y, groups):
        m, mu, sd = fit_w(X[tr], y[tr], w[tr])
        p[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
    return p


def sure_line(p, y, w) -> float | None:
    """As production picks it (filing_confidence.evaluate), the precision weighted as the arm weighs decisions"""
    for t in (0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97):
        passed = p >= t
        if passed.sum() >= 20 and np.average(y[passed], weights=w[passed]) >= fc.SURE:
            return t
    return None


def report():
    from sklearn.metrics import roc_auc_score
    index, con = mi.load(), connect()
    data = build(index, con)
    X, y, keys, day = data['X'], data['y'], data['keys'], data['day']
    bulk_of = provenance()
    bulk = np.array([bulk_of.get(k, False) for k in keys])
    deliberate = ~bulk
    groups = [k for k, _ in keys]
    feats = extra_features(keys, index, con)
    day_keys = list(data['day_rows'])
    day_X = np.array([data['day_rows'][k] for k in day_keys]) if day_keys else np.zeros((0, X.shape[1]))
    day_feats = extra_features(day_keys, index, con)
    in_day = np.array([k in day['clean'] or k in day['needed'] for k, _ in keys])
    harness.note(f'F24 Baron Munchausen: {len(y)} decided filings ({y.sum()} kept), {bulk.sum()} from bulk passes; '
                 f'Oct 18: {len(day["clean"])} sure claims passed clean, {len(day["needed"])} needed the person')
    arms = {}
    for name, add in (('today', []), ('+Hermagoras', ['H']), ('+Nimble', ['N']), ('+both', ['H', 'N'])):
        Xa = np.hstack([X] + [feats[a] for a in add])
        Da = np.hstack([day_X] + [day_feats[a] for a in add]) if day_keys else day_X
        for wname, wb in (('', 1.0), (', bulk 0.3', BULK_WEIGHT)):
            w = np.where(bulk, wb, 1.0)
            p = held_out(Xa, y, groups, w)
            at = sure_line(p, y, w)
            passed = p >= at if at is not None else np.zeros(len(p), dtype=bool)
            dp = passed & deliberate
            # the Oct 18 claims, by a model trained without them, and the sure line it would choose
            tr = ~in_day
            m, mu, sd = fit_w(Xa[tr], y[tr], w[tr])
            at_tr = sure_line(held_out(Xa[tr], y[tr], [g for g, t in zip(groups, tr) if t], w[tr]), y[tr], w[tr])
            fit = dict(zip(day_keys, m.predict_proba((Da - mu) / sd)[:, 1])) if day_keys else {}

            def still_sure(v, k, fit=fit, at_tr=at_tr):
                ps = [fit[(k, i)] for i in v['ids'] if (k, i) in fit]
                return bool(ps) and at_tr is not None and min(ps) >= at_tr
            out_needed = sum(not still_sure(v, k) for k, v in day['needed'].items())
            kept_clean = sum(still_sure(v, k) for k, v in day['clean'].items())
            a = {'auc': roc_auc_score(y, p), 'auc_deliberate': roc_auc_score(y[deliberate], p[deliberate]),
                 'sure_at': at, 'share_sure': passed.mean(), 'precision_deliberate': y[dp].mean() if dp.any() else None,
                 'needed_out': out_needed, 'clean_kept': kept_clean, 'day_sure_at': at_tr}
            arms[name + wname] = a
            harness.note(f"F24 {name + wname}: AUC {a['auc']:.3f}, deliberate {a['auc_deliberate']:.3f}; sure from "
                         f"{at}, {a['share_sure']:.0%} of filings past it, {a['precision_deliberate'] or 0:.1%} kept of "
                         f"the deliberate ones there; Oct 18 (sure from {at_tr}): {out_needed} of {len(day['needed'])} "
                         f"needing the person out of sure, {kept_clean} of {len(day['clean'])} clean still sure")
    base = arms['today']['auc_deliberate']
    cost = {'today': 0, '+Nimble': 1, '+Hermagoras': 2, '+both': 3}  # of two that pass, the cheaper (the paper)
    passing = sorted((n for n, a in arms.items() if n != 'today' and a['auc_deliberate'] - base >= 0.005
                      and a['needed_out'] >= 5 and a['clean_kept'] >= 0.85 * max(1, len(day['clean']))),
                     key=lambda n: cost[n.split(',')[0]])
    harness.note('F24 decision: ' + (f"in production: {passing[0]} (passing: {', '.join(passing)})" if passing
                                     else 'no arm passes the rule; production stays as it is'))


if __name__ == '__main__':
    {'freeze': freeze, 'ask': ask, 'report': report}[sys.argv[1]]()
