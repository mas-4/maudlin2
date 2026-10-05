"""The motif index page (#145): our own index of the recurring shapes of today's political rumors and narratives
(app/analysis/motif_index.py), each with the claims filed under it."""
from collections import Counter

from app.analysis import motif_index
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
        for e in motif_index.live(index):
            sources = Counter('people online' if c['source'] == 'narrative' else c['source'] for c in e['claims'])
            entries.append({**e, 'note': motif_index.public_note(e), 'count': len(e['claims']), 'sources': sources.most_common(),
                            'claims': sorted(e['claims'], key=lambda c: c.get('date', ''), reverse=True)})
        entries.sort(key=lambda e: (-e['count'], e['id']))
        self.template.write({'title': 'Motif index', 'entries': entries,
                             'claims': sum(e['count'] for e in entries),
                             'recurring': sum(1 for e in entries if e['count'] > 1)})
        logger.info("...%d motifs", len(entries))
