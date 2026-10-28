"""Older than you think (echoes.html): today's motifs told in 1896 newspapers (Oct 28, the person: the historical echoes
are "one of the things I am *most* eager to see live").

Each echo pairs a motif from today's index with a claim from a real 1896 paper, filed to it by the same pipeline that
files today's claims (Rip Van Winkle, papers/rip-van-winkle.md), read and approved by the person (scripts/echoes.py).
A card: 2026 on one side (the motif, its note, one of its claims this year), 1896 on the other (the quote, the paper,
the day, a link to the page scan at the Library of Congress, and how many papers printed it). Above the cards, the
echoes told in the most papers as a ranked strip: 1896's viral copy."""
import html
from datetime import datetime as dt

from app.analysis import echoes
from app.site import boards
from app.site.common import TemplateHandler, motif_href
from app.utils import get_logger

logger = get_logger(__name__)

VIRAL_LEAST = 2  # papers that printed it, for the viral strip
VIRAL_ROWS = 10


def paper_name(paper: str) -> str:
    """Chronicling America's title cut to the paper's name: "The Salt Lake herald. [volume] (Salt Lake City [Utah])
    1870-1909" -> "The Salt Lake Herald" """
    name = html.unescape(paper or '').split(' [volume]')[0].split(' (')[0].rstrip('. ')
    small = {'of', 'the', 'and', 'a', 'on'}
    return ' '.join(w if i and w.lower() in small else w[:1].upper() + w[1:] for i, w in enumerate(name.split()))


def day(date: str) -> str:
    try:
        return dt.strptime(date, '%Y-%m-%d').strftime('%B %-d, %Y')
    except (TypeError, ValueError):
        return date or ''


def today_claim(entry: dict | None) -> str:
    """One of the motif's public claims this year, the newest, for the 2026 side of the card"""
    if not entry:
        return ''
    from app.analysis import motif_index as mi
    claims = sorted(mi.public_claims(entry), key=lambda c: c.get('date') or '', reverse=True)
    return claims[0]['claim'] if claims else ''


def cards(rows: list[dict], entries: dict) -> list[dict]:
    from app.analysis import motif_index as mi
    from app.site.page_motifs import GENRE_EMOJI
    out = []
    for r in rows:
        e = entries.get(r['motif'])
        genre = (e or {}).get('facets', {}).get('genre') if e else None
        out.append({'id': r['id'], 'motif': r['motif'], 'name': e['name'] if e else r['motif_name'],
                    'href': motif_href(r['motif']), 'note': mi.public_note(e) if e else '',
                    'genre': genre or 'No genre yet', 'mark': GENRE_EMOJI.get(genre, '🧩'),
                    'ink': boards.GENRE_INK.get(genre, boards.UNCOLORED), 'today': today_claim(e),
                    'quote': r['quote_clean'] or r['quote'], 'ocr': r['quote'], 'headline': (r['headline'] or '').strip(),
                    'paper': paper_name(r['paper']), 'place': r['place'], 'day': day(r['date']), 'url': r['url'],
                    'papers': r['retold'] or 1, 'why': r['why'] or '', 'reviewer': r.get('reviewer') or 'person'})
    return out


def viral(rows: list[dict]) -> dict | None:
    """The echoes printed in the most papers, as a ranked strip"""
    told = sorted((c for c in rows if c['papers'] >= VIRAL_LEAST), key=lambda c: -c['papers'])[:VIRAL_ROWS]
    if not told:
        return None
    top = told[0]['papers']
    strip = [boards.row(c['name'], f"#echo-{c['id']}", c['papers'], top, f"{c['papers']} papers",
                        tip=f"1896: “{c['quote']}” ({c['paper']}, {c['day']})", ink=c['ink'], mark=c['mark'],
                        mark_label=c['genre']) for c in told]
    return boards.board('viral', '🗞️', 'Viral in 1896', '#ffc400', 'the claims 1896 papers printed again and again; the '
                        'bar is how many papers carried it, as near-copies of each other', strip)


class EchoesPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('echoes.html')

    def generate(self):
        from app.analysis import motif_index as mi
        logger.info("Generating the echoes page...")
        rows = echoes.approved()
        entries = mi.load()['entries'] if rows else {}
        shown = cards(rows, entries)
        self.template.write({
            'title': 'Older than you think', 'cards': shown, 'viral': viral(shown),
            'genre_key': boards.genre_key([{'genre': c['genre']} for c in shown]) if shown else [],
            'og_description': "Today's political story shapes, told in 1896 newspapers: the same plots, the same "
                              "villains, 130 years apart.",
        })
        logger.info("...%d echoes", len(shown))
