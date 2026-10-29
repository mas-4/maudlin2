"""🗺️ The outlet map (Oct 28): every outlet we read on enough of our stories, placed by which stories it covers (the
coverage axes of app.analysis.outlet_profile), with a second view on how it words them (wire × heat). Dots in the
outlets' lean colors, the most distinctive labeled, every one named on hover or tap. Drawn as inline SVG, like the
story charts, and opens full screen the same way (svg.story-chart). Also draws the small map on each outlet's page,
and the 🎯 beats (outlet_profile.find_beats): a board of them here, and the beat card on an outlet's page."""
from datetime import datetime as dt
from html import escape

import pytz

from app.analysis import outlet_profile
from app.site.boards import LEAN_INK
from app.site.common import TemplateHandler, short_name
from app.site.data import DataHandler
from app.site.favicons import slug
from app.site.graphing import bias_colors, bias_ink
from app.utils import get_logger

logger = get_logger(__name__)

W, H = 760, 560
LEFT, RIGHT, TOP, BOTTOM = 30, 14, 30, 40
MAX_LABELS = 30
BANDWIDTH = 0.045  # the shape's smoothing, as a share of the map's shorter side: wide enough to join a prong, not the gaps
CHAR_W = 7.0  # a label's width per character at 12px, near enough to keep labels apart
UNRATED = '#ffffff'
VIEWS = {
    'coverage': {'x': 'x', 'y': 'y', 'name': '🗞️ Which stories it covers',
                 'left': '← business, tech and world', 'right': 'the political fight →',
                 'up': '↑ stories critical of Trump', 'down': '↓ crime and immigration',
                 'shape': True},
    'style': {'x': 'wire', 'y': 'heat', 'name': '🌶️ How it words them',
              'left': '← its own agenda and words', 'right': 'close to AP and Reuters →',
              'up': '↑ heated wording', 'down': '↓ calm wording'},
}
LEANS = [(-2, 'Left'), (-1, 'Lean left'), (0, 'Center'), (1, 'Lean right'), (2, 'Right')]
LEAN_MARK = {-2: '🫏', -1: '🫏', 0: '⚖️', 1: '🐘', 2: '🐘'}

# The outlet types' colors (Oct 28), for every list that colors outlets by type: fixed to the type, in the order of
# outlet_profile's FAMILIES then TYPES, never cycled. The left family's two types are its purple lighter and darker, so
# the family reads first; the others stand apart (the dataviz validator, adjacent pairs on white: worst deutan ΔE 7.6,
# the olive and brown, in the floor band, so the emoji always goes with the color). None is the lean blue or red: the
# types are named for what outlets do, not for their lean. An outlet with no settled type is white.
TYPE_INK = {'Outside the partisan webs': '#00c2a8', 'Right partisan web': '#ff6b1a', 'Left partisan web': '#8a5cff',
            'Left Trump-watch': '#b49aff', 'Left opinion': '#5d3bd1', 'Business desk': '#eda100',
            'Washington and network news': '#00897b', 'General interest': '#a0522d',
            'Explainers and public media': '#7a8a00', 'Slow analysis and magazines': '#e87ba4'}
TYPE_EMOJI = {'Outside the partisan webs': '🏘️', 'Right partisan web': '🚨', 'Left partisan web': '📢',
              'Left Trump-watch': '👀', 'Left opinion': '💭', 'Business desk': '💹',
              'Washington and network news': '🏛️', 'General interest': '🏟️', 'Explainers and public media': '💡',
              'Slow analysis and magazines': '🐢'}
NO_TYPE = {'name': 'No settled type', 'mark': '⚪', 'ink': '#ffffff',
           'about': 'On the map, but between the types that hold together.'}
OFF_MAP = {'name': 'Not on the map', 'mark': '🌐', 'ink': '#ffffff',
           'about': 'In too few of our stories to place (most outlets outside the US and the UK).'}
# Which side ran a story more: the share of the left-rated outlets on the map that ran it against the share of the
# right-rated ones; within this ratio of each other they ran it alike
SIDE_EVEN = 1.5


def type_look(profiled: dict | None) -> dict:
    """An outlet's type as the lists color it (name, emoji, ink, what it does), from its profile; None: not mapped"""
    if not profiled:
        return OFF_MAP
    name = profiled.get('type')
    if not name:
        return NO_TYPE
    return {'name': name, 'mark': TYPE_EMOJI.get(name, '🏷️'), 'ink': TYPE_INK.get(name, '#ffffff'),
            'about': outlet_profile.ABOUT.get(name, '')}


