"""The aisle (Oct 27, the person: the motif map "is so big it's hard to read, interact with, and isn't even all that
interesting"): the motif map redrawn as the stories told across the political aisle. Each motif the shows we follow
told is a dot, placed left to right by which side's shows its claims came up on (blue left, red right, both in the
middle), and up by how many tellers told it; the motifs a person marked as each other's answer are joined by an arc
over the aisle. A story people tell, never a claim that it's true. Drawn as one inline SVG (docs/style-book.md:
charts in Python), with a little script to pick a motif, filter by genre and search. It replaces the force-directed
map at the same address (motif-map.html); the checker keeps its own map for curation."""
import hashlib
import math
from datetime import date, timedelta

from markupsafe import Markup, escape

from app import sidefeeds
from app.analysis import divide, motif_web
from app.site.common import TemplateHandler, motif_href
from app.site.page_motif import shared
from app.site.page_motifs import GENRE_EMOJI
from app.utils import get_logger

logger = get_logger(__name__)

W, H = 1000, 600
PAD_X, PAD_TOP, PAD_BOTTOM = 40, 40, 70
JITTER_X, JITTER_Y = 22, 7  # pixels
LABELLED = 45  # the most told get their name written by the dot
LEAN_INK = {'left': '#2456c9', 'right': '#c41d3a'}


WINDOWS = {'all': None, 'week': 7, 'days3': 3}  # the time buttons: every telling, the last 7 days, the last 3
SPARK_DAYS = 21  # the card's sparkline: tellings a day
RISING_MIN = 3  # a motif rises when told at least this often this week and at least twice as often as the week before
ONLY_LEAST = 2  # "only in the center": said on at least this many of the group's shows, so one show's habit isn't the group's

# The lists under the map, colored by genre (Oct 28, the person: the chips were "plain as hell"; color an axis they
# don't show): the shared ranked strips (app/site/boards.py)
from app.site import boards as strips  # noqa: E402
from app.site.boards import GENRE_INK, UNCOLORED, genre_key as _genre_key, genre_row  # noqa: E402, F401 (re-exported)


def where(rs: list[dict]) -> dict | None:
    """A set of tellings' place on the aisle: lean (-1 all left to 1 all right, pulled toward the middle when few shows
    told it), how many told it, and its counts; None when no show's own host or guest said it. The sides count the
    shows whose host or guest said it (motif_web.spoken), not the clips a show played or its callers (Oct 28: 15 of
    the left's 19 "The impostor" tellings were left shows playing the attack ad on Amy Acton); the height counts
    every telling"""
    s =motif_web.sided(motif_web.spoken(rs))
    left, right, center = len(s['left']), len(s['right']), len(s['center'])
    if not (left or right or center):
        return None
    return {'lean': (right - left) / (right + left + 2), 'told': len({(r['kind'], r['teller'], r['key']) for r in rs}),
            'left': left, 'right': right, 'center': center, 'posts': s['posts'], 'checks': len(s['checks'])}


def place(web: dict, today: date | None = None) -> list[dict]:
    """Every public motif told on the shows, with its place in each time window (WINDOWS), its trend (rising, fading
    or steady: this week's tellings against the week before) and its tellings a day for the last SPARK_DAYS"""
    today = today or date.today()
    by = {}
    for r in web['rows']:
        by.setdefault(r['motif'], []).append(r)
    out = []
    for m, rs in by.items():
        spots = {}
        for w, days in WINDOWS.items():
            since = (today - timedelta(days=days - 1)).isoformat() if days else ''
            spot = where([r for r in rs if r['date'] >= since])
            if spot:
                spots[w] = spot
        if 'all' not in spots:
            continue
        e = web['entries'][m]
        week = sum(1 for r in rs if r['date'] >= (today - timedelta(days=6)).isoformat())
        before = sum(1 for r in rs if (today - timedelta(days=13)).isoformat() <= r['date'] < (today - timedelta(days=6)).isoformat())
        trend = 'rising' if week >= RISING_MIN and week >= 2 * before else \
            'fading' if before >= RISING_MIN and week * 3 <= before else 'steady'
        days = [(today - timedelta(days=SPARK_DAYS - 1 - n)).isoformat() for n in range(SPARK_DAYS)]
        daily = [sum(1 for r in rs if r['date'] == d) for d in days]
        out.append({'id': m, 'name': e['name'], 'genre': rs[0]['genre'],
                    'note': e.get('note', '') if e.get('note_by') not in ('model', 'claude') else '',
                    **spots['all'], 'spots': spots, 'trend': trend, 'week': week, 'before': before, 'daily': daily,
                    'href': motif_href(m)})
    return out


