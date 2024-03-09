from afinn import Afinn
from nltk.sentiment import SentimentIntensityAnalyzer

from app.models import Headline
from app.utils.constants import Constants
from app.analysis.topics import score_tokens, prepare_for_topic, load_and_update_topics

SID = SentimentIntensityAnalyzer()
AFINN = Afinn()

topics = None

def apply_topic_scoring(headline: Headline):
    global topics
    if topics is None:
        topics = load_and_update_topics()
    if headline.article.topic_id is not None:
        return
    tokens = prepare_for_topic(headline.title)
    scores = {topic.id: score_tokens(tokens, topic) for topic in topics}
    max_score = max(scores.values())
    max_topic_id = max(scores, key=scores.get)
    if max_score > Constants.Thresholds.topic_score:
        headline.article.topic_id = max_topic_id


def apply_vader(headline: Headline):
    results = {f'vader_{k}': v for k, v in SID.polarity_scores(headline.title).items()}
    for k, v in results.items():
        setattr(headline, k, v)


def apply_afinn(headline: Headline):
    headline.afinn = AFINN.score(headline.title) / len(headline.title.split())


def apply(headline: Headline):
    apply_vader(headline)
    apply_afinn(headline)
    apply_topic_scoring(headline)
