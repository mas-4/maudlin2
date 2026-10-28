"""The weekly divide index (Oct 28, from the Oct 27 moonshot probe): how different the stories left-leaning and
right-leaning shows tell are, week by week, beyond what show-to-show differences alone would give.

For each election-aligned week (Tuesday to Monday, named by its Tuesday, so that election day starts one), the motifs
the left shows' hosts and guests said and the right shows' (motif_web.spoken: one telling per motif per show episode,
clips and callers left out) are two distributions; their Jensen-Shannon divergence (bits, 0 to 1) is the raw gap. Raw
JSD mostly tracks sample size, and shows differ from each other whatever their lean, so the floor is the same gap with
the lean labels shuffled among the week's whole shows (as many left shows as there were): the index is the observed
gap minus the floor's mean. 0 means the two sides are no more different than shows picked at random.

Daily values are never published: at a day's size only 7 of 23 days beat the floor (the probe). A week needs
MIN_TELLINGS tellings and MIN_SHOWS shows on each side, and the week in progress is left out.

Weeks before FULL_TRANSCRIPTS rest on partial transcripts: until the Oct 20 fix the shows' transcriber carried text
over between parts and kept about 3 characters a second of audio, against about 16 since, and show claims per episode
went from about 7 to about 24. The floor allows for the smaller sample, but those weeks are marked partial."""
import math
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

DRAWS = 500  # show shuffles per week (a week takes about 10 ms)
MIN_TELLINGS, MIN_SHOWS = 40, 4  # on each side, for a week to count
WEEKS = 26  # weeks kept on the chart
PRIOR = 10  # the log-odds prior's weight in tellings, spread over the motifs by their pooled share (as motif_web)
SHARED_Z = 1.0  # a motif told by both sides is shared when its log-odds z is under this
LIST = 5  # motifs in each of the latest week's lists
FULL_TRANSCRIPTS = '2026-10-20'  # the first week whose show transcripts are whole


def week_of(day: str) -> str:
    """The Tuesday-to-Monday week a day (ISO) falls in, named by its Tuesday"""
    d = date.fromisoformat(day[:10])
    return (d - timedelta(days=(d.weekday() - 1) % 7)).isoformat()


