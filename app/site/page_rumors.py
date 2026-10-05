"""Rumors (#153): the fact-checkers' work from the last few weeks as a running catalog of the rumors circulating,
each read for its shape the way the folklore page reads what people retell (app/analysis/factchecks.py,
app/analysis/rumor_shapes.py): genre, rumor class, conspiracy scope, subject. The verdict is always the
fact-checker's own, behind its link: the model doesn't rate claims."""
from collections import Counter

from app.analysis import circulation, factchecks, motif_index
from app.analysis.rumor_shapes import CONSPIRACY_SCOPES, EMOJI as SHAPE_EMOJI, RUMOR_CLASSES
from app.site.common import TemplateHandler
from app.site.page_folklore import GENRE_EMOJI, motif_cards, motif_counts
from app.utils import Config, get_logger

logger = get_logger(__name__)

DAYS = 30


class RumorsPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('rumors.html')

    def generate(self):
        logger.info("Generating rumors page...")
        try:
            items = factchecks._items(DAYS)
            labels = factchecks.label_all(items)
        except Exception as e:  # noqa: e.g. no side_item table on a database that hasn't migrated
            logger.warning("Rumors: %s", e)
            items, labels = [], {}
        looked = circulation.load()
        index = motif_index.load()
        seen = looked.get('claims', {})
        cards = []
        for item in items:
            label = labels.get(item['url'])
            if not label or not label.get('claim'):
                continue  # not labeled yet, or a roundup that checks no single claim
            cards.append({**item, 'claim': label['claim'], 'genre': label.get('genre', ''),
                          'genre_emoji': GENRE_EMOJI.get(label.get('genre'), '🧶'),
                          'rumor_class': label.get('rumor_class') if label.get('rumor_class') != 'other' else None,
                          'conspiracy': (label.get('conspiracy') if label.get('conspiracy') != 'not a conspiracy'
                                         else None),
                          'family': label.get('family') if label.get('family') != 'none' else None,
                          'date': item['published'][:10],
                          'seen': seen.get(item['url']) if looked else None,
                          'motifs': motif_cards(index, label['claim'])})
        count = lambda key: Counter(c[key] for c in cards if c[key]).most_common()
        self.template.write({
            'preview': Config.debug,  # the conspiracy scope shows only in previews until it's reliable (Oct 4)
            'title': 'Rumors', 'cards': cards, 'days': DAYS, 'rumor_classes': RUMOR_CLASSES,
            'conspiracy_scopes': CONSPIRACY_SCOPES, 'shape_emoji': SHAPE_EMOJI,
            'class_counts': count('rumor_class'), 'scope_counts': count('conspiracy'),
            'family_counts': count('family'), 'source_counts': count('source'),
            'motif_counts': motif_counts(cards), 'with_motifs': sum(bool(c['motifs']) for c in cards),
            'looked': looked, 'seen_count': sum(1 for c in cards if c['seen'] and c['seen']['people']),
        })
        logger.info("...%d fact-checked rumors", len(cards))
