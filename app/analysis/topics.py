from functools import partial
from typing import Optional

import nltk
import pandas as pd
import yaml
from sqlalchemy import or_

from app.analysis.pipelines import Pipelines, prepare, trem, tnorm
from app.models import Session, Topic, Headline, Article, SqlLock
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)

STOPWORDS = set(nltk.corpus.stopwords.words('english'))
STOPWORDS = [word.lower() for word in STOPWORDS]

pipeline = [
    str.lower,
    tnorm.hyphenated_words,
    tnorm.quotation_marks,
    tnorm.unicode,
    trem.accents,
    trem.brackets,
    trem.punctuation,
    Pipelines.tokenize,
    Pipelines.expand_contractions,
    Pipelines.lemmatize,
    partial(Pipelines.remove_stop, stopwords=STOPWORDS)
]


def load_and_update_topics(s: Optional[Session] = None):
    with (open(Constants.Paths.TOPICS_FILE, 'rt') as f):
        topic_dict: dict = yaml.safe_load(f)
    commit = False
    if s is None:
        s = Session()
        commit = True
        SqlLock.acquire()
    for top_d in topic_dict:
        topic: Topic = s.query(Topic).filter(Topic.name == top_d['name']).first()
        if topic is None:
            logger.info("Adding topic %s", top_d['name'])
            topic = Topic(name=top_d['name'])
            s.add(topic)
        topic.keywords = top_d['keywords']
        topic.essential = top_d['essential']
    s.commit()
    topics = s.query(Topic).all()
    for topic in topics:
        s.expunge(topic)
    if commit:
        s.close()
        SqlLock.release()
    return topics


def prepare_for_topic(headline: str):
    return prepare(headline, pipeline)


def score_tokens(tokens: list[str], topic: Topic):
    ngrams = Pipelines.ngrams(tokens, n=2, stopwords=STOPWORDS)
    if not any(k in tokens for k in topic.essential):
        return 0
    return sum(1 for word in tokens + ngrams if word in topic.keywords) / (len(tokens) + 1)


def analyze_all_topics(reset=False):
    with Session() as s:
        if reset:
            logger.info("Resetting all topic assignments")
            s.query(Article).update({Article.topic_id: None, Article.topic_score: None})
            s.commit()
            logger.info("Deleting all topics")
            s.query(Topic).delete()
            s.commit()
        topics = load_and_update_topics()
        # make a flattened list of all essentials
        essentials = [word for topic in topics for word in topic.essential]
        headlines = s.query(Headline).join(Headline.article).filter(
            or_(*[Headline.title.like(f"%{word}%") for word in essentials]),
            Article.topic_id == None
        ).all()
        logger.info("Analyzing %d headlines for %d topics", len(headlines), len(topics))

        df = pd.DataFrame([(h.article_id, h.title) for h in headlines], columns=['id', 'title'])
        df['prepared'] = df['title'].apply(prepare_for_topic)
        for topic in topics:
            df[topic.id] = df['prepared'].apply(partial(score_tokens, topic=topic))

        threshold = Constants.Thresholds.topic_score
        topic_ids = [topic.id for topic in topics]

        df['max_score'] = df[topic_ids].max(axis=1)
        df['max_topic_id'] = df[topic_ids].idxmax(axis=1)

        filtered = df[df['max_score'] > threshold]

        logger.info("Found %d articles for %d topics", len(filtered), len(topic_ids))
        logger.info("Updating database with topics")
        topic_updates = filtered[['id', 'max_topic_id', 'max_score']].to_dict(orient='records')

        for update in topic_updates:
            s.query(Article).filter(Article.id == update['id']).update(
                {Article.topic_id: update['max_topic_id'], Article.topic_score: update['max_score']},
                synchronize_session=False)

        s.commit()


if __name__ == "__main__":
    analyze_all_topics(True)
