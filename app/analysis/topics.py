from functools import partial

import nltk
import yaml
import pandas as pd
from sqlalchemy import or_

from app.analysis.pipelines import Pipelines, prepare, trem, tnorm
from app.models import Session, Topic, Headline, Article
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)

STOPWORDS = set(nltk.corpus.stopwords.words('english'))

pipeline = [
    Pipelines.split_camelcase,
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

def load_and_update_topics():
    with (open(Constants.Paths.TOPICS_FILE, 'rt') as f):
        topic_dict: dict = yaml.safe_load(f)
    with Session() as session:
        topics = []  # noqa
        for top_d in topic_dict:
            topic: Topic = session.query(Topic).filter(Topic.name == top_d['name']).first()
            if topic is None:
                logger.debug("Adding topic %s", top_d['name'])
                topic = Topic(name=top_d['name'])
                session.add(topic)
            topic.keywords = top_d['keywords']
            topic.essential = top_d['essential']
            topics.append(topic)
        session.commit()
        topics = session.query(Topic).all()
        for topic in topics:
            session.expunge(topic)
    return topics


def prepare_for_topic(headline: str):
    return prepare(headline, pipeline)


def score_tokens(tokens: list[str], topic: Topic):
    ngrams = Pipelines.ngrams(tokens, n=2, stopwords=STOPWORDS)
    return sum(1 for word in tokens + ngrams if word in topic.keywords) / (len(tokens) + 1)


def analyze_all_topics(reset=False):
    topics = load_and_update_topics()
    with Session() as s:
        if reset:
            logger.info("Resetting all topics")
            s.query(Article).update({Article.topic_id: None})
            s.commit()
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
        topic_updates = filtered[['id', 'max_topic_id']].set_index('id').to_dict()['max_topic_id']

        for article_id, topic_id in topic_updates.items():
            s.query(Article).filter(Article.id == article_id).update({Article.topic_id: topic_id}, synchronize_session=False)

        s.commit()


if __name__ == "__main__":
    analyze_all_topics(True)