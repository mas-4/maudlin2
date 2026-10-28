"""The Election Almanac (Oct 28): a forecast of which election story shapes surge in election week, frozen before the
polls open and scored afterwards from the motif index's tellings (motif_web.tellings rows).

The forecast lives in app/site/almanac_2026.json. Freezing it (scripts/freeze_almanac.py) records the SHA-256 of its
content, every key but `frozen` and `results` (the House result, set after the vote, picks the branch of the calls
that depend on it); a frozen forecast whose content no longer hashes to its seal is broken and never scored.

A surge: the motif's share of the window's tellings is at least `lift` times its share of the October baseline's, with
at least `floor` tellings in the window. Score: the Brier score of p_surge against the outcomes, beside a reference
forecaster's (every motif at the October base rate); skill = 1 - Brier / Brier_ref."""
import hashlib
import json
import os
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

FORECAST = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'site', 'almanac_2026.json')
UNSEALED = ('frozen', 'results')  # outside the seal: the seal itself, and the outcomes known only after the vote
SIDES = ('left', 'center', 'right')
EASTERN = ZoneInfo('America/New_York')


class BrokenSeal(Exception):
    """A frozen forecast whose content no longer matches its published SHA-256"""


def load(path: str = FORECAST) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def content(forecast: dict) -> dict:
    return {k: v for k, v in forecast.items() if k not in UNSEALED}


