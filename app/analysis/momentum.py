"""Momentum and crossing watch: what the site's own history says about a young story, as plain counts.

The Oct 28 study (maudlin-notes, moonshot-2026-10-27/story-spread) found that whether a story goes wide is told by how
fast it gathers outlets, not by its wording, and that one-sided stories cross to the other side at different rates by
side. Both are kept here as lookup tables, with no fitted model:

    momentum   a story's state now (outlets on it, outlets that joined in the last three hourly runs, hours since it
               first made a card) and the share of the stories once in that state that went wide (WIDE outlets or
               more by the time they settled)
    crossing   a story mostly from one side (CROSS_SHARE of its rated outlets, at least CROSS_MIN_RATED of them, and
               fewer than CROSS_OUTLETS from the other side): its side, whether a wire service or a center outlet is
               on it, its hours so far, and the share of stories once in that spot that had CROSS_OUTLETS outlets from
               the other side within CROSS_WITHIN hours. Both directions are counted the same way

The history is the stories born in the last HISTORY_DAYS that are at least SETTLE_HOURS old. Each is looked at hour by
hour from its birth (when it first made a card, `story.first_seen`) and counted once in each cell it passes through,
with its first hour there. A cell with fewer than MIN_STORIES stories gives way to a coarser one (the hours band
dropped; for crossing, then the wire/center split too); when none is big enough, nothing is said. The tables are built
once a day and kept in TABLE_FILE.

Membership is the stories' final membership (a headline that joined later counts from its own first sighting), as in
the study. A story's outlets are its distinct outlets, aggregators left out; sides are the signs of AllSides' leans."""
import os
from collections import defaultdict
from datetime import datetime as dt, timedelta as td

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

TABLE_FILE = os.path.join(Config.data, 'momentum.json')
REFRESH = td(hours=24)
HISTORY_DAYS = 30
SETTLE_HOURS = 48  # a story this old has done nearly all its gathering (and its day for crossing has passed)
WIDE = 20  # outlets: "went wide", about one story in five (the study: 19.6% of 815 stories)
MIN_STORIES = 20  # a cell with fewer stories says nothing
RECENT = td(hours=2.5)  # "the last three hourly runs": this run and the two before (runs are ~60 min apart)
YOUNG_HOURS = 12  # the momentum line is for stories younger than this
# Bands: (low, high, label); counts include their high end, hours don't. 20+ outlets has gone wide: no band
OUTLET_BANDS = [(0, 7, '7 or fewer'), (8, 10, '8–10'), (11, 15, '11–15'), (16, WIDE - 1, f'16–{WIDE - 1}')]
GAIN_BANDS = [(0, 0, 'none'), (1, 2, '1–2'), (3, 5, '3–5'), (6, 10 ** 6, '6 or more')]
AGE_BANDS = [(0, 3, 'in their first 3 hours'), (3, 6, '3–6 hours in'), (6, YOUNG_HOURS, f'6–{YOUNG_HOURS} hours in')]
# The line shows only when its cell is well off the base rate, either way
FAST_RATIO, FAST_GAP, SLOW_RATIO = 1.75, 0.1, 0.5
FAST_GAIN = 3  # outlets in the last three runs: "gaining fast" (fewer, and a high share: "big for its age")

CROSS_SHARE = 0.8  # of its rated outlets from one side
CROSS_MIN_RATED = 5
CROSS_OUTLETS = 3  # outlets from the other side: a foothold there, not one stray pickup
CROSS_WITHIN = 24  # hours
CROSS_YOUNG_HOURS = 24
CROSS_AGE_BANDS = [(0, 6, 'under 6 hours'), (6, 12, '6–12 hours'), (12, CROSS_YOUNG_HOURS, f'12–{CROSS_YOUNG_HOURS} hours')]
OTHER = {'left': 'right', 'right': 'left'}
SIDE_EMOJI = {'left': '🫏', 'right': '🐘'}
WATCH_NOTE = (f"Stories under a day old with at least {round(100 * CROSS_SHARE)}% of their rated outlets on one side "
              f"(and {CROSS_MIN_RATED} or more rated). Beside each: how often stories like it, in this site's last "
              f"{HISTORY_DAYS} days, had {CROSS_OUTLETS} or more outlets from the other side within a day. Counts, "
              f"not forecasts; hover for what was counted.")


def _band(value, bands):
    """The label of the band holding value: counts (ints) by their inclusive high end, hours by their exclusive one"""
    for low, high, label in bands:
        if (low <= value <= high) if isinstance(value, int) else (low <= value < high):
            return label
    return None


def side_of(bias) -> str | None:
    """An outlet's side from its AllSides lean (None: not rated)"""
    if bias is None:
        return None
    return 'left' if bias < 0 else 'right' if bias > 0 else 'center'


