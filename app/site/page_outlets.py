"""One page per outlet (#126), outlet-<slug>.html (at the top level, so the site's relative links work): who it is (ratings, owner, Wikipedia), its measures (spin, mood,
framing, feelings, rewrites, wire copy), what's on its front page now and which of our stories each headline is part
of, and its recent rewrites. Built from the outlets page's profiles, after the front page (for the story links).

Oct 28 (the site redo): its measures read against the median outlet ("7.1 rewrites per 100" alone said nothing); the
feelings bar became a diverging strip against the average outlet ("more anger than most | less hope"); and its front
page, a numbered list of every headline (Fox's ran to 86), is split in two: With the pack (headlines in our stories,
by the story's rank) | Only here (headlines in none of our stories: no one else ran them, as far as our matching can
tell)."""
import os

import pandas as pd

from app.analysis import outlet_profile
from app.analysis.edits import find_edits
from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI, emotion_weights
from app.site.common import SHARED, TemplateHandler
from app.site.data import DataHandler
from app.site.page_outlet_map import fingerprint
from app.utils import Config, get_logger

logger = get_logger(__name__)

FEELING_COLORS = {'fear': '#8a5cff', 'anger': '#e0102e', 'sadness': '#3a86ff', 'disgust': '#4caf50',
                  'surprise': '#ffc400', 'joy': '#ff6b1a', 'hope': '#00c2a8', 'neutral': '#c8c8d0'}
FEELING_WORDS = {'neutral': 'no strong feeling'}
MAX_REWRITES = 12
NOW_SHOWN = 12  # headlines in each front-page list before the rest fold away
FEELING_MIN = 5  # live headlines an outlet needs to count toward the average outlet's feelings
FEELING_EVEN = 2  # percentage points: closer to the average than this is "about the same"


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


def feeling_shares(ranks: pd.Series) -> dict[str, float] | None:
    """Each feeling's share of the headlines, in percent, unrounded; None without any read"""
    totals, n = dict.fromkeys(EMOTIONS, 0.0), 0
    for r in ranks.dropna():
        for e, w in emotion_weights(r).items():
            totals[e] += w
        n += 1
    return {e: 100 * v / n for e, v in totals.items()} if n else None


def average_feelings(live: pd.DataFrame) -> dict[str, float]:
    """The average outlet's feelings now: each outlet with FEELING_MIN or more headlines read counts once"""
    per = [feeling_shares(g['emotion_ranks']) for _, g in live.groupby('agency')
           if g['emotion_ranks'].notna().sum() >= FEELING_MIN]
    per = [p for p in per if p]
    return {e: sum(p[e] for p in per) / len(per) for e in EMOTIONS} if per else {}


def feeling_strip(mine: dict | None, average: dict) -> dict | None:
    """Its feelings against the average outlet's: a row per feeling, the furthest above first, each with the
    difference in percentage points (the diverging bar) and both shares; and the headline words, the feeling it has
    most more of than most outlets and the one it has most less of"""
    if not mine or not average:
        return None
    rows = []
    for e in EMOTIONS:
        diff = mine[e] - average[e]
        name = FEELING_WORDS.get(e, e)
        rows.append({'name': name, 'emoji': EMOTION_EMOJI[e], 'diff': round(diff),
                     'more_words': 'calmer than most' if e == 'neutral' else f'more {name} than most',
                     'less_words': 'less calm' if e == 'neutral' else f'less {name}',
                     'mine': round(mine[e]), 'average': round(average[e]),
                     'side': 'more' if diff >= FEELING_EVEN else 'less' if diff <= -FEELING_EVEN else 'even'})
    rows.sort(key=lambda r: -r['diff'])
    top = max(abs(mine[e] - average[e]) for e in EMOTIONS) or 1
    for r in rows:  # within FEELING_EVEN of the average the bar is still drawn, in grey, on the side it leans
        r['bar'] = round(100 * abs(r['diff']) / top) if r['diff'] else 0
        r['lean'] = 'right' if r['diff'] > 0 else 'left'
    more = next((r for r in rows if r['side'] == 'more'), None)
    less = next((r for r in reversed(rows) if r['side'] == 'less'), None)
    return {'rows': rows, 'more': more, 'less': less, 'even': FEELING_EVEN}


