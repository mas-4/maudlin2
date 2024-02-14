import string
from typing import Optional

import nltk
from wordcloud import STOPWORDS
from wordcloud import WordCloud

from app.logger import get_logger
from app.models import Headline

logger = get_logger(__name__)

POS = ['NN', 'NNS', 'NNP', 'NNPS']

STOPWORDS = list(STOPWORDS)
# clean some default words
STOPWORDS.extend([
    'say', 'said', 'says', "n't", 'Mr', 'Ms', 'Mrs', 'time', 'year', 'week', 'month', "years",
    "people", "life", "day", "thing", "something", "number", "system", "video", "months", "group",
    "state", "country", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "home", "effort", "product", "part", "cup", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
    "Oct", "Nov", "Dec", "company", "companies", "business"
])
# strip stray letters
STOPWORDS.extend([l for l in string.ascii_lowercase + string.ascii_uppercase])


def filter_words(text: str, parts_of_speech: Optional[list[str]] = None):
    if parts_of_speech is None:
        parts_of_speech = POS
    words = filter(lambda word: word[1] in parts_of_speech, nltk.pos_tag(nltk.word_tokenize(text)))
    return ' '.join([word[0] for word in words])


def generate_wordcloud(headlines: list[Headline], path: str):
    wc = WordCloud(background_color="white", max_words=100, width=800, height=400, stopwords=STOPWORDS)
    logger.debug("Generating wordcloud for %s articles", len(headlines))
    text = ' '.join([headline.title for headline in headlines])
    logger.debug("There are %d words", text.count(' '))
    if not text.strip():
        logger.warning("No text to generate wordcloud")
        return
    wc.generate(filter_words(text, ['NN', 'NNS', 'NNP', 'NNPS']))
    logger.debug("Saving wordcloud to %s", path)
    wc.to_file(path)