def type_key(names, off_map: bool = False) -> list[dict]:
    """The key to the type colors the lists hold: the colored ones in their fixed order, then the white ones"""
    names = set(names)
    key = [{'name': n, 'mark': TYPE_EMOJI[n], 'ink': ink} for n, ink in TYPE_INK.items() if n in names]
    if None in names or NO_TYPE['name'] in names:
        key.append({k: NO_TYPE[k] for k in ('name', 'mark', 'ink')})
    if off_map:
        key.append({k: OFF_MAP[k] for k in ('name', 'mark', 'ink')})
    return key


def side_look(left: float | None, right: float | None) -> dict:
    """A pulling story's disc: the lean whose outlets ran it more, in the lean colors, or grey when they ran it alike"""
    from app.site.boards import LEAN_EMOJI, LEAN_INK
    lf, rt = left or 0.0, right or 0.0
    if lf > rt * SIDE_EVEN and lf > 0:
        side, words = 'left', 'run more by left-rated outlets'
    elif rt > lf * SIDE_EVEN and rt > 0:
        side, words = 'right', 'run more by right-rated outlets'
    else:
        side, words = 'center', 'run alike by left- and right-rated outlets'
    return {'ink': LEAN_INK[side], 'mark': LEAN_EMOJI[side], 'label': words}


def pull_boards(profile: dict, with_page: set[int]) -> list[list[dict]]:
    """🧲 The stories that pull outlets toward each end of the map's two axes, as two answering pairs of boards
    (across: business, tech and world | the political fight; up and down: critical of Trump | crime and
    immigration), each story's disc in the lean that ran it more, its bar how many outlets on the map ran it"""
    from app.site import boards
    from app.site.page_story import page_name
    axes = profile.get('axes', {})
    pulls, n = axes.get('pull', {}), len(profile.get('outlets', {}))

    def rows(axis, end):
        found = pulls.get(axis, {}).get(end)
        if found is None:  # a profile from before the stories carried their ids: the labels alone
            found = [{'id': None, 'label': x, 'outlets': None, 'left': None, 'right': None}
                     for x in axes.get(axis, {}).get(end, [])]
        top = max((s['outlets'] or 0 for s in found), default=0)
        out = []
        for s in found:
            look = side_look(s['left'], s['right'])
            tip = f"{s['label']}: {look['label']}"
            if s['left'] is not None and s['right'] is not None:
                tip += (f"; {round(100 * s['left'])}% of the left-rated outlets on the map ran it, "
                        f"{round(100 * s['right'])}% of the right-rated")
            out.append(boards.row(s['label'], page_name(s['id']) if s['id'] in with_page else None,
                                  s['outlets'] or 0, top, f"{s['outlets']} of {n}" if s['outlets'] else '',
                                  tip=tip, ink=look['ink'], mark=look['mark'], mark_label=look['label']))
        return out
    sub = 'the stories that pull outlets this way hardest, first; the bar is how many outlets on the map ran it'
    v = VIEWS['coverage']
    return [[boards.board('pull-left', '💼', v['left'].removeprefix('← '), '#00c2a8', sub, rows('x', 'low')),
             boards.board('pull-right', '🥊', v['right'].removesuffix(' →'), '#ff6b1a', sub, rows('x', 'high'))],
            [boards.board('pull-up', '🔍', v['up'].removeprefix('↑ '), '#8a5cff', sub, rows('y', 'high')),
             boards.board('pull-down', '🚔', v['down'].removeprefix('↓ '), '#eda100', sub, rows('y', 'low'))]]


