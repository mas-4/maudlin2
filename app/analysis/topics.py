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


def score_headline(headline: str, topic: Topic):
    h = prepare(headline, pipeline)
    ngrams = Pipelines.ngrams(h, n=2, stopwords=STOPWORDS)
    return sum(1 for word in h + ngrams if word in topic.keywords) / (len(h) + 1)


def analyze_topic(topic: Topic):
    with Session() as s:
        headlines = s.query(Headline).join(Headline.article).filter(
            or_(*[Headline.title.like(f"%{word}%") for word in topic.essential]),
            Article.topic_id == None
        ).all()
        df = pd.DataFrame([(h.article_id, h.title) for h in headlines], columns=['id', 'title'])
        df['score'] = df['title'].apply(partial(score_headline, topic=topic))
        ids = list(set(df[df['score'] > Constants.Thresholds.topic_score]['id'].tolist()))
        # Update all articles with these headline_ids to have the topic_id
        s.query(Article).filter(Article.id.in_(ids)).update({Article.topic_id: topic.id}, synchronize_session=False)

if __name__ == "__main__":
    topics = load_and_update_topics()
    print(topics)