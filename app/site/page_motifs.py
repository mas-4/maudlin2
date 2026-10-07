"""The motif index page (#145): our own index of the recurring shapes of today's political rumors and narratives
(app/analysis/motif_index.py), each with the claims filed under it."""
from collections import Counter

from app.analysis import accusations, motif_index
from app.site.common import TemplateHandler
from app.utils import get_logger

logger = get_logger(__name__)


class MotifsPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('motifs.html')

    def generate(self):
        logger.info("Generating motif index page...")
        index = motif_index.load()
        entries = []
        screen = accusations.screen()  # claims accusing a named private person of a crime: name swapped out, or held
        for e in motif_index.live(index):
            claims = motif_index.public_claims(e) if motif_index.public(e) else []  # only motifs a person verified
            claims = [{**c, 'claim': shown} for c in claims
                      if (shown := screen.shown(motif_index.corrected(c['claim'], index), c['source']))]
            if not claims:
                continue
            sources = Counter('people online' if c['source'] == 'narrative' else c['source'] for c in claims)
            entries.append({**e, 'note': motif_index.public_note(e), 'count': len(claims), 'sources': sources.most_common(),
                            'claims': sorted(claims, key=lambda c: c.get('date', ''), reverse=True)})
        entries.sort(key=lambda e: (-e['count'], e['id']))
        screen.save()
        self.template.write({'title': 'Motif index', 'entries': entries,
                             'claims': sum(e['count'] for e in entries),
                             'recurring': sum(1 for e in entries if e['count'] > 1)})
        logger.info("...%d motifs", len(entries))
