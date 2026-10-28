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

# The lists under the map, colored by genre (Oct 28, the person: the chips were "plain as hell"; color an axis they don't
# show). Five colors for the five biggest genres (93% of tellings): of 14 hues tried, no set of more than five stays apart
# for every pair under color blindness (the dataviz validator, all pairs on white: worst deutan ΔE 7.6, the olive and
# brown, in the floor band, so the emoji always goes with the color), and none is the lean blue or red. The rest (Values, Exhortations, Perennials) stay white,
# known by their emoji. Fixed to the genre, in GENRE_EMOJI order, never cycled.
GENRE_INK = {'Archetypes': '#e87ba4', 'Plots': '#a0522d', 'Beliefs': '#7a8a00', 'Theories': '#8a5cff',
             'Arguments': '#eda100'}
UNCOLORED = '#ffffff'
GENRE_SHORT = {'Archetypes': 'a kind of person', 'Plots': 'what happened', 'Beliefs': 'a premise',
               'Theories': 'what people think is behind it', 'Arguments': 'a move in an argument',
               'Values': 'how things ought to be', 'Exhortations': 'a call to act', 'Perennials': 'safe small talk'}


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
    return [{'name': d['name'], 'href': d['href'], 'genre': d['genre'] or 'No genre yet',
             'emoji': GENRE_EMOJI.get(d['genre'], '🧩'), 'ink': GENRE_INK.get(d['genre'], UNCOLORED),
             'bar': max(4, round(100 * value(d) / top)), 'figure': figure(d), 'tip': tip(d)} for d in items]


def sides_tip(d: dict) -> str:
    return f"{d['genre'] or 'no genre yet'}: said on {d['left']} left, {d['center']} center and {d['right']} right shows"


def lists(dots: list[dict], web: dict) -> list[dict]:
    """The ranked lists under the map, in pairs that answer each other: rising and fading, left and right, both sides
    and only in the center (and only on crossover shows, when any motif is)"""
    def board(key, emoji, title, stage, sub, items, value, figure, tip):
        return {'key': key, 'emoji': emoji, 'title': title, 'stage': stage, 'sub': sub,
                'rows': strip(items, value, figure, tip)}
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
    shown = {r['genre'] for b in boards for r in b['rows']}
    key = [{'genre': g, 'emoji': GENRE_EMOJI[g], 'ink': ink, 'about': GENRE_SHORT.get(g, '')}
           for g, ink in GENRE_INK.items()]
    rest = [g for g in GENRE_EMOJI if g not in GENRE_INK and g in shown]
    return key + [{'genre': g, 'emoji': GENRE_EMOJI[g], 'ink': UNCOLORED, 'about': GENRE_SHORT.get(g, ''),
                   'first_plain': i == 0} for i, g in enumerate(rest)]


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


