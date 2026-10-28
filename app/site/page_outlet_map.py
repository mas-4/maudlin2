"""🗺️ The outlet map (Oct 28): every outlet we read on enough of our stories, placed by which stories it covers (the
coverage axes of app.analysis.outlet_profile), with a second view on how it words them (wire × heat). Dots in the
outlets' lean colors, the most distinctive labeled, every one named on hover or tap. Drawn as inline SVG, like the
story charts, and opens full screen the same way (svg.story-chart). Also draws the small map on each outlet's page."""
from datetime import datetime as dt
from html import escape

import pytz

from app.analysis import outlet_profile
from app.site.common import TemplateHandler, short_name
from app.site.data import DataHandler
from app.site.favicons import slug
from app.site.graphing import bias_colors, bias_ink
from app.utils import get_logger

logger = get_logger(__name__)

W, H = 760, 560
LEFT, RIGHT, TOP, BOTTOM = 30, 14, 30, 40
MAX_LABELS = 30
CHAR_W = 7.0  # a label's width per character at 12px, near enough to keep labels apart
UNRATED = '#ffffff'
VIEWS = {
    'coverage': {'x': 'x', 'y': 'y', 'name': '🗞️ Which stories it covers',
                 'left': '← business, tech and world', 'right': 'the political fight →',
                 'up': '↑ stories critical of Trump', 'down': '↓ crime and immigration'},
    'style': {'x': 'wire', 'y': 'heat', 'name': '🌶️ How it words them',
              'left': '← its own agenda and words', 'right': 'close to AP and Reuters →',
              'up': '↑ heated wording', 'down': '↓ calm wording'},
}
LEANS = [(-2, 'Left'), (-1, 'Lean left'), (0, 'Center'), (1, 'Lean right'), (2, 'Right')]


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
                 'lean': dict(LEANS).get(o['lean'], 'not rated')}
                for n, o in sorted(outlets.items(), key=lambda kv: kv[0].removeprefix('The '))]
        dots = {r['name']: {**{k: r[k] for k in ('href', 'type', 'like', 'is_wire', 'lean')},
                            'wire': ordinal(r['wire_pct']), 'heat': ordinal(r['heat_pct'])} for r in rows}
        until = profile.get('until')
        self.context.update({
            'profile': profile, 'svg': map_svg(outlets) if len(outlets) >= 3 else '', 'outlets': rows, 'dots': dots,
            'until': eastern_day(until) if until else '', 'min_stories': outlet_profile.MIN_STORIES,
            'min_articles': outlet_profile.MIN_ARTICLES,
            'views': VIEWS, 'leans': [{'name': nm, 'color': bias_colors[b + 3], 'ink': bias_ink[b + 3]}
                                      for b, nm in LEANS],
            'types': [{**t, 'members': [{'name': m, 'href': f'outlet-{slug(m)}.html',
                                         'bias': outlets[m]['lean'] or 0} for m in t['members']]}
                      for t in profile.get('types', [])],
        })
        self.template.write(self.context)
        logger.info("...%d outlets on the map", len(outlets))