def group_of(r: dict) -> str | None:
    """A show telling's lean group: its side (left, center, right), else its show's group in app/sidefeeds.py
    (crossover: the aisle's sides leave those shows out)"""
    return r['side'] or (sidefeeds.source_for(r.get('show_source') or '') or {}).get('group')


def only_in(web: dict, group: str, least: int = ONLY_LEAST) -> list[dict]:
    """The public motifs told on one lean group's shows and no other's, over all time: at least `least` of the group's
    shows said it in their own voice (a host or guest, as the aisle counts sides), and no show of another group told it
    at all, not even in a clip it played or a call. Not "told on both sides": a motif the center tells and the left and
    right never do. Most shows first"""
    by = {}
    for r in web['rows']:
        if r['kind'] == 'shows':
            by.setdefault(r['motif'], []).append(r)
    out = []
    for m, rs in by.items():
        if {group_of(r) for r in rs} != {group}:
            continue
        shows = sorted({r['teller'] for r in motif_web.spoken(rs)})
        if len(shows) >= least:
            out.append({'id': m, 'name': web['entries'][m]['name'], 'genre': rs[0]['genre'], 'shows': shows,
                        'told': len({(r['teller'], r['key']) for r in rs}), 'href': motif_href(m)})
    return sorted(out, key=lambda d: (-len(d['shows']), -d['told'], d['name'].lower()))


def strip(items: list[dict], value, figure, tip) -> list[dict]:
    """A list under the map as a ranked strip: each motif's genre (emoji and color), its bar (`value` against the
    list's biggest) and its figure, with the detail in data-tip for the pop-up cards"""
    top = max((value(d) for d in items), default=0) or 1
    return [genre_row(d['name'], d['href'], d['genre'], value(d), top, figure(d), tip(d)) for d in items]


def sides_tip(d: dict) -> str:
    return f"{d['genre'] or 'no genre yet'}: said on {d['left']} left, {d['center']} center and {d['right']} right shows"


def lists(dots: list[dict], web: dict) -> list[dict]:
    """The ranked lists under the map, in pairs that answer each other: rising and fading, left and right, both sides
    and only in the center (and only on crossover shows, when any motif is)"""
    def board(key, emoji, title, stage, sub, items, value, figure, tip):
        return strips.board(key, emoji, title, stage, sub, strip(items, value, figure, tip),
                            empty='🦗 None yet: no motif fits this list today.')
    week = lambda d: f"{d['genre'] or 'no genre yet'}: {d['before']} tellings the week before, {d['week']} in the last 7 days"  # noqa: E731
    split = lambda d: f"🫏 {d['left']} · {d['right']} 🐘"  # noqa: E731
    only_tip = lambda d: f"{d['genre'] or 'no genre yet'}: said on {', '.join(d['shows'])}"  # noqa: E731
    boards = [
        board('rising', '🔥', 'Rising this week', '#ff6b1a', 'told at least twice as often in the last 7 days as in '
              'the 7 before; the bar is this week',
              sorted((d for d in dots if d['trend'] == 'rising'), key=lambda d: -d['week'])[:12],
              lambda d: d['week'], lambda d: f"{d['before']} → {d['week']}", week),
        board('fading', '🧊', 'Fading', '#8a8f98', 'told a third as often or less this week; the bar is the week before',
              sorted((d for d in dots if d['trend'] == 'fading'), key=lambda d: -d['before'])[:12],
              lambda d: d['before'], lambda d: f"{d['before']} → {d['week']}", week),
        board('left', '🫏', 'Mostly left', '#3a86ff', "most of the shows that said it lean left; the bar is how many "
              "told it", sorted((d for d in dots if d['lean'] < -0.4), key=lambda d: -d['told'])[:8],
              lambda d: d['told'], split, sides_tip),
        board('right', '🐘', 'Mostly right', '#ff4fa3', "most of the shows that said it lean right; the bar is how "
              "many told it", sorted((d for d in dots if d['lean'] > 0.4), key=lambda d: -d['told'])[:8],
              lambda d: d['told'], split, sides_tip),
        board('both', '⚖️', 'Told on both sides', '#a9a9b8', 'said on left and right shows; the bar is the smaller '
              'side', sorted((d for d in dots if d['left'] and d['right']), key=lambda d: -min(d['left'], d['right']))[:12],
              lambda d: min(d['left'], d['right']), split, sides_tip),
        board('center', '🎯', 'Only in the center', '#b8b8c8', f'said on {ONLY_LEAST} or more center shows and never '
              'heard on a left, right or crossover show, not even in a clip; the bar is how many shows',
              only_in(web, 'center')[:12], lambda d: len(d['shows']),
              lambda d: f"{len(d['shows'])} shows", only_tip)]
    crossover = only_in(web, 'crossover')[:12]
    if crossover:
        boards.append(board('crossover', '🔀', 'Only on crossover shows', '#00c2a8', f'said on {ONLY_LEAST} or more '
                            'crossover shows (Rogan, Theo Von, Tim Dillon…) and no left, right or center show',
                            crossover, lambda d: len(d['shows']), lambda d: f"{len(d['shows'])} shows", only_tip))
    return [b for b in boards if b['rows'] or b['key'] in ('both', 'left', 'right', 'center')]


