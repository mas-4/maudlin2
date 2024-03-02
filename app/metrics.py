from afinn import Afinn
from nltk.sentiment import SentimentIntensityAnalyzer

from app.models import Headline

SID = SentimentIntensityAnalyzer()
AFINN = Afinn()


def vader_lexicon(headline: Headline):
    results = {f'vader_{k}': v for k, v in SID.polarity_scores(headline.title).items()}
    for k, v in results.items():
        setattr(headline, k, v)


def apply_afinn(headline: Headline):
    headline.afinn = AFINN.score(headline.title)


def apply(headline: Headline):
    vader_lexicon(headline)
    apply_afinn(headline)
