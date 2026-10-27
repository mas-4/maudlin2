"""A page for each show we transcribe (Oct 27): what it tells, as the motif index files its claims. Its repertoire
(the motifs its claims came up in), its signature (the motifs it tells far more than the other shows: weighted
log-odds, motif_web.shows), the shows that tell the most alike (by their motifs, not by their lean), and its latest
claims. A map of the shows by the stories they tell."""
import os

from app.analysis import motif_web
from app.site.common import TemplateHandler
from app.site.page_motif import LEAN_INK, shared
from app.utils import get_logger
from app.utils.config import Config

logger = get_logger(__name__)

LATEST = 30  # claims listed, newest first
REPERTOIRE = 40  # motifs listed in its repertoire


def show_href(show: str) -> str:
    return f'show-{motif_web.show_slug(show)}.html'


class ShowPages:
    def __init__(self, dh=None):
        self.template = TemplateHandler('show.html')

    def generate(self):
        logger.info("Generating show pages...")
        web = shared()['web']
        shows = web['shows']
        for name, sh in shows.items():
            mine = sorted((r for r in web['rows'] if r['kind'] == 'shows' and r['teller'] == name),
                          key=lambda r: r['date'], reverse=True)
            latest, seen = [], set()
            for r in mine:
                if r['key'] in seen:
                    for c in latest:
                        if c['key'] == r['key'] and r['motif'] not in [m[0] for m in c['motifs']]:
                            c['motifs'].append((r['motif'], r['name']))
                    continue
                seen.add(r['key'])
                if len(latest) < LATEST:
                    latest.append({'key': r['key'], 'claim': r['claim'], 'date': r['date'], 'url': r['url'],
                                   'motifs': [(r['motif'], r['name'])]})
            self.template.write({
                'title': name, 'og_title': f'What {name} tells · bignews.day',
                'og_description': f"The stories {name} tells, from our motif index: "
                                  + ', '.join(n for _, n, _ in sh['signature'][:5]) + '.',
                'sh': sh, 'ink': LEAN_INK.get(sh['lean'] or '', '#b8b8c8'), 'latest': latest,
                'repertoire': sh['motifs'][:REPERTOIRE], 'neighbours': [(o, round(100 * x)) for o, x in sh['neighbours']],
                'show_href': show_href, 'inks': LEAN_INK, 'leans': {o: shows[o]['lean'] for o in shows},
            }, os.path.join(Config.build, show_href(name)))
        logger.info("...%d show pages", len(shows))
