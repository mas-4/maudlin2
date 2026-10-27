"""The aisle (Oct 27, the person: the motif map "is so big it's hard to read, interact with, and isn't even all that
interesting"): the motif map redrawn as the stories told across the political aisle. Each motif the shows we follow
told is a dot, placed left to right by which side's shows its claims came up on (blue left, red right, both in the
middle), and up by how many tellers told it; the motifs a person marked as each other's answer are joined by an arc
over the aisle. A story people tell, never a claim that it's true. Drawn as one inline SVG (docs/style-book.md:
charts in Python), with a little script to pick a motif, filter by genre and search. It replaces the force-directed
map at the same address (motif-map.html); the checker keeps its own map for curation."""
import hashlib
import math

from markupsafe import Markup, escape

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


def place(web: dict) -> list[dict]:
    """Every public motif told on the shows: its lean (-1 all left to 1 all right, pulled toward the middle when few
    shows told it), how many told it, its genre, note and counts"""
    from app.analysis import motif_web
    by = {}
    for r in web['rows']:
        by.setdefault(r['motif'], []).append(r)
    out = []
    for m, rs in by.items():
        s = motif_web.sided(rs)
        left, right, center = len(s['left']), len(s['right']), len(s['center'])
        if not (left or right or center):
            continue
        e = web['entries'][m]
        out.append({'id': m, 'name': e['name'], 'genre': rs[0]['genre'], 'note': e.get('note', '') if e.get('note_by') not in ('model', 'claude') else '',
                    'left': left, 'right': right, 'center': center, 'posts': s['posts'], 'checks': len(s['checks']),
                    'lean': (right - left) / (right + left + 2),
                    'told': len({(r['kind'], r['teller'], r['key']) for r in rs}),
                    'href': motif_href(m)})
    return out


def draw(dots: list[dict], arcs: list[tuple[str, str, str]]) -> Markup:
    """The aisle as SVG: dots, the most told labelled, answers as arcs"""
    top = max((d['told'] for d in dots), default=1)
    x = lambda lean: PAD_X + (lean + 1) / 2 * (W - 2 * PAD_X)  # noqa: E731
    y = lambda told: H - PAD_BOTTOM - (math.log1p(told) / math.log1p(top)) * (H - PAD_TOP - PAD_BOTTOM)  # noqa: E731
    # Few shows give a motif one of a handful of leans (1 of 3, 2 of 4...), so dots would stand in columns: each is
    # spread a little sideways and up, by a fixed amount from its id, so the columns fan out the same way every build
    def spread(mid: str, scale: float) -> float:
        h = int(hashlib.sha1(mid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return (h * 2 - 1) * scale
    at = {d['id']: (x(d['lean']) + spread(d['id'], JITTER_X), y(d['told']) + spread(d['id'][::-1], JITTER_Y)) for d in dots}
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
    taken = []
    for d in sorted(dots, key=lambda d: d['told']):  # the most told drawn last, on top
        cx, cy = at[d['id']]
        r = 4 + 9 * math.sqrt(d['told'] / top)
        ink = LEAN_INK['left'] if d['lean'] < -0.2 else LEAN_INK['right'] if d['lean'] > 0.2 else '#6b6f78'
        parts.append(f'<a href="{d["href"]}" class="aisle-dot" data-id="{escape(d["id"])}" data-genre="{escape(d["genre"])}" '
                     f'data-name="{escape(d["name"].lower())}"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{ink}"/>'
                     f'<title>{escape(d["name"])}: {d["left"]} left, {d["center"]} center, {d["right"]} right shows</title></a>')
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
        both = sorted((d for d in dots if d['left'] and d['right']), key=lambda d: -min(d['left'], d['right']))[:12]
        self.template.write({
            'title': 'The aisle', 'svg': draw(dots, arcs), 'dots': dots, 'arcs': len(arcs),
            'genres': [(g, GENRE_EMOJI.get(g, '🧩'), sum(1 for d in dots if d['genre'] == g)) for g in genres],
            'unplaced': len(web['entries']) - len(dots), 'both': both,
            'leftmost': sorted((d for d in dots if d['lean'] < -0.4), key=lambda d: -d['told'])[:8],
            'rightmost': sorted((d for d in dots if d['lean'] > 0.4), key=lambda d: -d['told'])[:8],
            'og_title': 'The aisle: the stories each side tells · bignews.day',
            'og_description': 'Every story shape in our motif index, placed by which side\'s shows tell it, with the '
                              'answers each side gives the other.'})
        logger.info("...%d motifs on the aisle, %d answers", len(dots), len(arcs))