def genre_key(boards: list[dict]) -> list[dict]:
    """The lists' color key: the colored genres, then the uncolored ones the lists hold"""
    return _genre_key([r for b in boards for r in b['rows']])


def draw(dots: list[dict], arcs: list[tuple[str, str, str]]) -> Markup:
    """The aisle as SVG: dots at their place over all time (each window's place in data attributes, for the time
    buttons), the most told labelled, rising motifs ringed, answers as arcs"""
    top = max((d['told'] for d in dots), default=1)
    x = lambda lean: PAD_X + (lean + 1) / 2 * (W - 2 * PAD_X)  # noqa: E731
    y = lambda told: H - PAD_BOTTOM - (math.log1p(told) / math.log1p(top)) * (H - PAD_TOP - PAD_BOTTOM)  # noqa: E731

    # Few shows give a motif one of a handful of leans (1 of 3, 2 of 4...), so dots would stand in columns: each is
    # spread a little sideways and up, by a fixed amount from its id, so the columns fan out the same way every build
    def spread(mid: str, scale: float) -> float:
        h = int(hashlib.sha1(mid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return (h * 2 - 1) * scale

    def xy(d: dict, spot: dict) -> tuple[float, float]:
        return x(spot['lean']) + spread(d['id'], JITTER_X), y(spot['told']) + spread(d['id'][::-1], JITTER_Y)

    at = {d['id']: xy(d, d['spots']['all']) for d in dots}
    parts = [f'<svg class="aisle-svg" viewBox="0 0 {W} {H}" role="img" aria-label="The stories told across the aisle">',
             '<defs><linearGradient id="aisle-ground" x1="0" x2="1"><stop offset="0" stop-color="#2456c9" stop-opacity="0.12"/>'
             '<stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/><stop offset="1" stop-color="#c41d3a" stop-opacity="0.12"/>'
             '</linearGradient></defs>',
             f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#aisle-ground)" rx="14"/>',
             f'<line x1="{W / 2}" y1="{PAD_TOP - 20}" x2="{W / 2}" y2="{H - PAD_BOTTOM + 10}" class="aisle-mid"/>',
             f'<text x="{PAD_X}" y="{H - 22}" class="aisle-end aisle-end-left">🫏 told on left-leaning shows</text>',
             f'<text x="{W / 2}" y="{H - 22}" class="aisle-end" text-anchor="middle">⚖️ both sides</text>',
             f'<text x="{W - PAD_X}" y="{H - 22}" class="aisle-end aisle-end-right" text-anchor="end">told on right-leaning shows 🐘</text>',
             f'<text x="12" y="{PAD_TOP - 14}" class="aisle-end">↑ told more</text>']
    for a, b, note in arcs:
        if a in at and b in at:
            (x1, y1), (x2, y2) = at[a], at[b]
            lift = 40 + abs(x2 - x1) * 0.25
            parts.append(f'<path class="aisle-arc" data-a="{escape(a)}" data-b="{escape(b)}" d="M {x1:.1f} {y1:.1f} Q '
                         f'{(x1 + x2) / 2:.1f} {min(y1, y2) - lift:.1f} {x2:.1f} {y2:.1f}"><title>{escape(note)}</title></path>')
    labelled = {d['id'] for d in sorted(dots, key=lambda d: -d['told'])[:LABELLED]}
    for d in sorted(dots, key=lambda d: d['told']):  # the most told drawn last, on top
        cx, cy = at[d['id']]
        r = 4 + 9 * math.sqrt(d['told'] / top)
        ink = LEAN_INK['left'] if d['lean'] < -0.2 else LEAN_INK['right'] if d['lean'] > 0.2 else '#6b6f78'
        places = ' '.join(f'data-{w}="{px:.1f},{py:.1f},{4 + 9 * math.sqrt(sp["told"] / top):.1f}"'
                          for w, sp in d['spots'].items() for px, py in [xy(d, sp)])
        ring = f'<circle class="aisle-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="{r + 5:.1f}"/>' if d['trend'] == 'rising' else ''
        parts.append(f'<a href="{d["href"]}" class="aisle-dot aisle-{d["trend"]}" data-id="{escape(d["id"])}" '
                     f'data-genre="{escape(d["genre"])}" data-name="{escape(d["name"].lower())}" {places}>{ring}'
                     f'<circle class="aisle-core" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{ink}"/>'
                     f'<title>{escape(d["name"])}: {d["left"]} left, {d["center"]} center, {d["right"]} right shows</title></a>')
    taken = []
    for d in sorted(dots, key=lambda d: -d['told']):
        if d['id'] not in labelled:
            continue
        cx, cy = at[d['id']]
        w, h = 7.2 * len(d['name']) + 6, 16
        box = (cx + 9, cy - h / 2, cx + 9 + w, cy + h / 2)
        if box[2] > W - 4:
            box = (cx - 9 - w, box[1], cx - 9, box[3])
        if any(not (box[2] < t[0] or box[0] > t[2] or box[3] < t[1] or box[1] > t[3]) for t in taken):
            continue
        taken.append(box)
        parts.append(f'<text x="{box[0] + 3:.1f}" y="{cy + 5:.1f}" class="aisle-label" data-id="{escape(d["id"])}">'
                     f'{escape(d["name"])}</text>')
    parts.append('</svg>')
    return Markup(''.join(parts))


def short_day(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.strftime('%b')} {d.day}"


def day_span(first: str, last: str) -> str:
    """'Oct 20–26', 'Sep 29–Oct 5', or one day"""
    if first == last:
        return short_day(first)
    end = str(date.fromisoformat(last).day) if first[:7] == last[:7] else short_day(last)
    return f'{short_day(first)}–{end}'


def divide_plot(weeks: list[dict]) -> dict | None:
    """The weekly divide index (app/analysis/divide.py) as a full-width line, laid out for the page: each week a
    column (a button that picks the week for the lists below) with its dot at the week's index, the band where 9 in 10
    shuffles of whole shows land (their 5th to 95th percentile, less their mean) around 0, and the ticks. Positions are
    percents of the plot; the band, grid and line are an SVG stretched over it (0-100 both ways), the dots and words
    HTML, so they stay round and readable at any width (Oct 28 redo: the old chart was half the page wide)"""
    if not weeks:
        return None
    lo = min(-0.1, *(k['floor_p05'] - k['floor'] for k in weeks))
    hi = max(0.3, *(k['index'] for k in weeks), *(k['floor_p95'] - k['floor'] for k in weeks))
    lo, hi = math.floor(lo * 10) / 10, math.ceil(hi * 10) / 10
    n = len(weeks)
    x = lambda i: (i + 0.5) * 100 / n  # noqa: E731 - each week's column, its dot in the middle
    y = lambda v: (hi - v) / (hi - lo) * 100  # noqa: E731
    up = [(x(i), y(k['floor_p95'] - k['floor'])) for i, k in enumerate(weeks)]
    down = [(x(i), y(k['floor_p05'] - k['floor'])) for i, k in enumerate(weeks)]
    up = [(0, up[0][1])] + up + [(100, up[-1][1])]  # the band runs edge to edge
    down = [(0, down[0][1])] + down + [(100, down[-1][1])]
    labelled = n <= 8 or None
    out = []
    for i, k in enumerate(weeks):
        span = day_span(k['first'], k['last'])
        partial = bool(k.get('partial'))
        tip = (f"{k['index']:.2f} apart, where 0 is no further apart than shows picked at random\n"
               f"From {k['left']} tellings on {k['left_shows']} left shows and {k['right']} on {k['right_shows']} right "
               f"shows\nRaw gap {k['jsd']:.2f}, random splits {k['floor']:.2f}"
               + ('\nPartial transcripts that week: it rests on less' if partial else '')
               + '\nClick for that week\'s stories below')
        out.append({'week': k['week'], 'span': span, 'x': round(x(i), 2), 'y': round(y(k['index']), 2),
                    'width': round(100 / n, 2), 'index': k['index'], 'partial': partial, 'tip': tip,
                    'label': short_day(k['week']) if labelled or i % 2 == (n - 1) % 2 else ''})
    return {'weeks': out, 'zero': round(y(0), 2),
            'ticks': [{'value': f'{t / 10:g}', 'y': round(y(t / 10), 2)} for t in range(round(lo * 10), round(hi * 10) + 1)],
            'band': ' '.join(f'{px:.2f},{py:.2f}' for px, py in up + down[::-1]),
            'line': ' '.join(f"{w['x']},{w['y']}" for w in out) if n > 1 else ''}


def divide_lists(spoken: list[dict], weeks: list[dict], genre_of: dict) -> list[dict]:
    """Each charted week's stories as a butterfly: its most one-sided motifs on the left and on the right
    (divide.contrasts) and those said on both sides alike between them, mostly-left first and mostly-right last. A row
    has the left's tellings as a blue bar running left and the right's as a red bar running right, against the
    biggest count of any week, so switching weeks keeps the scale"""
    by = {}
    for r in spoken:
        if r.get('date') and r['side'] in ('left', 'right'):
            by.setdefault(divide.week_of(r['date']), []).append(r)
    out, top = [], 1
    for k in weeks:
        c = divide.contrasts(by.get(k['week'], []))
        alike = {m['id'] for m in c['shared']}  # a thin week can rank a both-sides motif "mostly" too: one row only
        groups = [('mostly_left', '🫏', 'Mostly on the left', [m for m in c['mostly_left'] if m['id'] not in alike]),
                  ('shared', '⚖️', 'Said on both sides alike', c['shared']),
                  ('mostly_right', '🐘', 'Mostly on the right',
                   [m for m in c['mostly_right'] if m['id'] not in alike][::-1])]  # the most right-leaning last
        top = max([top] + [max(m['left'], m['right']) for *_, ms in groups for m in ms])
        out.append({'week': k['week'], 'span': day_span(k['first'], k['last']), 'k': k, 'groups': [
            {'key': key, 'emoji': emoji, 'label': label, 'rows': [dict(m, href=motif_href(m['id']),
                                                                      genre=genre_of.get(m['id'])) for m in ms]}
            for key, emoji, label, ms in groups]})
    for w in out:
        for g in w['groups']:
            for m in g['rows']:
                genre = m['genre']
                m.update(left_len=strips.bar(m['left'], top) if m['left'] else 0,
                         right_len=strips.bar(m['right'], top) if m['right'] else 0,
                         ink=GENRE_INK.get(genre, UNCOLORED), mark=GENRE_EMOJI.get(genre, '🧩'),
                         mark_label=genre or 'No genre yet',
                         tip=f"{genre or 'No genre yet'}: in the week of {w['span']}, told {m['left']} times on "
                             f"{m['left_shows']} left-leaning shows and {m['right']} times on {m['right_shows']} "
                             f"right-leaning ones (one telling per episode, by its hosts and guests)")
    return out


class AislePage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('aisle.html', 'motif-map.html')

    def generate(self):
        logger.info("Generating the aisle (motif map)...")
        web = shared()['web']
        dots = place(web)
        placed = {d['id'] for d in dots}
        arcs, seen = [], set()
        for m, ans in web['answers'].items():
            for a in ans:
                pair = tuple(sorted((m, a['id'])))
                if pair not in seen and m in placed and a['id'] in placed:
                    seen.add(pair)
                    arcs.append((pair[0], pair[1], a['note']))
        genres = sorted({d['genre'] for d in dots if d['genre']}, key=lambda g: list(GENRE_EMOJI).index(g) if g in GENRE_EMOJI else 99)
        boards = lists(dots, web)
        try:  # the weekly divide index (app/analysis/divide.py), and each week's stories for the butterfly
            spoken = motif_web.spoken(web['rows'])
            gaps = divide.weekly(spoken)
            genre_of = {r['motif']: r['genre'] for r in web['rows']}
            weeks = divide_lists(spoken, gaps['weeks'], genre_of)
        except Exception as e:  # noqa: BLE001 - the page stands without it
            logger.warning("The aisle: divide index: %s", e)
            gaps, weeks = {'weeks': [], 'latest': None}, []
        self.template.write({
            'divide': gaps, 'divide_plot': divide_plot(gaps['weeks']), 'divide_draws': divide.DRAWS,
            'divide_weeks': weeks,
            'divide_key': _genre_key([{'genre': m['genre'] or 'No genre yet'} for w in weeks for g in w['groups']
                                      for m in g['rows']]),
            'title': 'The aisle', 'svg': draw(dots, arcs), 'dots': dots, 'arcs': len(arcs),
            'genres': [(g, GENRE_EMOJI.get(g, '🧩'), sum(1 for d in dots if d['genre'] == g)) for g in genres],
            'unplaced': len(web['entries']) - len(dots), 'boards': boards, 'genre_key': genre_key(boards),
            'og_title': 'The aisle: the stories each side tells · bignews.day',
            'og_description': 'Every story shape in our motif index, placed by which side\'s shows tell it, with the '
                              'answers each side gives the other.'})
        logger.info("...%d motifs on the aisle, %d answers", len(dots), len(arcs))
