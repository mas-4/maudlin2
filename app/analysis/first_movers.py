"""First movers (#116): how often each outlet is on a story from our first sighting of it, and how far behind it trails
when it isn't. Scrapes are hourly, so "first" means in the same hourly read as the story's first headline, not first
by the minute. Stories already running when the database started are left out (their first sighting is ours, not
the news's)."""
from datetime import timedelta as td

import pandas as pd

from app.models import Session, StoryHeadline, Headline, Article, Agency
from app.utils import get_logger

AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire'}  # as in page_headlines

logger = get_logger(__name__)

SAME_READ = td(minutes=45)  # within one hourly read of the story's first headline
WARM_UP = td(hours=2)  # stories first seen this soon after the database started are skipped
MIN_STORIES = 5


def first_movers() -> pd.DataFrame:
    """Per outlet on MIN_STORIES or more stories: stories, times first, share first, median hours behind when not."""
    with Session() as s:
        rows = s.query(StoryHeadline.story_id, Agency.name, Headline.first_accessed) \
            .join(Headline, Headline.id == StoryHeadline.headline_id) \
            .join(Article, Article.id == Headline.article_id).join(Agency, Agency.id == Article.agency_id).all()
        start = s.query(Headline.first_accessed).order_by(Headline.first_accessed).first()
    df = pd.DataFrame(rows, columns=['story', 'agency', 'seen'])
    if df.empty or start is None:
        return pd.DataFrame(columns=['stories', 'first', 'share', 'lag_hours'])
    df = df[~df['agency'].isin(AGGREGATORS)]  # they link to others' stories (#151)
    df = df.groupby(['story', 'agency'], as_index=False)['seen'].min()  # an outlet's first headline on the story
    broke = df.groupby('story')['seen'].transform('min')
    df = df[broke - start[0] >= WARM_UP].copy()
    df['lag'] = (df['seen'] - broke[df.index]).dt.total_seconds() / 3600
    df['first'] = df['lag'] <= SAME_READ.total_seconds() / 3600
    out = df.groupby('agency').agg(stories=('story', 'nunique'), first=('first', 'sum'))
    out['lag_hours'] = df[~df['first']].groupby('agency')['lag'].median()
    out = out[out['stories'] >= MIN_STORIES]
    out['share'] = out['first'] / out['stories']
    logger.info("First movers: %d outlets; most often first: %s", len(out),
                ', '.join(f'{a} {s:.0%}' for a, s in out['share'].sort_values(ascending=False).head(5).items()))
    return out.sort_values('share', ascending=False)