def type_rows(profile: dict) -> list[dict]:
    """🏷️ The outlet types as strips, the most heated first: each with its members' middle heat and wire percentiles
    (the bars), how many outlets, what it does, how well it held together, and its members, for the hover card"""
    outlets = profile.get('outlets', {})
    out = []
    for t in profile.get('types', []):
        members = [m for m in t['members'] if m in outlets]
        if not members:
            continue
        heat = sorted(outlets[m]['heat_pct'] for m in members)
        wire = sorted(outlets[m]['wire_pct'] for m in members if not outlets[m]['is_wire'])
        look = type_look({'type': t['name']})
        out.append({**look, 'level': t['level'], 'heat': heat[len(heat) // 2],
                    'wire': wire[len(wire) // 2] if wire else None, 'n': len(members),
                    'about': t['about'] or look['about'], 'stability': round(100 * t['stability']),
                    'members': [{'name': m, 'href': f'outlet-{slug(m)}.html'} for m in members]})
    return sorted(out, key=lambda t: -t['heat'])


def story_pages() -> set[int]:
    """The stories with a page of their own: every story of the last days, and every page kept once built"""
    from datetime import timedelta as td
    from app.models import Session, Story
    from app.site import page_story
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=page_story.DAYS)
    try:
        with Session() as s:
            recent = {i for (i,) in s.query(Story.id).filter(Story.last_seen >= since)}
    except Exception:  # noqa: BLE001 - lists without links beat no page
        logger.exception("Story ids for the outlet map's links")
        recent = set()
    return recent | page_story.archived_ids()


def ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 11th, 22nd..."""
    suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


def eastern_day(iso: str) -> str:
    """'2026-10-28T12:05' (UTC) as 'Oct 28, 8 AM'"""
    t = pytz.UTC.localize(dt.fromisoformat(iso)).astimezone(pytz.timezone('US/Eastern'))
    return t.strftime('%b %-d, %-I %p')


def fill(lean) -> str:
    return UNRATED if lean is None else bias_colors[lean + 3]


def _scale(values: list[float], lo: float, hi: float, pad: float = 0.05):
    """A linear map from the values' range (padded, and always taking in 0) onto lo..hi"""
    a, b = min(values + [0.0]), max(values + [0.0])
    span = (b - a) or 1.0
    a, b = a - pad * span, b + pad * span
    return lambda v: lo + (hi - lo) * (v - a) / (b - a)


def density_svg(points: list[tuple[float, float]], width: float, height: float, step: float = 5,
                levels: tuple = (0.06, 0.2, 0.45)) -> str:
    """The shape the outlets make, as soft shading behind their dots: a smoothed count of dots (a Gaussian kernel a
    little wider than a dot), cut at a few heights and filled, darker where more of them crowd. It shows whatever
    shape the day's map has, so it never claims one the dots don't make. Oct 29, the person, on the arrow the outlets
    made (a shaft of business and wire outlets forking into a left prong and a right one): "can we tweak this to make
    the shape clearer?" """
    import contourpy
    import numpy as np
    if len(points) < 3:
        return ''
    xs, ys = np.arange(0, width + step, step), np.arange(0, height + step, step)
    gx, gy = np.meshgrid(xs, ys)
    bw = BANDWIDTH * min(width, height)
    z = np.zeros(gx.shape)
    for x, y in points:
        z += np.exp(-((gx - x) ** 2 + (gy - y) ** 2) / (2 * bw * bw))
    top = z.max()
    if top <= 0:
        return ''
    gen = contourpy.contour_generator(gx, gy, z / top, fill_type='OuterOffset')
    parts = ['<g class="omap-shape" aria-hidden="true">']
    for i, lo in enumerate(levels):
        polys, offsets = gen.filled(lo, 2.0)
        for pts, offs in zip(polys, offsets):
            d = ''.join('M' + 'L'.join(f'{px:.0f},{py:.0f}' for px, py in pts[s:e]) + 'Z'
                        for s, e in zip(offs[:-1], offs[1:]))
            parts.append(f'<path class="omap-shape-{i}" d="{d}" fill-rule="evenodd"/>')
    parts.append('</g>')
    return ''.join(parts)


def _overlaps(box, boxes) -> bool:
    x0, y0, x1, y1 = box
    return any(x0 < b[2] and b[0] < x1 and y0 < b[3] and b[1] < y1 for b in boxes)


def place_labels(points: list[tuple[str, float, float]], width: float, height: float,
                 most: int = MAX_LABELS, r: float = 7) -> dict[str, tuple[float, float, str]]:
    """Labels for the points in the order given (most distinctive first): right of the dot, else left, above or
    below, wherever it overlaps no other label or dot and stays inside; a point with no room goes unlabeled.
    name -> (x, y, text-anchor)"""
    dots = [(x - r, y - r, x + r, y + r) for _, x, y in points]
    boxes, out = [], {}
    for name, x, y in points:
        if len(out) >= most:
            break
        w = CHAR_W * len(short_name(name))
        others = [d for d, p in zip(dots, points) if p[0] != name]
        for lx, ly, anchor, box in ((x + r + 2, y + 4, 'start', (x + r + 2, y - 7, x + r + 2 + w, y + 6)),
                                    (x - r - 2, y + 4, 'end', (x - r - 2 - w, y - 7, x - r - 2, y + 6)),
                                    (x, y - r - 4, 'middle', (x - w / 2, y - r - 16, x + w / 2, y - r - 3)),
                                    (x, y + r + 13, 'middle', (x - w / 2, y + r + 2, x + w / 2, y + r + 15))):
            inside = box[0] >= 2 and box[2] <= width - 2 and box[1] >= 2 and box[3] <= height - 2
            if inside and not _overlaps(box, boxes) and not _overlaps(box, others):
                boxes.append(box)
                out[name] = (lx, ly, anchor)
                break
    return out


def distinctive(outlets: dict, view: str) -> list[str]:
    """Outlets furthest from the middle of a view first (each axis in its own spread)"""
    v = VIEWS[view]
    xs = [o[v['x']] for o in outlets.values()]
    ys = [o[v['y']] for o in outlets.values()]
    sx = (sum(x * x for x in xs) / len(xs)) ** 0.5 or 1
    sy = (sum(y * y for y in ys) / len(ys)) ** 0.5 or 1
    return sorted(outlets, key=lambda n: -((outlets[n][v['x']] / sx) ** 2 + (outlets[n][v['y']] / sy) ** 2))


def view_group(outlets: dict, view: str, shown: bool) -> str:
    """One view of the map: its axes, words at their ends, and a dot per outlet. The wording view leaves out the
    wires themselves: they're the yardstick, measured only against each other"""
    v = VIEWS[view]
    if view == 'style':
        outlets = {n: o for n, o in outlets.items() if not o['is_wire']}
    sx = _scale([o[v['x']] for o in outlets.values()], LEFT, W - RIGHT)
    sy = _scale([o[v['y']] for o in outlets.values()], H - BOTTOM, TOP)
    x0, y0 = sx(0), sy(0)
    parts = [f'<g class="omap-view" data-view="{view}"{"" if shown else ' display="none"'}>',
             f'<line class="sc-grid" x1="{LEFT}" y1="{y0:.1f}" x2="{W - RIGHT}" y2="{y0:.1f}"/>',
             f'<line class="sc-grid" x1="{x0:.1f}" y1="{TOP}" x2="{x0:.1f}" y2="{H - BOTTOM}"/>',
             f'<text class="omap-end" x="{LEFT}" y="{H - 12}">{escape(v["left"])}</text>',
             f'<text class="omap-end" x="{W - RIGHT}" y="{H - 12}" text-anchor="end">{escape(v["right"])}</text>',
             f'<text class="omap-end" x="{LEFT}" y="{TOP - 12}">{escape(v["up"])}</text>',
             f'<text class="omap-end" x="{LEFT}" y="{H - BOTTOM - 6}">{escape(v["down"])}</text>']
    order = distinctive(outlets, view)
    points = [(n, sx(outlets[n][v['x']]), sy(outlets[n][v['y']])) for n in order]
    if v.get('shape'):
        parts.insert(1, density_svg([(x, y) for _, x, y in points], W, H))
    labels = place_labels(points, W, H - BOTTOM + 2)
    for name, x, y in reversed(points):  # the most distinctive drawn last, on top
        o = outlets[name]
        tip = f'{name}: {o["type"] or "no settled type"}'
        # No <title>: the browser's tooltip would cover the card that pops up beside the dot (outlet_map.html)
        parts.append(f'<g class="omap-dot" tabindex="0" role="button" data-name="{escape(name)}" '
                     f'aria-label="{escape(tip)}"><circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{fill(o["lean"])}"/></g>')
    for name, (lx, ly, anchor) in labels.items():
        parts.append(f'<text class="omap-label" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                     f'aria-hidden="true">{escape(short_name(name))}</text>')
    parts.append('</g>')
    return ''.join(parts)


def map_svg(outlets: dict) -> str:
    """Both views in one chart, the coverage view showing; the page's buttons swap them"""
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" class="story-chart omap-chart" '
            f'aria-label="The outlet map: every profiled outlet placed by which stories it covers">'
            f'{view_group(outlets, "coverage", True)}{view_group(outlets, "style", False)}</svg>')


def mini_svg(outlets: dict, me: str, width: int = 220, height: int = 150) -> str:
    """The coverage map small, for an outlet's page: everyone grey, this outlet in its lean color"""
    sx = _scale([o['x'] for o in outlets.values()], 8, width - 8)
    sy = _scale([o['y'] for o in outlets.values()], height - 8, 8)
    parts = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" class="outlet-fp-map" '
             f'aria-label="{escape(me)} on the outlet map">',
             f'<line class="sc-grid" x1="4" y1="{sy(0):.1f}" x2="{width - 4}" y2="{sy(0):.1f}"/>',
             f'<line class="sc-grid" x1="{sx(0):.1f}" y1="4" x2="{sx(0):.1f}" y2="{height - 4}"/>']
    for name, o in outlets.items():
        if name != me:
            parts.append(f'<circle cx="{sx(o["x"]):.1f}" cy="{sy(o["y"]):.1f}" r="2.6" class="outlet-fp-other">'
                         f'<title>{escape(name)}</title></circle>')
    o = outlets[me]
    parts.append(f'<circle cx="{sx(o["x"]):.1f}" cy="{sy(o["y"]):.1f}" r="7" fill="{fill(o["lean"])}" '
                 f'class="outlet-fp-me"><title>{escape(me)}</title></circle></svg>')
    return ''.join(parts)


