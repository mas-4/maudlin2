import string
from functools import partial

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from textacy.preprocessing import normalize as tnorm, remove as trem
from wordcloud import WordCloud

from app.models import Headline
from app.pipelines import (
    prepare,
    split_camelcase,
    tokenize,
    lemmatize,
    pos_filter,
    remove_stop,
    expand_contractions,
    STOPWORDS
)
from app.utils import get_logger

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
    "Subscribe", "EST", "READ", "News", "New", "York", "Images", "Politics", "newsletter", "ago"
])
# strip stray letters
STOPWORDS.extend(list(string.ascii_lowercase))
STOPWORDS.extend(list(string.ascii_uppercase))
STOPWORDS.extend(list(string.punctuation))

pipeline = [
    split_camelcase,
    tnorm.hyphenated_words,
    tnorm.quotation_marks,
    tnorm.unicode,
    tnorm.whitespace,
    trem.accents,
    trem.brackets,
    trem.punctuation,
    tokenize,
    expand_contractions,
    partial(remove_stop, stopwords=STOPWORDS),
    lemmatize,
    pos_filter,
    lambda x: ' '.join(x)
]


def generate_wordcloud(headlines: list[Headline], path: str):
    logger.debug("Generating wordcloud for %s articles", len(headlines))
    text = pd.DataFrame([headline.title for headline in headlines], columns=['title'])
    text['title'] = text['title'].apply(prepare, pipeline=pipeline)
    tfidf = TfidfVectorizer(ngram_range=(1, 3), lowercase=False)
    tfidf_matrix = tfidf.fit_transform(text['title'])
    df = pd.DataFrame(tfidf_matrix.todense().tolist(), columns=(tfidf.get_feature_names_out()))
    wc: WordCloud = WordCloud(background_color="white", max_words=100, width=800, height=400)
    wc.generate_from_frequencies(df.T.sum(axis=1))
    logger.debug("Saving wordcloud to %s", path)
    wc.to_file(path)