def front_page(mine: pd.DataFrame, live: pd.DataFrame, story_of_url: dict) -> dict:
    """Its front page now in two: headlines in one of our stories, by the story's rank (our stories ranked by how
    many outlets run them now), each with how many outlets run it and their lean mix; and headlines in none of them,
    in its own front page's order"""
    from app.site import boards
    ours = live[live['url'].isin(story_of_url)].copy()
    ours['anchor'] = ours['url'].map(lambda u: story_of_url[u][0])
    size = ours.groupby('anchor')['agency'].nunique()
    rated = ours[ours['rated'].astype(bool)]
    left = rated[rated['bias'] < 0].groupby('anchor')['agency'].nunique()
    right = rated[rated['bias'] > 0].groupby('anchor')['agency'].nunique()
    rank = {a: i + 1 for i, a in enumerate(sorted(size.index, key=lambda a: (-size[a], str(a))))}
    top = int(size.max()) if len(size) else 1
    pack, only = [], []
    for place, r in enumerate(mine.sort_values('position').itertuples(), start=1):
        story = story_of_url.get(r.url)
        if story:
            a = story[0]
            lf, rt = int(left.get(a, 0)), int(right.get(a, 0))
            pack.append({'title': r.title, 'url': r.url, 'anchor': a, 'story': story[1], 'rank': rank.get(a),
                         'outlets': int(size.get(a, 1)), 'bar': boards.bar(int(size.get(a, 1)), top),
                         'split': round(100 * lf / (lf + rt)) if lf + rt else None, 'left': lf, 'right': rt})
        else:
            only.append({'title': r.title, 'url': r.url, 'place': place})
    pack.sort(key=lambda h: (h['rank'] or 10 ** 6, h['title']))
    return {'pack': pack, 'only': only, 'stories': len(size), 'shown': NOW_SHOWN}


def versus(value, median, top, unit: str) -> dict | None:
    """A measure against the median outlet's: its bar and the median's tick (on a scale to the biggest outlet's),
    and a few words on how far apart they are"""
    if value is None or median is None:
        return None
    if not median:
        words = 'the median outlet has none' if value else 'like the median outlet'
    elif abs(value - median) <= 0.1 * median:
        words = 'about the median'
    elif value > median:
        words = f'{value / median:.1f}× the median'.replace('.0×', '×')
    else:
        words = f'{100 * value / median:.0f}% of the median' if value else 'none'
    top = max(top or 0, value, median) or 1
    return {'value': value, 'median': median, 'bar': max(2, round(100 * value / top)) if value else 0,
            'tick': round(100 * median / top), 'words': words, 'unit': unit}


def measures(o: dict, medians: dict, tops: dict) -> list[dict]:
    """The outlet page's measures, each against the median outlet's"""
    rows = []
    for key, emoji, name, value, unit in (
            ('stirs', '🌶️', 'Worded to stir', o['shares']['stirs'], '% of its headlines'),
            ('grim', '⛈️', 'Bad news', o['shares']['grim'], '% of its headlines'),
            ('edits', '✏️', 'Rewrites', o['edits'], ' per 100 headlines'),
            ('wire', '📡', 'Wire copy', None if o['is_wire'] else o['wire'], '% AP or Reuters headlines')):
        v = versus(value, medians.get(key), tops.get(key), unit)
        if v:
            rows.append({**v, 'key': key, 'emoji': emoji, 'name': name})
    return rows


class OutletPages:
    def __init__(self, dh: DataHandler, outlets: list[dict], window_days: int, medians: dict | None = None,
                 tops: dict | None = None):
        self.dh = dh
        self.outlets = outlets
        self.window_days = window_days
        self.medians = medians or {}
        self.tops = tops or {}
        self.template = TemplateHandler('outlet.html')

    def generate(self):
        live = self.dh.main_headline_df
        story_of_url = SHARED.get('story_of_url', {})
        edits, _ = find_edits()
        try:
            profile = outlet_profile.profiles()  # its fingerprint (Oct 28), kept for the day
        except Exception:  # noqa: BLE001 - the pages without fingerprints beat no pages
            logger.exception("Outlet profiles failed; outlet pages go without fingerprints this build")
            profile = {}
        has_feelings = 'emotion_ranks' in live
        average = average_feelings(live) if has_feelings else {}
        for o in self.outlets:
            mine = live[live['agency'] == o['name']]
            rewrites = []
            if not edits.empty:
                for _, e in edits[edits['agency'] == o['name']].head(MAX_REWRITES).iterrows():
                    # without the model's note on what changed (not credible: see page_edits)
                    rewrites.append({'before': e['before_html'], 'after': e['after_html']})
            read = int(mine['emotion_ranks'].notna().sum()) if has_feelings else 0
            self.template.write({'title': o['name'], 'o': o, 'now': front_page(mine, live, story_of_url),
                                 'rewrites': rewrites, 'window_days': self.window_days,
                                 'fp': fingerprint(profile, o['name']), 'profiled': bool(profile.get('outlets')),
                                 'feelings': feeling_strip(feeling_shares(mine['emotion_ranks']), average)
                                 if has_feelings else None, 'feelings_read': read,
                                 'measures': measures(o, self.medians, self.tops) if 'shares' in o else [],
                                 'medians': self.medians},
                                os.path.join(Config.build, f"outlet-{o['slug']}.html"))
        logger.info("Outlet pages: %d", len(self.outlets))
