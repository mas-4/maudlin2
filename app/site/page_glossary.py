"""How it works: the glossary and methodology page. Its numbers come from the settings the rest of the site uses, so
the page stays true when a threshold changes."""
import re

from app.analysis import clustering, edits, lean_estimate, sagas
from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI
from app.registry import Scrapers, SeleniumScrapers
from app.scraper import FeedScraper, GoogleNewsScraper
from app.site import page_agencies, page_emotions, page_headlines, wordcloudgen
from app.site.common import TemplateHandler, j2env
from app.site.data import DataHandler, STORY_LOOKBACK_HOURS
from app.analysis.llm import DEFAULT_MODELS
from app.utils import get_logger

logger = get_logger(__name__)


class GlossaryPage:
    def __init__(self, dh: DataHandler):
        self.template = TemplateHandler('glossary.html')
        self.context = {'title': 'How it works'}

    def generate(self):
        logger.info("Generating glossary page...")
        feeds = sum(issubclass(s, FeedScraper) and not issubclass(s, GoogleNewsScraper) for s in Scrapers)
        google = sum(issubclass(s, GoogleNewsScraper) for s in Scrapers)
        ph = page_headlines
        self.context.update({
            'outlets': len(Scrapers), 'feeds': feeds, 'google': google, 'selenium': len(SeleniumScrapers),
            'pages': len(Scrapers) - feeds - google - len(SeleniumScrapers),
            'model': DEFAULT_MODELS['ollama'], 'emotions': [(e, EMOTION_EMOJI[e]) for e in EMOTIONS],
            'story_hours': STORY_LOOKBACK_HOURS,
            'story_model': clustering.STORY_MODEL, 'story_threshold': clustering.STORY_THRESHOLDS[clustering.STORY_MODEL],
            'cloud_words': wordcloudgen.CLOUD_WORDS, 'emoji_share': round(100 * wordcloudgen.MIN_EMOTION_SHARE),
            'emoji_outlets': wordcloudgen.MIN_OUTLETS_FOR_EMOJI, 'emoji_max': wordcloudgen.MAX_EMOJI,
            'saga_similarity': sagas.SAGA_SIMILARITY, 'saga_word_share': round(100 * sagas.NAME_MIN_SHARE),
            'saga_word_rare': round(100 * sagas.NAME_MAX_SHARE),
            'story_feeling': round(100 * ph.STORY_EMOTION_SHARE),
            'fresh_hours': ph.NEWS_DAY_FRESH_HOURS, 'half_life': ph.NEWS_DAY_HALF_LIFE_HOURS,
            'tiers': {k: round(100 * v) for k, v in ph.NEWS_DAY_TIERS},
            'break_minutes': ph.BREAK_WINDOW_MINUTES, 'fast_break': ph.FAST_BREAK,
            'blind_outlets': ph.BLINDSPOT_MIN_OUTLETS, 'blind_share': round(100 * ph.BLINDSPOT_SHARE),
            'blind_lift': ph.BLINDSPOT_LIFT,
            'edit_days': edits.WINDOW_DAYS, 'emotion_days': page_emotions.WINDOW_DAYS,
            'outlet_days': page_agencies.WINDOW_DAYS,
            'estimate_days': lean_estimate.WINDOW_DAYS, 'estimate_strength': lean_estimate.MIN_STRENGTH,
            'estimate_rank': lean_estimate.MIN_RANK_AGREEMENT, 'lean_quality': j2env.globals.get('lean_quality'),
            'estimates': len(j2env.globals.get('lean_estimates') or {}),
        })
        self.context['folk'] = folk()
        self.template.write(self.context)
        logger.info("...done")


# The folklore half (Oct 28, the site redo: the page promised every number, badge and emoji on the site and had none of
# the motif side). Each card opens with the real chip, sticker or meter it explains; the motifs named in them are the
# ones the site's own words use as examples (motif.html: Voter fraud is answered by Voter suppression), with what one
# rests on in the index, linked to their pages when this build has them (motif_href falls back to the index).
EXAMPLES = {'motif': ('M806', 'Voter fraud', 'Theories'), 'rests_on': ('M174', 'Rigged election'),
            'answer': ('M875', 'Voter suppression')}


def folk() -> dict:
    """What the folklore cards need, from the settings the folklore pages use"""
    from app import sidefeeds
    from app.analysis import divide, replay
    from app.site import boards, page_aisle
    from app.site.page_motifs import GENRE_EMOJI
    crossover = []
    for s in sidefeeds.SOURCES:  # the crossover shows by name, once each (a show's podcast and video feeds are one show:
        # "Joe Rogan Experience (podcast)", "This Past Weekend w/ Theo Von" beside "Theo Von")
        name = re.sub(r'\s*\((?:podcast|video)\)$', '', s['name'])
        bare = lambda n: n.lower().removeprefix('the ')  # noqa: E731
        if s['group'] == 'crossover' and not any(bare(name) in bare(c) or bare(c) in bare(name) for c in crossover):
            crossover.append(name)
    chips = [sidefeeds.BY_KEY[k]['name'] for k in ('yt_rogan', 'yt_theo') if k in sidefeeds.BY_KEY] or crossover[:2]
    key = [{**k, 'about': ''} for k in boards.genre_key()]  # the genres' glosses are in the card's words
    return {'examples': EXAMPLES, 'genre_key': key, 'genre_emoji': GENRE_EMOJI, 'crossover_chips': chips,
            'genre_ink': boards.GENRE_INK, 'lean_ink': boards.LEAN_INK, 'aisle_ink': page_aisle.LEAN_INK, 'crossover': crossover,
            'replay_words': replay.K, 'replay_shows': replay.MIN_SHOWS, 'replay_days': replay.DAYS,
            'divide_draws': divide.DRAWS, 'divide_full': divide.FULL_TRANSCRIPTS,
            'only_least': page_aisle.ONLY_LEAST, 'rising_min': page_aisle.RISING_MIN}