def fingerprint(profile: dict, name: str) -> dict | None:
    """What an outlet's page shows of its profile, or None when it isn't profiled"""
    o = (profile or {}).get('outlets', {}).get(name)
    if not o:
        return None
    n = len(profile['outlets'])
    return {**o, 'n': n, 'window_days': profile['window_days'],
            'wire_ord': ordinal(o['wire_pct']), 'heat_ord': ordinal(o['heat_pct']),
            'about': outlet_profile.ABOUT.get(o['type'] or '', ''),
            'family_note': o['family'] if o['family'] and o['family'] != o['type'] else None,
            'like': [{'name': x, 'href': f'outlet-{slug(x)}.html'} for x in o['like']],
            'map': mini_svg(profile['outlets'], name)}


BEAT_SHOWN = 5  # stories on an outlet's beat card
BEAT_QUOTED = 2  # stories quoted in the name of a beat its stories' topics don't name
BEAT_QUOTE_CHARS = 60
BEAT_INK = '#ff4fa3'  # the beats' pink: the card's shadow, its rows and the map's board


def _quote(label: str) -> str:
    """A story label, cut at a word to BEAT_QUOTE_CHARS, in curly quotes"""
    if len(label) > BEAT_QUOTE_CHARS:
        label = label[:BEAT_QUOTE_CHARS].rsplit(' ', 1)[0].rstrip(',;:') + '…'
    return f'‘{label}’'


