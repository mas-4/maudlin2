"""One page per outlet (#126), outlet-<slug>.html (at the top level, so the site's relative links work): who it is (ratings, owner, Wikipedia), its measures (spin, mood,
framing, feelings, rewrites, wire copy), what's on its front page now and which of our stories each headline is part
of, and its recent rewrites. Built from the outlets page's profiles, after the front page (for the story links)."""
import os

import pandas as pd

from app.analysis.edits import find_edits, judge_edits
from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI, emotion_weights
from app.site.common import SHARED, TemplateHandler
from app.site.data import DataHandler
from app.utils import Config, get_logger

logger = get_logger(__name__)

FEELING_COLORS = {'fear': '#8a5cff', 'anger': '#e0102e', 'sadness': '#3a86ff', 'disgust': '#4caf50',
                  'surprise': '#ffc400', 'joy': '#ff6b1a', 'hope': '#00c2a8', 'neutral': '#c8c8d0'}
MAX_REWRITES = 12



def feelings(ranks: pd.Series) -> list[dict]:
    """Each feeling's share of an outlet's headlines, ranked-choice style (emotion_weights), biggest first."""
    totals = pd.Series(0.0, index=EMOTIONS)
    n = 0
    for r in ranks.dropna():
        for e, w in emotion_weights(r).items():
            totals[e] += w
        n += 1
    if not n:
        return []
    return [{'name': e, 'emoji': EMOTION_EMOJI[e], 'share': round(100 * totals[e] / n), 'color': FEELING_COLORS[e]}
            for e in totals.sort_values(ascending=False).index if totals[e] > 0]


class OutletPages:
    def __init__(self, dh: DataHandler, outlets: list[dict], window_days: int):
        self.dh = dh
        self.outlets = outlets
        self.window_days = window_days
        self.template = TemplateHandler('outlet.html')

    def generate(self):
        live = self.dh.main_headline_df
        story_of_url = SHARED.get('story_of_url', {})
        edits, _ = find_edits()
        judged = judge_edits([(e['before'], e['after']) for _, e in edits.iterrows()]) if not edits.empty else {}
        for o in self.outlets:
            mine = live[live['agency'] == o['name']]
            now = [{'title': r.title, 'url': r.url, 'story': story_of_url.get(r.url)}
                   for r in mine.sort_values('position').itertuples()] if not mine.empty else []
            rewrites = []
            if not edits.empty:
                for _, e in edits[edits['agency'] == o['name']].head(MAX_REWRITES).iterrows():
                    j = judged.get((e['before'], e['after'])) or {}
                    rewrites.append({'before': e['before_html'], 'after': e['after_html'], 'change': j.get('change')})
            self.template.write({'title': o['name'], 'o': o, 'now': now, 'rewrites': rewrites, 'window_days': self.window_days,
                                 'feelings': feelings(mine['emotion_ranks']) if 'emotion_ranks' in mine else []},
                                os.path.join(Config.build, f"outlet-{o['slug']}.html"))
        logger.info("Outlet pages: %d", len(self.outlets))