# --- a story's state at a moment ----------------------------------------------------------------------------------
# A story here: {'id', 'birth' (datetime, UTC), 'outlets': {name: (first seen, side)}}, side left, center, right or
# None (not rated). Its reach is len(outlets).

def hours_since(story: dict, at: dt) -> float:
    return max(0.0, (at - story['birth']).total_seconds() / 3600)


def state(story: dict, at: dt) -> dict:
    """Outlets on it by `at`, those first seen in the RECENT window before it, and its hours since birth"""
    seen = [first for first, _ in story['outlets'].values() if first <= at]
    return {'outlets': len(seen), 'gained': sum(first > at - RECENT for first in seen), 'hours': hours_since(story, at)}


def momentum_keys(st: dict) -> list[str]:
    """The cells a state falls in, finest first; none once it has gone wide or is YOUNG_HOURS old"""
    n, g, a = _band(st['outlets'], OUTLET_BANDS), _band(st['gained'], GAIN_BANDS), _band(st['hours'], AGE_BANDS)
    if n is None or g is None or a is None:
        return []
    return [f'{n}|{g}|{a}', f'{n}|{g}']


def sides(story: dict, at: dt) -> dict:
    """Its rated outlets by `at`, counted by side"""
    counts = {'left': 0, 'center': 0, 'right': 0}
    for first, side in story['outlets'].values():
        if first <= at and side:
            counts[side] += 1
    return counts


def side_state(story: dict, at: dt, wires=None) -> dict | None:
    """Its side when it's mostly one side's (else None), with the wire services and center outlets on it"""
    if wires is None:
        from app.analysis.wire import WIRES as wires
    c = sides(story, at)
    rated = c['left'] + c['center'] + c['right']
    if rated < CROSS_MIN_RATED:
        return None
    for side, other in OTHER.items():
        if c[side] >= CROSS_SHARE * rated and c[other] < CROSS_OUTLETS:
            wire = sorted(n for n, (first, _) in story['outlets'].items() if first <= at and n in wires)
            return {'side': side, 'counts': c, 'rated': rated, 'wire': wire, 'center': c['center'],
                    'bridge': bool(wire or c['center']), 'hours': hours_since(story, at)}
    return None


def crossing_keys(ss: dict) -> list[str]:
    a = _band(ss['hours'], CROSS_AGE_BANDS)
    if a is None:
        return []
    b = 'bridge' if ss['bridge'] else 'no bridge'
    return [f"{ss['side']}|{b}|{a}", f"{ss['side']}|{b}", ss['side']]


def crossed(story: dict, side: str, by: dt) -> bool:
    return sides(story, by)[OTHER[side]] >= CROSS_OUTLETS


# --- the tables -----------------------------------------------------------------------------------------------------

def build(stories: list[dict], now: dt, wires=None) -> dict:
    """Both tables from the settled stories: {'momentum': {'base', 'cells'}, 'crossing': {'cells'}, ...}, a cell
    {'n': stories, 'hit': went wide (or crossed)}. A story counts in every key of each state, the coarse ones too."""
    settled = [s for s in stories if now - s['birth'] >= td(hours=SETTLE_HOURS)]
    mom, cross = defaultdict(lambda: {'n': 0, 'hit': 0}), defaultdict(lambda: {'n': 0, 'hit': 0})
    for s in settled:
        wide = len(s['outlets']) >= WIDE
        seen, seen_x = set(), set()  # each story counts once a cell, with its first hour there
        for h in range(YOUNG_HOURS):
            for key in momentum_keys(state(s, s['birth'] + td(hours=h))):
                if key not in seen:
                    seen.add(key)
                    mom[key]['n'] += 1
                    mom[key]['hit'] += wide
        for h in range(CROSS_YOUNG_HOURS):
            at = s['birth'] + td(hours=h)
            ss = side_state(s, at, wires)
            if ss is None:
                continue
            hit = crossed(s, ss['side'], at + td(hours=CROSS_WITHIN))
            for key in crossing_keys(ss):
                if key not in seen_x:
                    seen_x.add(key)
                    cross[key]['n'] += 1
                    cross[key]['hit'] += hit
    births = [s['birth'] for s in settled]
    return {'built': now.isoformat(timespec='seconds'), 'stories': len(settled),
            'from': min(births).isoformat(timespec='minutes') if births else None,
            'to': max(births).isoformat(timespec='minutes') if births else None,
            'momentum': {'base': {'n': len(settled), 'hit': sum(len(s['outlets']) >= WIDE for s in settled)},
                         'cells': dict(mom)},
            'crossing': {'cells': dict(cross)}}