def beat_title(beat: dict) -> str:
    """A beat in a few words: its topic name, or 'stories like ‘…’ and ‘…’' from its first stories"""
    if beat.get('name'):
        return beat['name']
    quoted = [_quote(s['label']) for s in beat['stories'][:BEAT_QUOTED]]
    return 'stories like ' + ' and '.join(quoted) if quoted else 'its own stories'


def _chip(profile: dict, name: str, tip: str) -> dict:
    from app.site.common import chip_style
    lean = profile.get('outlets', {}).get(name, {}).get('lean')
    return {'name': name, 'href': f'outlet-{slug(name)}.html', 'style': chip_style(name, lean or 0), 'tip': tip}


def beat_story_rows(beat: dict, n_outlets: int, with_page: set, only: str | None = None,
                    most: int = BEAT_SHOWN) -> list[dict]:
    """A beat's stories as ranked rows (the bar: how many outlets on the map ran it), linked to their pages; `only`:
    just the ones that outlet ran"""
    from app.site import boards
    from app.site.page_story import page_name
    picked = [s for s in beat['stories'] if only is None or only in s['by']][:most]
    top = max((s['outlets'] for s in picked), default=0)
    return [boards.row(s['label'], page_name(s['id']) if s['id'] in with_page else None, s['outlets'], top,
                       f"{s['outlets']} of {n_outlets}",
                       tip=f"{s['label']}: run by {s['outlets']} of the {n_outlets} outlets on the map",
                       ink=BEAT_INK, mark='🗞️', mark_label='a story') for s in picked]


