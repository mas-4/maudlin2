"""The filing pipeline's trace (Oct 14, the person: "show the process as it works", the way some tools show which
neurons fire in a language model): each stage a claim passes through, appended as it happens to a day's file of JSON
lines, for the checker's 🧠 Live page (app/analysis/trace_view.py, scripts/checker/ui/src/pages/live).

    written      a claim written from its source: people's posts (narratives.py: the posts' keys and count), a
                 fact-check (factchecks.py), the shows (show_claims.py)
    shaped       its bare shape and its layers, as the filing model wrote them (motif_signals.py's caches)
    shortlist    the motifs shown the filing model, in order, each with its score and every signal the learned weights
                 read (the "neurons"), with the weights
    picked       what the filing model picked among them, the names it gave, its reason
    scored       the confidence model's features for each filing, its weights and bias, and the fit
    refiled      a plain claim filed again (watch_list.py)
    split_proposed / split
                 the claim organizer's reading, and a split applied (claim_organizer.py)

The person's decisions aren't traced here: the curation log has them, and the view reads them from it.

Only values already worked out are written: tracing never asks a model anything. Keys, ids and the claims' own words
(the model's or the person's) are kept; posts' texts never are. Nothing here may stop the pipeline: every failure is
swallowed. Files older than KEEP_DAYS are deleted."""
import fcntl
import json
import os
from datetime import datetime as dt
from datetime import timedelta as td

from app.analysis.motif_index import key  # noqa: F401 - the claim key, as trace.key for the trace's readers
from app.utils import Config

KEEP_DAYS = 14
TEXT = 400  # characters of a claim kept
FOLDER = None  # tests and tools may point it elsewhere; by default Config.data/motifs/trace, read at call time
_pruned = {'day': None}


def folder() -> str:
    return FOLDER or os.path.join(Config.data, 'motifs', 'trace')