def lookup(cells: dict, keys: list[str]) -> dict | None:
    """The finest cell with MIN_STORIES or more, as {'n', 'hit', 'share', 'key', 'level'}; None if none has"""
    for level, key in enumerate(keys):
        c = cells.get(key)
        if c and c['n'] >= MIN_STORIES:
            return {**c, 'share': c['hit'] / c['n'], 'key': key, 'level': level}
    return None


def odds(hit: int, n: int) -> str:
    """A share in plain words: "8 times in 10", "about 1 time in 20", "every time"..."""
    p = hit / n
    if hit == 0:
        return 'never'
    if hit == n:
        return 'every time'
    if p >= 0.95:
        return 'almost every time'
    if p >= 0.15:
        return f'{min(9, max(2, round(10 * p)))} times in 10'
    if p >= 0.075:
        return 'about 1 time in 10'
    if p < 0.01:
        return 'less than 1 time in 100'
    return f"about 1 time in {min((15, 20, 25, 30, 40, 50, 100), key=lambda k: abs(k - 1 / p))}"


def said(did: str, hit: int, n: int) -> str:
    """How often it did: 'went wide 8 times in 10', or 'never went wide'"""
    return f'never {did}' if hit == 0 else f'{did} {odds(hit, n)}'


# --- what the pages say ------------------------------------------------------------------------------------------------

def badge(table: dict, story: dict, now: dt) -> dict | None:
    """The momentum line for a young story's card and page, or None: YOUNG_HOURS old, already wide, no cell big
    enough, or a cell too close to the base rate to say anything"""
    st = state(story, now)
    found = lookup(table['momentum']['cells'], momentum_keys(st))
    base = table['momentum']['base']
    if not found or not base['n']:
        return None
    rate = base['hit'] / base['n']
    if found['share'] >= max(FAST_RATIO * rate, rate + FAST_GAP):
        kind = 'fast' if st['gained'] >= FAST_GAIN else 'big'
    elif found['share'] <= SLOW_RATIO * rate:
        kind = 'slow'
    else:
        return None
    emoji, label, like = {'fast': ('📈', 'gaining fast', 'stories gathering like this'),
                          'big': ('📰', 'big for its age', 'stories this big this early'),
                          'slow': ('🐢', 'slow so far', 'stories gathering like this')}[kind]
    n_band, g_band, *a_band = found['key'].split('|')
    tip = (f"Of the {found['n']} stories in the last {HISTORY_DAYS} days that had {n_band} outlets with "
           f"{g_band} new in the last three hourly runs{', ' + a_band[0] if a_band else ''} (counting from when each "
           f"first made a card), {found['hit']} went on to reach {WIDE} or more outlets; of all stories, "
           f"{round(100 * rate)}% did. A count from this site's own history, not a forecast.")
    return {'emoji': emoji, 'label': label, 'kind': kind, 'title': tip,
            'text': f"{like} {said('went wide', found['hit'], found['n'])} ({found['n']} stories)",
            'n': found['n'], 'hit': found['hit'], 'share': round(found['share'], 3),
            'outlets': st['outlets'], 'gained': st['gained'], 'hours': round(st['hours'], 1)}


def crossing(table: dict, story: dict, now: dt, wires=None) -> dict | None:
    """A young one-sided story's line on the crossing watch, or None (not one-sided, too old, no cell big enough)"""
    ss = side_state(story, now, wires)
    if ss is None or ss['hours'] >= CROSS_YOUNG_HOURS:
        return None
    found = lookup(table['crossing']['cells'], crossing_keys(ss))
    if not found:
        return None
    side, other = ss['side'], OTHER[ss['side']]
    centers = f"{ss['center']} center outlet{'' if ss['center'] == 1 else 's'}"
    if ss['wire']:
        more = ss['center'] - sum(story['outlets'][w][1] == 'center' for w in ss['wire'])  # Reuters is center
        bridge = f"{' and '.join(ss['wire'])} {'has' if len(ss['wire']) == 1 else 'have'} it" + \
                 (f", and {more} more center outlet{'' if more == 1 else 's'}" if more else '')
    elif ss['center']:
        bridge = f"{centers} {'has' if ss['center'] == 1 else 'have'} it"
    else:
        bridge = 'no wire service or center outlet yet'
    parts = found['key'].split('|')
    counted = 'mostly ' + side
    if found['level'] < 2:
        counted += f", {'with' if ss['bridge'] else 'without'} a wire service or center outlet on them"
    counted += f", {parts[2]} after first making a card" if found['level'] == 0 else ' in their first day'
    who = f"mostly-{side} stories" if found['level'] == 2 else 'stories like this'
    hours = int(ss['hours'])
    return {'side': side, 'other': other, 'emoji': SIDE_EMOJI[side], 'hours': hours,
            'when': 'under an hour' if hours < 1 else f"{hours} hour{'' if hours == 1 else 's'}",
            'counts': ss['counts'], 'bridge': bridge, 'has_bridge': ss['bridge'],
            'n': found['n'], 'hit': found['hit'], 'share': round(found['share'], 3),
            'text': f"{who} {said(f'had {CROSS_OUTLETS}+ {other}-leaning outlets within a day', found['hit'], found['n'])}"
                    f" ({found['n']} stories)",
            'title': (f"Mostly {side}: at least {round(100 * CROSS_SHARE)}% of {CROSS_MIN_RATED} or more rated outlets "
                      f"lean {side}, and fewer than {CROSS_OUTLETS} lean {other}. Of the {found['n']} stories in the last "
                      f"{HISTORY_DAYS} days that were {counted}, {found['hit']} had {CROSS_OUTLETS} or more "
                      f"{other}-leaning outlets within the next {CROSS_WITHIN} hours. A count from this site's own "
                      f"history, not a forecast.")}


