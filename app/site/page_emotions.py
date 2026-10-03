"""The emotions page: what feelings the news is stirring, overall, by side, by outlet and by topic."""
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz

from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI, NEWS_THRESHOLD, emotion_weights
from app.models import Session, Headline, Article, Agency, Topic
from app.site.common import TemplateHandler
from app.site.data import DataHandler
from app.site.graphing import bias_colors, bias_ink
from app.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 7
MIN_OUTLET_HEADLINES = 30
MIN_TOPIC_HEADLINES = 20
EMOTION_COLUMNS = [e for e in EMOTIONS if e != 'neutral'] + ['neutral']
SIDES = [('Left-leaning', lambda b: b < 0), ('Center', lambda b: b == 0), ('Right-leaning', lambda b: b > 0)]


def load(days: int = WINDOW_DAYS) -> pd.DataFrame:
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    with Session() as s:
        rows = s.query(Headline.emotion_ranks, Agency.name, Agency._bias, Topic.name).join(  # noqa prot attr
            Headline.article).join(Article.agency).join(Article.topic, isouter=True).filter(
            Headline.first_accessed > since, Headline.emotion_ranks.isnot(None), Headline.news_score >= NEWS_THRESHOLD
        ).all()
    df = pd.DataFrame(rows, columns=['ranks', 'agency', 'bias', 'topic'])
    # Each headline's vote, split ranked-choice style across the feelings it names (3:2:1, normalized)
    weights = pd.DataFrame([emotion_weights(r) for r in df['ranks']], index=df.index).reindex(
        columns=EMOTION_COLUMNS, fill_value=0).fillna(0)
    return df.join(weights)


def shares(df: pd.DataFrame, by: str, minimum: int) -> list[dict]:
    """One row per group with each emotion's share of the feeling in its headlines (the average of their split
    votes), the dominant feeling first."""
    sizes = df.groupby(by).size()
    table = df.groupby(by)[EMOTION_COLUMNS].mean()[sizes >= minimum]
    rows = []
    for name, row in table.iterrows():
        felt = row.drop('neutral')
        rows.append({'name': name, 'headlines': int(sizes[name]),
                     'shares': {e: round(float(row[e]), 3) for e in EMOTION_COLUMNS},
                     'dominant': felt.idxmax(), 'dominant_share': float(felt.max())})
    return sorted(rows, key=lambda r: (EMOTION_COLUMNS.index(r['dominant']), -r['dominant_share']))


class EmotionsPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('emotions.html')
        self.context = {'title': 'Emotions', 'window_days': WINDOW_DAYS, 'emotions': EMOTION_COLUMNS,
                        'emoji': EMOTION_EMOJI, 'min_outlet_headlines': MIN_OUTLET_HEADLINES}

    def generate(self):
        logger.info("Generating emotions page...")
        df = load()
        if df.empty:
            self.context['available'] = False
            self.template.write(self.context)
            return
        overall = df[EMOTION_COLUMNS].mean()
        df['side'] = df['bias'].map(lambda b: next(name for name, test in SIDES if test(b)))
        bias_by_agency = df.drop_duplicates('agency').set_index('agency')['bias']
        outlets = shares(df, 'agency', MIN_OUTLET_HEADLINES)
        for row in outlets:
            b = int(bias_by_agency[row['name']])
            row['color'], row['ink'] = bias_colors[b + 3], bias_ink[b + 3]
        self.context.update({
            'available': True,
            'total': len(df),
            'overall': sorted(({'emotion': e, 'share': float(overall[e]), 'count': int((df[e] > 0).sum())}
                               for e in EMOTION_COLUMNS), key=lambda o: -o['share']),
            'sides': sorted(shares(df, 'side', 1), key=lambda r: [n for n, _ in SIDES].index(r['name'])),
            'outlets': outlets,
            'topics': shares(df.dropna(subset=['topic']), 'topic', MIN_TOPIC_HEADLINES),
            'max_share': max(max(r['shares'][e] for e in EMOTION_COLUMNS if e != 'neutral')
                             for r in outlets) if outlets else 1,
        })
        self.template.write(self.context)
        logger.info("...%d headlines, %d outlets", len(df), len(outlets))
