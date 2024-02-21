from app.models import Headline
from nltk.sentiment import SentimentIntensityAnalyzer


def vader_lexicon(headline: Headline):
    results = {f'vader_{k}': v for k, v in SentimentIntensityAnalyzer().polarity_scores(headline.title).items()}
    for k, v in results.items():
        setattr(headline, k, v)


def apply(headline: Headline):
    vader_lexicon(headline)