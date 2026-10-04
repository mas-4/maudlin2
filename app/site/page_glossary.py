"""How it works: the glossary and methodology page. Its numbers come from the settings the rest of the site uses, so
the page stays true when a threshold changes."""
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
        self.template.write(self.context)
        logger.info("...done")
