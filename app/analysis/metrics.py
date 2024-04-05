from typing import Optional

import pandas as pd
from afinn import Afinn
from nltk.sentiment import SentimentIntensityAnalyzer
from sqlalchemy import or_

from app.analysis.topics import score_tokens, prepare_for_topic, load_and_update_topics
from app.models import Headline, Topic, Session, SqlLock
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


SID = SentimentIntensityAnalyzer()
AFINN = Afinn()

topics: Optional[list[Topic]] = None


def apply_topic_scoring(headline: Headline):
    global topics
    if headline.article.topic_id is not None:
        return
    tokens = prepare_for_topic(headline.title)
    scores = {topic.id: score_tokens(tokens, topic) for topic in topics}
    max_score = max(scores.values())
    max_topic_id = max(scores, key=scores.get)
    if max_score > Constants.Thresholds.topic_score:
        headline.article.topic_id = max_topic_id
        headline.article.topic_score = max_score


def apply_vader(headline: Headline):
    results = {f'vader_{k}': v for k, v in SID.polarity_scores(headline.title).items()}
    for k, v in results.items():
        setattr(headline, k, v)


def apply_afinn(headline: Headline):
    headline.afinn = AFINN.score(headline.title) / len(headline.title.split())


def apply(headline: Headline):
    global topics
    if topics is None:
        topics = load_and_update_topics()
    with Session() as s, SqlLock:
        s.add(headline)
        apply_vader(headline)
        apply_afinn(headline)
        apply_topic_scoring(headline)
        s.commit()
        pass


def reapply_sent():
    with Session() as s, SqlLock:
        headlines = s.query(Headline.id, Headline.title).all()
        count = len(headlines)
        logger.debug('Reapplying sentiment to %i headlines', count)
        df = pd.DataFrame(headlines, columns=['id', 'title'])
        df['afinn'] = df['title'].apply(lambda x: AFINN.score(x) / len(x.split()))
        df['vader'] = df['title'].apply(lambda x: SID.polarity_scores(x))
        logger.debug("Sentiment calculated, now updating database.")
        for i, row in enumerate(df.itertuples()):
            s.query(Headline).update(
                {
                    Headline.afinn: row.afinn,
                    Headline.vader_neg: row.vader['neg'],
                    Headline.vader_neu: row.vader['neu'],
                    Headline.vader_pos: row.vader['pos'],
                    Headline.vader_compound: row.vader['compound']
                },
                synchronize_session=False
            )
            if i % 1000 == 0:
                logger.debug('Updating %i of %i', i, count)
        logger.debug('Committing changes to database.')
        s.commit()
        logger.debug('Sentiment reapplication complete.')

if __name__ == '__main__':
    reapply_sent()