def _plain(x, digits: int = 4):
    """JSON-ready: numpy numbers and arrays as Python's, floats rounded"""
    if isinstance(x, float):
        return round(x, digits) if x == x and abs(x) != float('inf') else None
    if isinstance(x, (str, int, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {str(k): _plain(v, digits) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_plain(v, digits) for v in x]
    if hasattr(x, 'tolist'):  # numpy
        return _plain(x.tolist(), digits)
    return str(x)


def live() -> bool:
    """Whether this process files into the live index: an experiment's step (MAUDLIN_TRACE=off, set by the queue) or a
    copy of the index (an experiment's sandbox) isn't the pipeline, and its filings stay out of the trace (the night of
    Oct 14-15, Rip Van Winkle's 687 sandbox filings showed on the Live page as if real)"""
    if os.environ.get('MAUDLIN_TRACE') == 'off':
        return False
    from app.analysis import motif_index as mi
    return os.path.realpath(mi.INDEX) == os.path.realpath(os.path.join(Config.data, 'motif_index.sqlite'))


def emit(stage: str, claim: str, **data):
    """One event of a claim at a stage, appended to today's file. Never raises"""
    try:
        if not isinstance(claim, str) or not claim.strip() or not live():
            return
        now = dt.now()
        row = {'t': now.isoformat(timespec='seconds'), 's': stage, 'k': key(claim)}
        if stage != 'scored':  # the claim's words, so the feed can show it (a scoring comes after its shortlist)
            row['c'] = claim.strip()[:TEXT]
        row.update({k: v for k, v in _plain(data).items() if v not in (None, [], {}, '')})
        line = json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n'
        os.makedirs(folder(), exist_ok=True)
        with open(os.path.join(folder(), f'{now:%Y-%m-%d}.jsonl'), 'a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # the hourly run, the worker and the checker may all write at once
            f.write(line)
        if _pruned['day'] != now.date():
            _pruned['day'] = now.date()
            prune(now)
    except Exception:  # noqa: BLE001 - the trace is a window on the pipeline, never a part of it
        pass


def prune(now: dt | None = None):
    """Delete the days older than KEEP_DAYS"""
    try:
        cut = f'{(now or dt.now()) - td(days=KEEP_DAYS):%Y-%m-%d}'
        for name in os.listdir(folder()):
            if name.endswith('.jsonl') and name[:10] < cut:
                os.remove(os.path.join(folder(), name))
    except Exception:  # noqa: BLE001
        pass


# ---------- what each stage's hook hands over ----------

def written_narratives(report: dict):
    """narratives.report(): each retold narrative's claim, with its posts' keys and count (never their words)"""
    try:
        for g in report.get('found', []):
            lab = g.get('label') or {}
            if lab.get('retold') and lab.get('narrative'):
                emit('written', lab['narrative'], source='narrative', ref=report.get('made', ''), posts=g.get('posts'),
                     authors=g.get('authors'), variety=g.get('variety'), kind=g.get('kind'), keys=(g.get('keys') or [])[:30],
                     genre=lab.get('genre'), story=(g.get('story') or {}).get('id'),
                     factchecks=len(g.get('factchecks') or []) or None)
    except Exception:  # noqa: BLE001
        pass


def written_shows(old: list, new: list):
    """show_claims.extract(): each claim newly retold on two or more shows (the shows and how many tellings)"""
    try:
        seen = {key(r.get('claim') or '') for r in old or []}
        for r in new or []:
            if r.get('claim') and key(r['claim']) not in seen:
                emit('written', r['claim'], source='shows', ref=r.get('ref', ''), shows=r.get('shows'),
                     tellings=r.get('tellings'), speakers=r.get('speakers'))
    except Exception:  # noqa: BLE001
        pass


def shortlisted(c: dict, shown: list[dict], lister, **extra):
    """motif_index.file_claims() and watch_list.refile(), once a claim's shortlist is drawn: its shape and layers (from
    the shortlister's caches, if it read them), then the shortlist with the signals behind it (motif_retriever.last,
    the arrays it just ranked by)"""
    try:
        claim = c['claim']
        k = key(claim)
        sig = getattr(lister, 'sig', None)
        if sig is not None:
            shape = (getattr(sig, 'shapes', None) or {}).get(k)
            layers = (getattr(sig, 'layered', None) or {}).get(k)
            if shape or layers:
                emit('shaped', claim, shape=shape, layers=layers)
        from app.analysis import motif_retriever as mr
        last = mr.last if mr.last.get('key') == k else {}
        out = {'source': c.get('source', ''), 'ref': c.get('ref', ''), 'split_from': c.get('split_from'), **extra,
               'shown': [e['id'] for e in shown], 'seeds': [e['id'] for e in shown if not e.get('claims')],
               'method': last.get('method') or ('closest' if shown else 'none')}
        if last:
            entries, X, score, order = last['entries'], last['X'], last['score'], last['order']
            rank = {i: n for n, i in enumerate(order)}
            at = {e['id']: i for i, e in enumerate(entries)}
            top, more = set(last['top']), set(last['more'])
            rows = []
            for e in shown:
                i = at.get(e['id'])
                why = 'seed' if i is None else 'top' if i in top else 'tree' if i in more else 'other'
                rows.append({'id': e['id'], 'why': why, **({} if i is None else {
                    'rank': rank.get(i), 'score': float(score[i]), 'x': [float(v) for v in X[i]]})})
            shown_at = {at[e['id']] for e in shown if e['id'] in at}
            out.update(features=last['features'], coef=last['coef'], mu=last['mu'], sd=last['sd'], bias=last['bias'],
                       rows=rows, of=len(entries),
                       next=[{'id': entries[i]['id'], 'rank': rank[i], 'score': float(score[i])}
                             for i in order if i not in shown_at][:8])
        emit('shortlist', claim, **out)
    except Exception:  # noqa: BLE001
        pass


def picked(claim: str, named: dict, filed: list[str], made: list[str] | None = None, **extra):
    """What the filing model made of a shortlist (motif_index.name_claim's answer) and what was filed"""
    try:
        emit('picked', claim, picked=[e['id'] for e in named.get('existing', [])], new=named.get('new'),
             reason=named.get('reason'), new_reason=named.get('new_reason'), filed=filed, made=made, **extra)
    except Exception:  # noqa: BLE001
        pass


def scored(claim: str, source: str, ids: list[str], rows, z, m: dict, features: list[str], confirmed: bool = False):
    """filing_confidence.score(): each filing's feature row, the weights and bias it was weighed by, and its fit"""
    try:
        import math
        emit('scored', claim, source=source, ids=ids, x=rows, z=z,
             fit=[round(1 / (1 + math.exp(-float(v))), 3) for v in z], features=features,
             w=[m['weights'][f] for f in features], bias=m['bias'], model=m.get('at'),
             sure_at=(m.get('test') or {}).get('sure_at'), confirmed=confirmed or None)
    except Exception:  # noqa: BLE001
        pass
