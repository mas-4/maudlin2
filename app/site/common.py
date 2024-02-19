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
    "Oct", "Nov", "Dec", "company", "companies", "business", "’", "'", '"', "go",
    "new", "January", "February", "March", "April", "June", "July", "August", "September", "October", "November",
    "December", "time", "year", "week", "month", "years", "people", "life", "day", "thing", "something", "number",
    "Subscribe", "EST", "READ", "News", "New", "York", "Images"
])
# strip stray letters
STOPWORDS.extend([l for l in string.ascii_lowercase + string.ascii_uppercase])
STOPWORDS.extend([c for c in string.punctuation])
STOPWORDS = [word.lower() for word in STOPWORDS]


def filter_words(headlines: list[str], parts_of_speech: Optional[list[str]] = None) -> list[str]:
    if parts_of_speech is None:
        parts_of_speech = POS
    words: list[tuple[str, str]] = list(filter(lambda word: word[1] in parts_of_speech,
                                               nltk.pos_tag(nltk.word_tokenize(' '.join(headlines)))))
    filtered_words = [word[0] for word in words if word[0].lower() not in STOPWORDS and len(word[0]) > 2]
    return filtered_words


def generate_wordcloud(headlines: list[Headline], path: str):
    wc: WordCloud = WordCloud(background_color="white", max_words=100, width=800, height=400, stopwords=STOPWORDS)
    logger.debug("Generating wordcloud for %s articles", len(headlines))
    frequencies = get_frequencies(headlines)
    wc.generate_from_frequencies(frequencies)
    logger.debug("Saving wordcloud to %s", path)
    wc.to_file(path)

def get_frequencies(headlines: list[Headline]):
    headlines: list[str] = [headline.title for headline in headlines]
    return nltk.FreqDist(filter_words(headlines))