def digest(forecast: dict) -> str:
    """The SHA-256 of the forecast's canonical JSON: sorted keys, no spaces, UTF-8, the seal and results left out"""
    text = json.dumps(content(forecast), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sealed(forecast: dict) -> bool:
    """Frozen and unchanged since; raises BrokenSeal for a frozen forecast that was edited"""
    seal = forecast.get('frozen')
    if not seal:
        return False
    if seal.get('sha256') != digest(forecast):
        raise BrokenSeal(f"the almanac's content hashes to {digest(forecast)[:12]}…, not its seal "
                         f"{str(seal.get('sha256'))[:12]}…")
    return True


def freeze(path: str = FORECAST, now: datetime | None = None) -> dict:
    """Seal the forecast at `path` once: write frozen = {at, sha256, late}. Refuses a forecast already frozen"""
    forecast = load(path)
    if forecast.get('frozen'):
        raise RuntimeError(f"already frozen at {forecast['frozen']['at']}: a frozen forecast is never edited")
    now = (now or datetime.now(EASTERN)).astimezone(EASTERN)
    late = now >= datetime.fromisoformat(forecast['dates']['freeze_by'])
    forecast['frozen'] = {'at': now.isoformat(timespec='seconds'), 'sha256': digest(forecast), 'late': late}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(forecast, f, indent=1, ensure_ascii=False)
        f.write('\n')
    return forecast['frozen']


def today_eastern() -> date:
    return datetime.now(EASTERN).date()


def stage(forecast: dict, today: date) -> str:
    """'draft' (not frozen), 'frozen' (sealed, before the window), 'scoring' (the window has begun; provisional until
    the count day), 'scored' (the count day has come), or 'broken' (edited after freezing)"""
    try:
        frozen = sealed(forecast)
    except BrokenSeal:
        return 'broken'
    if not frozen:
        return 'draft'
    dates = forecast['dates']
    if today.isoformat() < dates['window'][0]:
        return 'frozen'
    return 'scored' if today.isoformat() >= dates['count'] else 'scoring'


def within(rows: list[dict], first: str, last: str) -> list[dict]:
    return [r for r in rows if first <= (r.get('date') or '') <= last]


def lead_side(rows: list[dict], side_totals: Counter, floor: int) -> str | None:
    """The side whose shows told these tellings at the highest rate (its tellings over all that side's show tellings
    in the period), with at least `floor` show tellings; None below the floor or on a tie"""
    told = Counter(r['side'] for r in rows if r['kind'] == 'shows' and r['side'] in SIDES)
    if sum(told.values()) < floor:
        return None
    rates = sorted(((told[s] / side_totals[s], s) for s in SIDES if side_totals[s] and told[s]), reverse=True)
    if not rates or (len(rates) > 1 and rates[0][0] == rates[1][0]):
        return None
    return rates[0][1]


def posts_lead(rows: list[dict]) -> bool:
    """Posts retold online outnumber the tellings on any one side's shows"""
    told = Counter(r['side'] for r in rows if r['kind'] == 'shows' and r['side'] in SIDES)
    posts = sum(r['kind'] == 'posts' for r in rows)
    return posts > 0 and posts > max(told.values(), default=0)


def period(rows: list[dict], first: str, last: str) -> dict:
    """A period's tellings: {n (all), by (motif -> its rows), sides (show tellings by side)}"""
    rs = within(rows, first, last)
    by: dict[str, list[dict]] = {}
    for r in rs:
        by.setdefault(r['motif'], []).append(r)
    sides = Counter(r['side'] for r in rs if r['kind'] == 'shows' and r['side'] in SIDES)
    return {'n': len(rs), 'by': by, 'sides': sides}


def brier(ps: list[float], outcomes: list[int]) -> float | None:
    if not ps:
        return None
    return sum((p - o) ** 2 for p, o in zip(ps, outcomes)) / len(ps)


def called_sides(spec, house: str | None) -> list[str] | None:
    """The sides a lead-side call names, the branch picked by the House result for a conditional call (None: not
    scored, or not known yet)"""
    if isinstance(spec, dict):
        return spec.get(house) if house else None
    return spec or None


def answer(call: dict, win: dict, public: set[str], floor: int) -> dict:
    """An answer call scored on the window: {result: 'hit', 'miss' or None, why: why it isn't scored}"""
    test, ms = call['test'], call['motifs']
    if any(m not in public for m in ms):
        return {'result': None, 'why': 'not scored: a motif in it is not public'}
    rows = {m: win['by'].get(m, []) for m in ms}
    n = {m: len(rows[m]) for m in ms}
    lead = {m: lead_side(rows[m], win['sides'], floor) for m in ms}
    ok = None
    if test == 'counter_follows':  # if the move is told, its counter follows, mostly on center and left shows
        move, counter = ms
        if n[move] < 3:
            return {'result': None, 'why': 'not scored: Voter fraud had fewer than 3 tellings'}
        told = Counter(r['side'] for r in rows[counter] if r['kind'] == 'shows' and r['side'] in SIDES)
        ok = n[counter] >= 2 and told['center'] + told['left'] > sum(told.values()) / 2
    elif test in ('both_by_sides', 'mirror_sides'):  # right shows lead the first; left shows or posts the second
        first, second = ms
        ok = (n[first] >= 3 and n[second] >= 3 and lead[first] == 'right'
              and (lead[second] == 'left' or posts_lead(rows[second])))
    elif test == 'prebunk_first':  # the answer is told on or before the move's first day
        move, pre = ms
        if not rows[move]:
            return {'result': None, 'why': 'not scored: Ballot dump was not told in the window'}
        first_pre = min((r['date'] for r in rows[pre]), default=None)
        ok = first_pre is not None and first_pre <= min(r['date'] for r in rows[move])
    elif test == 'share_exceeds':  # the same window, so shares compare as counts
        a, b = ms
        ok = n[a] > n[b]
    if ok is None:
        return {'result': None, 'why': f'not scored: no test {test!r}'}
    return {'result': 'hit' if ok else 'miss', 'why': ''}


def score(forecast: dict, rows: list[dict], public: set[str], today: date) -> dict:
    """The forecast scored on the tellings so far: {stage, provisional, through (the last window day counted), motifs
    ({id: outcome}), brier, brier_ref, skill, n, surges, sides ({hits, scored, persistence}), answers}. Nothing is
    scored before the window opens, or for a draft or a broken forecast"""
    st = stage(forecast, today)
    out = {'stage': st, 'provisional': st == 'scoring', 'motifs': {}, 'answers': [], 'through': None, 'brier': None,
           'brier_ref': None, 'skill': None}
    first, last = forecast['dates']['window']
    if st not in ('scoring', 'scored') or today.isoformat() < first:
        return out
    through = min(last, today.isoformat())
    base = period(rows, *forecast['dates']['baseline'])
    win = period(rows, first, through)
    lift, floor = forecast['surge']['lift'], forecast['surge']['floor']
    side_floor = forecast['side_floor']
    house = (forecast.get('results') or {}).get('house')
    ps, outs, side_hits, side_scored, persist_hits = [], [], 0, 0, 0
    for f in forecast['forecasts']:
        m = f['id']
        if m not in public:
            out['motifs'][m] = {'public': False}
            continue
        o_n, w_n = len(base['by'].get(m, [])), len(win['by'].get(m, []))
        o_share = o_n / base['n'] if base['n'] else 0.0
        w_share = w_n / win['n'] if win['n'] else 0.0
        surge = int(w_n >= floor and w_share >= lift * o_share)
        lead = lead_side(win['by'].get(m, []), win['sides'], side_floor)
        was = lead_side(base['by'].get(m, []), base['sides'], side_floor)
        sides = called_sides(f.get('lead_sides'), house)
        side_hit = None
        if sides and lead:
            side_hit = lead in sides
            side_hits += side_hit
            side_scored += 1
            persist_hits += was == lead
        out['motifs'][m] = {'public': True, 'oct_n': o_n, 'oct_share': o_share, 'n': w_n, 'share': w_share,
                            'lift': w_share / o_share if o_share else None, 'surge': surge, 'lead': lead,
                            'oct_lead': was, 'side_hit': side_hit}
        ps.append(f['p_surge'])
        outs.append(surge)
    b = brier(ps, outs)
    ref = brier([forecast['base_rate']] * len(ps), outs)
    out.update({'through': through, 'window_n': win['n'], 'baseline_n': base['n'], 'n': len(ps), 'surges': sum(outs),
                'brier': b, 'brier_ref': ref, 'skill': (1 - b / ref) if b is not None and ref else None,
                'sides': {'hits': side_hits, 'scored': side_scored, 'persistence': persist_hits},
                'answers': [answer(c, win, public, side_floor) for c in forecast['answer_calls']]})
    return out
