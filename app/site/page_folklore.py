"""Folklore (work in progress, #142): the folklore-shaped narratives in what people say on Bluesky and Mastodon, from the
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

from app.analysis.rumor_shapes import CONSPIRACY_SCOPES, EMOJI as SHAPE_EMOJI, RUMOR_CLASSES
from app.site.common import TemplateHandler
from app.utils import Config, get_logger

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
GENRE_EMOJI = {'rumor': '🗣️', 'contemporary legend': '🏙️', 'conspiracy theory': '🕸️', 'folk belief': '🔮',
               'prophecy or prediction': '🔭', 'cautionary tale': '⚠️', 'atrocity story': '🩸', 'trickster tale': '🦊',
               'joke formula or meme': '🤡', 'proverb or catchphrase': '📜', 'personal testimony': '🙋',
               'news report or shared reaction': '📣'}
# Fewer tellers than this aren't shown: at five to nine people (half of what the finder keeps) most groups are a
# handful reacting to the same news, not a story people retell. The floor grows with the sample, 1 in PEOPLE_SHARE.
MIN_PEOPLE = 10
PEOPLE_SHARE = 2500
# Plain glosses, in our words, of what each Motif-Index chapter covers (shown on hover and in "What the labels mean")
CHAPTER_NOTES = {
    'A': 'creators, gods, and how the world began or will end', 'B': 'talking, helpful or monstrous animals',
    'C': 'forbidden acts and what happens to people who break the rule',
    'D': 'transformations, enchantments, magic objects and powers', 'E': 'ghosts, the soul, returns from the dead',
    'F': 'wonders, other worlds, extraordinary beings and places', 'G': 'monsters, witches and other menaces',
    'H': 'trials of identity, wit, strength or worth', 'J': 'cleverness and stupidity, good and bad judgment',
    'K': 'tricks, disguises, frauds, hidden plots and false appearances',
    'L': 'the lowly raised up, the proud brought down', 'M': 'oaths, bargains, curses and prophecies',
    'N': 'luck, accidents and fate', 'P': 'rulers, classes, families, trades and customs',
    'Q': 'deeds paid back, rewarded or punished', 'R': 'captures, rescues and escapes',
    'S': 'cruel relatives, murders, abandonment and sacrifice', 'T': 'love, marriage, seduction and birth',
    'U': 'how life and the world work', 'V': 'worship, saints, religious belief and practice',
    'W': 'virtues and vices', 'X': 'jokes about kinds of people, absurd lies',
    'Z': 'formulas, symbols, numbers and other patterns',
}
GENRE_NOTES = {
    'rumor': 'an unconfirmed claim passed along as news ("I heard that…")',
    'contemporary legend': 'a story told as true and recent, often about a friend of a friend (the folklorists\' '
                           'name for an "urban legend")',
    'conspiracy theory': 'a hidden group said to be secretly behind events',
    'folk belief': 'something held as known without evidence, often about health, luck or how the world works',
    'prophecy or prediction': "what's going to happen",
    'cautionary tale': 'a story told as a warning',
    'atrocity story': "a story of shocking cruelty by the other side, told to show what they're like",
    'trickster tale': 'a clever figure outwitting the powerful',
    'joke formula or meme': 'a joke shape people refill with new content',
    'proverb or catchphrase': 'a stock saying or slogan repeated as wisdom',
    'personal testimony': 'many people telling the same kind of experience as their own',
    'news report or shared reaction': 'many people passing on, or reacting to, the same news; not folklore in '
                                      'itself, kept for comparison',
}
NOT_STORIES = {'news report or shared reaction', 'none: a shared topic, not a retold narrative'}  # no cast or motif
SIDE_INK = {'left': '#1a5cff', 'right': '#e0102e', 'both': '#7a3fd1', 'none': '#8a8f98'}


WITHHELD = os.path.join(FOLDER, 'withheld.json')  # narratives pulled by hand: [{claim, reason, at}]


def withheld() -> set[str]:
    """Claims withheld from the page by hand after a misreading (Oct 4: a group of trans people talking about their
    own identity was labeled as spreading an anti-trans claim one of them had quoted)."""
    try:
        with open(WITHHELD) as f:
            return {w['claim'] for w in json.load(f)}
    except (OSError, ValueError):
        return set()


def latest_report() -> dict | None:
    reports = sorted(glob.glob(os.path.join(FOLDER, 'report-*.json')))
    if not reports:
        return None
    with open(reports[-1]) as f:
        return json.load(f)


class FolklorePage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('folklore.html')

    def generate(self):
        logger.info("Generating folklore page...")
        report = latest_report()
        cards, copies, fewer = [], [], 0
        pulled = withheld()
        floor = max(MIN_PEOPLE, round(report['authors'] / PEOPLE_SHARE)) if report else MIN_PEOPLE
        if report:
            for g in report['found']:
                label = g.get('label') or {}
                if label.get('narrative') in pulled:
                    continue
                if label.get('retold') and g['authors'] < floor:
                    fewer += 1
                elif label.get('retold'):
                    cards.append({
                        'claim': label.get('narrative') or '', 'people': g['authors'], 'posts': g['posts'],
                        'variety': g['variety'], 'variety_pct': round(100 * g['variety']),
                        'genre': label.get('genre', ''), 'genre_emoji': GENRE_EMOJI.get(label.get('genre'), '🧶'),
                        'chapter': '' if label.get('motif_chapter') in (None, '', 'none') else label['motif_chapter'],
                        'motif': label.get('motif', ''),
                        'villain': label.get('villain'), 'victim': label.get('victim'), 'hero': label.get('hero'),
                        'politics': bool(label.get('politics')),
                        # Shown on the site only from evidence (the lean of the outlets its posts share); the
                        # model's guess, unchecked, only in previews
                        'side': g.get('shared_side') or (label.get('side', 'none') if Config.debug else None),
                        'side_from': 'shares' if g.get('shared_side') else 'model',
                        'side_ink': SIDE_INK.get(g.get('shared_side') or label.get('side'), '#8a8f98'),
                        'story_shape': label.get('genre') not in NOT_STORIES,
                        'rumor_class': label.get('rumor_class') if label.get('rumor_class') != 'other' else None,
                        'conspiracy': label.get('conspiracy') if label.get('conspiracy') != 'not a conspiracy' else None,
                        'family': label.get('family') if label.get('family') != 'none' else None,
                        'story': g.get('story'), 'articles': g.get('articles') or [],
                        'factchecks': g.get('factchecks') or [],
                        'examples': g['examples'][:4] if Config.debug else [],
                    })
                elif g['kind'] == 'copypasta':
                    copies.append({'people': g['authors'], 'posts': g['posts'],
                                   'example': g['examples'][0] if Config.debug else None})
        self.template.write({
            'title': 'Folklore', 'report': report, 'cards': cards, 'copies': copies,
            'floor': floor, 'fewer': fewer, 'genres': Counter(c['genre'] for c in cards).most_common(), 'genre_emoji': GENRE_EMOJI,
            'genre_notes': GENRE_NOTES, 'chapter_notes': CHAPTER_NOTES,
            'rumor_classes': RUMOR_CLASSES, 'conspiracy_scopes': CONSPIRACY_SCOPES, 'shape_emoji': SHAPE_EMOJI,
            'class_counts': Counter(c['rumor_class'] for c in cards if c['rumor_class']).most_common(),
            'scope_counts': Counter(c['conspiracy'] for c in cards if c['conspiracy']).most_common(),
            'chapters_seen': sorted({c['chapter'] for c in cards if c['chapter']}),
            'preview': Config.debug,
        })
        logger.info("...%d narratives, %d copypasta groups", len(cards), len(copies))