def jsd(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Jensen-Shannon divergence in bits between the rows of two count matrices (or two count vectors)"""
    P, Q = np.atleast_2d(P).astype(float), np.atleast_2d(Q).astype(float)
    P = P / P.sum(axis=1, keepdims=True)
    Q = Q / Q.sum(axis=1, keepdims=True)
    M = (P + Q) / 2
    with np.errstate(divide='ignore', invalid='ignore'):
        a = np.where(P > 0, P * np.log2(P / M), 0.0)
        b = np.where(Q > 0, Q * np.log2(Q / M), 0.0)
    return 0.5 * a.sum(axis=1) + 0.5 * b.sum(axis=1)


def gap(rows: list[dict], draws: int = DRAWS, seed: int = 0) -> dict | None:
    """The divide in one set of host-and-guest tellings: {jsd, floor (mean), floor_p05, floor_p95, index (jsd minus
    the floor's mean), left, right (tellings), left_shows, right_shows}; None when a side is too small"""
    sides = {r['teller']: r['side'] for r in rows if r['side'] in ('left', 'right')}
    rows = [r for r in rows if r['teller'] in sides]
    n = Counter(r['side'] for r in rows)
    shows = {s: sum(1 for v in sides.values() if v == s) for s in ('left', 'right')}
    if min(n['left'], n['right']) < MIN_TELLINGS or min(shows.values()) < MIN_SHOWS:
        return None
    motifs = {m: i for i, m in enumerate(sorted({r['motif'] for r in rows}))}
    names = sorted(sides)
    at = {s: i for i, s in enumerate(names)}
    X = np.zeros((len(names), len(motifs)))  # tellings per show per motif
    for r in rows:
        X[at[r['teller']], motifs[r['motif']]] += 1
    left = np.array([sides[s] == 'left' for s in names])
    observed = float(jsd(X[left].sum(0), X[~left].sum(0))[0])
    rng = np.random.default_rng(seed)
    masks = np.array([rng.permutation(left) for _ in range(draws)], dtype=float)  # draws x shows, 1 = left
    P, Q = masks @ X, (1 - masks) @ X
    ok = (P.sum(1) > 0) & (Q.sum(1) > 0)
    floor = jsd(P[ok], Q[ok])
    mean = float(floor.mean())
    return {'jsd': round(observed, 4), 'floor': round(mean, 4),
            'floor_p05': round(float(np.quantile(floor, 0.05)), 4), 'floor_p95': round(float(np.quantile(floor, 0.95)), 4),
            'index': round(observed - mean, 4), 'left': n['left'], 'right': n['right'],
            'left_shows': shows['left'], 'right_shows': shows['right']}


def log_odds(a: Counter, b: Counter, prior: float = PRIOR) -> dict:
    """Weighted log-odds z of each motif in a against b, with an informative prior (Monroe, Colaresi and Quinn 2008):
    {motif: z}, positive when a tells it more"""
    total = a + b
    n_all = sum(total.values()) or 1
    alpha = {m: 1 + prior * total[m] / n_all for m in total}
    a0, n_a, n_b = sum(alpha.values()), sum(a.values()), sum(b.values())
    out = {}
    for m in total:
        ya, yb = a[m], b[m]
        d = (math.log((ya + alpha[m]) / (n_a + a0 - ya - alpha[m]))
             - math.log((yb + alpha[m]) / (n_b + a0 - yb - alpha[m])))
        out[m] = d / math.sqrt(1 / (ya + alpha[m]) + 1 / (yb + alpha[m]))
    return out


def contrasts(rows: list[dict], top: int = LIST) -> dict:
    """A week's most shared and most one-sided motifs: {shared, mostly_left, mostly_right: [{id, name, left, right,
    left_shows,
    right_shows, z}]}. Shared: said by at least 2 shows on each side with no clear lean (|z| < SHARED_Z), the biggest
    smaller side first. One-sided: the strongest lean, said by at least 2 shows on that side"""
    rows = [r for r in rows if r['side'] in ('left', 'right')]
    count = {s: Counter(r['motif'] for r in rows if r['side'] == s) for s in ('left', 'right')}
    shows = defaultdict(lambda: {'left': set(), 'right': set()})
    names = {}
    for r in rows:
        shows[r['motif']][r['side']].add(r['teller'])
        names[r['motif']] = r['name']
    z = log_odds(count['right'], count['left'])
    n = {s: sum(count[s].values()) or 1 for s in ('left', 'right')}
    items = [{'id': m, 'name': names[m], 'left': count['left'][m], 'right': count['right'][m],
              'left_shows': len(shows[m]['left']), 'right_shows': len(shows[m]['right']), 'z': round(z[m], 2)}
             for m in names]
    shared = sorted((i for i in items if i['left_shows'] >= 2 and i['right_shows'] >= 2 and abs(i['z']) < SHARED_Z),
                    key=lambda i: (-min(i['left'] / n['left'], i['right'] / n['right']), i['name']))
    left = sorted((i for i in items if i['z'] < 0 and i['left_shows'] >= 2), key=lambda i: (i['z'], i['name']))
    right = sorted((i for i in items if i['z'] > 0 and i['right_shows'] >= 2), key=lambda i: (-i['z'], i['name']))
    return {'shared': shared[:top], 'mostly_left': left[:top], 'mostly_right': right[:top]}


def weekly(spoken: list[dict], today: date | None = None, draws: int = DRAWS) -> dict:
    """The index week by week from host-and-guest tellings (motif_web.spoken): {weeks: [{week, end, **gap}], latest:
    the last week's {week, end, **gap, **contrasts}} over the last WEEKS complete weeks; the week in progress is left
    out. Each week's shuffles are seeded by its date, so a week's floor doesn't move between builds"""
    today = today or date.today()
    current = week_of(today.isoformat())
    by = defaultdict(list)
    for r in spoken:
        if r.get('date') and r['side'] in ('left', 'right'):
            by[week_of(r['date'])].append(r)
    weeks = []
    for wk in sorted(w for w in by if w < current)[-WEEKS:]:
        g = gap(by[wk], draws, seed=int(wk.replace('-', '')))
        if g:
            days = [r['date'][:10] for r in by[wk]]  # the days it has tellings for (the shows began on Oct 3)
            weeks.append({'week': wk, 'end': (date.fromisoformat(wk) + timedelta(days=6)).isoformat(),
                          'first': min(days), 'last': max(days), 'partial': wk < FULL_TRANSCRIPTS, **g})
    latest = {**weeks[-1], **contrasts(by[weeks[-1]['week']])} if weeks else None
    return {'weeks': weeks, 'latest': latest}
