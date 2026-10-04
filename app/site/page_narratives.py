"""Narratives (work in progress, #142): the folklore-shaped narratives in what people say on Bluesky and Mastodon, from the
latest nightly report (app/narratives.py). A card per retold narrative: the claim in the model's words, how many
people tell it and how varied their wording is, its genre and Motif-Index motif, who it casts as villain, victim and
hero, and the news story it rides on.

People's own posts are never shown on the published site, only the model's summary of what they share: even without
handles, a quoted post can be searched back to its author. Local preview builds (debug) show a few versions, so the
research can be checked."""
import glob
import json
import os
from collections import Counter

from app.site.common import TemplateHandler
from app.utils import Config, get_logger

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
GENRE_EMOJI = {'rumor': '🗣️', 'contemporary legend': '🏙️', 'conspiracy theory': '🕸️', 'folk belief': '🔮',
               'prophecy or prediction': '🔭', 'cautionary tale': '⚠️', 'atrocity story': '🩸', 'trickster tale': '🦊',
               'joke formula or meme': '🤡', 'proverb or catchphrase': '📜', 'personal testimony': '🙋',
               'news report or shared reaction': '📣'}
SIDE_INK = {'left': '#1a5cff', 'right': '#e0102e', 'both': '#7a3fd1', 'none': '#8a8f98'}


def latest_report() -> dict | None:
    reports = sorted(glob.glob(os.path.join(FOLDER, 'report-*.json')))
    if not reports:
        return None
    with open(reports[-1]) as f:
        return json.load(f)


class NarrativesPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('narratives.html')

    def generate(self):
        logger.info("Generating narratives page...")
        report = latest_report()
        cards, copies = [], []
        if report:
            for g in report['found']:
                label = g.get('label') or {}
                if label.get('retold'):
                    cards.append({
                        'claim': label.get('narrative') or '', 'people': g['authors'], 'posts': g['posts'],
                        'variety': g['variety'], 'variety_pct': round(100 * g['variety']),
                        'genre': label.get('genre', ''), 'genre_emoji': GENRE_EMOJI.get(label.get('genre'), '🧶'),
                        'chapter': label.get('motif_chapter', ''), 'motif': label.get('motif', ''),
                        'villain': label.get('villain'), 'victim': label.get('victim'), 'hero': label.get('hero'),
                        'politics': bool(label.get('politics')), 'side': label.get('side', 'none'),
                        'side_ink': SIDE_INK.get(label.get('side'), '#8a8f98'),
                        'story': g.get('story'), 'voters': g.get('voters') or [],
                        'examples': g['examples'][:4] if Config.debug else [],
                    })
                elif g['kind'] == 'copypasta':
                    copies.append({'people': g['authors'], 'posts': g['posts'],
                                   'example': g['examples'][0] if Config.debug else None})
        self.template.write({
            'title': 'Narratives', 'report': report, 'cards': cards, 'copies': copies,
            'genres': Counter(c['genre'] for c in cards).most_common(), 'genre_emoji': GENRE_EMOJI,
            'preview': Config.debug,
        })
        logger.info("...%d narratives, %d copypasta groups", len(cards), len(copies))