def beat_card(profile: dict, name: str, with_page: set) -> dict | None:
    """🎯 What an outlet's page shows of its beat: the beat in a few words, the stories of it it ran, the outlets
    leading it with it and those sharing it; None when it leads none"""
    beats = (profile or {}).get('beats') or []
    i = (profile or {}).get('outlets', {}).get(name, {}).get('beat')
    if i is None or not 0 <= i < len(beats):
        return None
    beat = beats[i]
    n = len(profile['outlets'])
    with_it = [_chip(profile, o, f'{o} leads this beat too') for o in beat['leaders'] if o != name]
    shared = [_chip(profile, s['name'], f"{s['name']} ran {s['ran']} of its {len(beat['stories'])} stories, "
                                        f"{s['lift']:g}× as often as it runs our stories in general")
              for s in beat['shared']]
    return {'title': beat_title(beat), 'named': bool(beat.get('name')), 'with': with_it, 'shared': shared,
            'stories': beat_story_rows(beat, n, with_page, only=name), 'held': round(100 * beat['held']),
            'defining': len(beat['stories']), 'window_days': profile.get('window_days')}


def beat_rows(profile: dict, with_page: set) -> list[dict]:
    """🎯 The outlet map's beats: each with its title, leaders and sharers as chips, and its stories for the card"""
    n = len(profile.get('outlets', {}))
    out = []
    for b in profile.get('beats') or []:
        out.append({'title': beat_title(b), 'named': bool(b.get('name')),
                    'leaders': [_chip(profile, o, f'{o}: its page') for o in b['leaders']],
                    'shared': [_chip(profile, s['name'], f"ran {s['ran']} of these {len(b['stories'])} stories, "
                                                         f"{s['lift']:g}× its usual rate") for s in b['shared']],
                    'stories': beat_story_rows(b, n, with_page), 'held': round(100 * b['held'])})
    return out


class OutletMapPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('outlet_map.html', 'outlet-map.html')
        self.context = {'title': 'The outlet map'}

    def generate(self):
        logger.info("Generating the outlet map...")
        try:
            profile = outlet_profile.profiles()
        except Exception:  # noqa: BLE001 - a page without its map beats a build without the page
            logger.exception("Outlet profiles failed; the outlet map is empty this build")
            profile = {}
        outlets = profile.get('outlets', {})
        rows = [{'name': n, 'href': f'outlet-{slug(n)}.html', 'type': o['type'], 'wire_pct': o['wire_pct'],
                 'heat_pct': o['heat_pct'], 'like': o['like'], 'is_wire': o['is_wire'],
                 'lean': dict(LEANS).get(o['lean'], 'not rated'), 'look': type_look(o),
                 'lean_ink': fill(o['lean']), 'lean_mark': LEAN_MARK.get(o['lean'], ''),
                 'like_links': [{'name': x, 'href': f'outlet-{slug(x)}.html'} for x in o['like']]}
                for n, o in sorted(outlets.items(), key=lambda kv: kv[0].removeprefix('The '))]
        dots = {r['name']: {**{k: r[k] for k in ('href', 'type', 'like', 'is_wire', 'lean')},
                            'wire': ordinal(r['wire_pct']), 'heat': ordinal(r['heat_pct'])} for r in rows}
        until = profile.get('until')
        with_page = story_pages() if outlets else set()
        self.context.update({
            'profile': profile, 'svg': map_svg(outlets) if len(outlets) >= 3 else '', 'outlets': rows, 'dots': dots,
            'until': eastern_day(until) if until else '', 'min_stories': outlet_profile.MIN_STORIES,
            'min_articles': outlet_profile.MIN_ARTICLES,
            'views': VIEWS, 'leans': [{'name': nm, 'color': bias_colors[b + 3], 'ink': bias_ink[b + 3]}
                                      for b, nm in LEANS],
            'types': type_rows(profile),
            'pulls': pull_boards(profile, with_page) if outlets else [],
            'beats': beat_rows(profile, with_page) if outlets else [],
            'type_key': type_key([o['type'] for o in outlets.values()]), 'LEAN_INK': LEAN_INK, 'ordinal': ordinal,
        })
        self.template.write(self.context)
        logger.info("...%d outlets on the map", len(outlets))