# --- the database ---------------------------------------------------------------------------------------------------

def load(since: dt | None = None, ids=None) -> list[dict]:
    """Stories born since `since` (or those with these ids), with each outlet's first sighting and side"""
    from app.models import Agency, Article, Headline, Session, Story, StoryHeadline
    from app.site.page_headlines import AGGREGATORS
    with Session() as s:
        q = s.query(Story.id, Story.first_seen, Agency.name, Agency._bias, Agency.lean_rated, Headline.first_accessed) \
            .join(StoryHeadline, StoryHeadline.story_id == Story.id) \
            .join(Headline, Headline.id == StoryHeadline.headline_id) \
            .join(Article, Article.id == Headline.article_id).join(Agency, Agency.id == Article.agency_id)
        q = q.filter(Story.id.in_(list(ids))) if ids is not None else q.filter(Story.first_seen >= since)
        rows = q.all()
    stories = {}
    for sid, birth, name, bias, rated, first in rows:
        if name in AGGREGATORS or first is None:
            continue
        st = stories.setdefault(sid, {'id': sid, 'birth': birth, 'outlets': {}})
        have = st['outlets'].get(name)
        if have is None or first < have[0]:
            st['outlets'][name] = (first, side_of(bias) if rated else None)
    return list(stories.values())


def from_headlines(story_id: int, birth: dt, headlines: list[dict]) -> dict:
    """A story as above from its headlines ({'outlet', 'bias' (None: not rated), 'first'}), as the story pages hold them"""
    from app.site.page_headlines import AGGREGATORS
    outlets = {}
    for h in headlines:
        if h['outlet'] in AGGREGATORS or h.get('first') is None:
            continue
        if h['outlet'] not in outlets or h['first'] < outlets[h['outlet']][0]:
            outlets[h['outlet']] = (h['first'], side_of(h['bias']))
    return {'id': story_id, 'birth': birth, 'outlets': outlets}


def latest() -> dt:
    """The newest headline's first sighting: "now" as the latest run saw it (a preview's data ends earlier than now)"""
    from sqlalchemy import func

    from app.models import Headline, Session
    with Session() as s:
        return s.query(func.max(Headline.first_accessed)).scalar() or dt.utcnow()


_made = {}  # this process's table, so the front page and the story pages share one build


def table(now: dt | None = None) -> dict:
    """The tables, built from the database at most once every REFRESH and kept in TABLE_FILE (a preview build reads
    the kept one, or builds its own without keeping it)"""
    now = now or latest()
    for kept in (_made.get('table'), read_json(TABLE_FILE, None)):
        if kept and _fresh(kept, now):
            return kept
    made = build(load(since=now - td(days=HISTORY_DAYS, hours=SETTLE_HOURS)), now)
    logger.info("Momentum: tables from %d stories (%d went wide)", made['stories'], made['momentum']['base']['hit'])
    if not Config.debug:
        write_json(TABLE_FILE, made)
    _made['table'] = made
    return made


def _fresh(kept: dict, now: dt) -> bool:
    try:
        return td(0) <= now - dt.fromisoformat(kept['built']) < REFRESH
    except (KeyError, TypeError, ValueError):
        return False


def for_stories(ids, now: dt | None = None) -> dict:
    """For current stories (saved ids): {'badges': {id: line}, 'crossing': [watch lines, each with its 'id'], 'table'},
    the watch youngest first"""
    now = now or latest()
    tbl = table(now)
    badges, watch = {}, []
    for story in load(ids=set(ids)):
        line = badge(tbl, story, now)
        if line:
            badges[story['id']] = line
        entry = crossing(tbl, story, now)
        if entry:
            watch.append({**entry, 'id': story['id']})
    watch.sort(key=lambda w: (w['hours'], w['id']))
    return {'badges': badges, 'crossing': watch, 'table': tbl}