def divide_chart(weeks: list[dict]) -> Markup | None:
    """The weekly divide index (app/analysis/divide.py) as a small SVG line: each week's index, with the band where
    90% of the shuffles of whole shows land (their 5th to 95th percentile, less their mean) around 0"""
    if not weeks:
        return None
    w, h, left, right, top, bottom = 420, 220, 40, 26, 24, 34  # narrow, so its words stay readable on a phone
    lo = min(-0.1, *(k['floor_p05'] - k['floor'] for k in weeks))
    hi = max(0.3, *(k['index'] for k in weeks), *(k['floor_p95'] - k['floor'] for k in weeks))
    lo, hi = math.floor(lo * 10) / 10, math.ceil(hi * 10) / 10
    step = (w - left - right) / max(len(weeks) - 1, 1)
    x = (lambda i: left + i * step) if len(weeks) > 1 else (lambda i: (left + w - right) / 2)  # noqa: E731
    y = lambda v: top + (hi - v) / (hi - lo) * (h - top - bottom)  # noqa: E731
    parts = [f'<svg class="divide-svg" viewBox="0 0 {w} {h}" role="img" aria-label="The divide between left and right '
             f'shows, week by week">']
    for t in range(round(lo * 10), round(hi * 10) + 1):
        v = t / 10
        parts.append(f'<line class="divide-grid" x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="divide-tick" x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:g}</text>')
    up = [(x(i), y(k['floor_p95'] - k['floor'])) for i, k in enumerate(weeks)]
    down = [(x(i), y(k['floor_p05'] - k['floor'])) for i, k in enumerate(weeks)]
    if len(weeks) == 1:  # one week: a band as wide as a dot's neighbourhood
        up = [(up[0][0] - 20, up[0][1]), (up[0][0] + 20, up[0][1])]
        down = [(down[0][0] - 20, down[0][1]), (down[0][0] + 20, down[0][1])]
    band = ' '.join(f'{px:.1f},{py:.1f}' for px, py in up + down[::-1])
    parts.append(f'<polygon class="divide-band" points="{band}"><title>Where 9 in 10 random splits of the same shows '
                 f'land</title></polygon>')
    parts.append(f'<line class="divide-zero" x1="{left}" x2="{w - right}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>'
                 f'<text class="divide-tick" x="{w - right}" y="{y(0) + 14:.1f}" text-anchor="end">0: shows picked at '
                 f'random</text>')
    if len(weeks) > 1:
        parts.append('<polyline class="divide-line" points="' +
                     ' '.join(f'{x(i):.1f},{y(k["index"]):.1f}' for i, k in enumerate(weeks)) + '"/>')
    for i, k in enumerate(weeks):
        span = day_span(k['first'], k['last'])
        partial = ' divide-partial' if k.get('partial') else ''
        note = '; partial transcripts' if partial else ''
        parts.append(f'<circle class="divide-dot{partial}" cx="{x(i):.1f}" cy="{y(k["index"]):.1f}" r="6"><title>{span}'
                     f'{note}: {k["index"]:.2f} ({k["left"]} left and {k["right"]} right tellings from {k["left_shows"]} and '
                     f'{k["right_shows"]} shows; their raw gap {k["jsd"]:.2f}, random splits {k["floor"]:.2f})'
                     f'</title></circle>')
        if len(weeks) <= 8 or i % 2 == (len(weeks) - 1) % 2:
            parts.append(f'<text class="divide-tick" x="{x(i):.1f}" y="{h - 10}" text-anchor="middle">'
                         f'{short_day(k["week"])}</text>')
    last = weeks[-1]
    parts.append(f'<text class="divide-value" x="{x(len(weeks) - 1) - 10:.1f}" y="{y(last["index"]) - 12:.1f}" '
                 f'text-anchor="end">{last["index"]:.2f}</text>')
    parts.append('</svg>')
    return Markup(''.join(parts))


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
        try:  # the weekly divide index (app/analysis/divide.py)
            gaps = divide.weekly(motif_web.spoken(web['rows']))
            for side in ('shared', 'mostly_left', 'mostly_right'):
                for m in (gaps['latest'] or {}).get(side, []):
                    m['href'] = motif_href(m['id'])
        except Exception as e:  # noqa: BLE001 - the page stands without it
            logger.warning("The aisle: divide index: %s", e)
            gaps = {'weeks': [], 'latest': None}
        latest = gaps['latest']
        self.template.write({
            'divide': gaps, 'divide_svg': divide_chart(gaps['weeks']), 'divide_draws': divide.DRAWS,
            'divide_span': day_span(latest['first'], latest['last']) if latest else '',
            'title': 'The aisle', 'svg': draw(dots, arcs), 'dots': dots, 'arcs': len(arcs),
            'genres': [(g, GENRE_EMOJI.get(g, '🧩'), sum(1 for d in dots if d['genre'] == g)) for g in genres],
            'unplaced': len(web['entries']) - len(dots), 'boards': boards, 'genre_key': genre_key(boards),
            'og_title': 'The aisle: the stories each side tells · bignews.day',
            'og_description': 'Every story shape in our motif index, placed by which side\'s shows tell it, with the '
                              'answers each side gives the other.'})
        logger.info("...%d motifs on the aisle, %d answers", len(dots), len(arcs))
