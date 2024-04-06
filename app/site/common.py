import string
from functools import partial
from typing import Callable, Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from wordcloud import WordCloud

from app.analysis.pipelines import Pipelines, trem, tnorm, STOPWORDS, prepare
from app.utils.logger import get_logger

logger = get_logger(__name__)

POS = ['NN', 'NNS', 'NNP', 'NNPS']

STOPWORDS = list(STOPWORDS)
# clean some default words
STOPWORDS.extend([
    'say', 'said', 'says', "n't", 'Mr', 'Ms', 'Mrs', 'time', 'year', 'week', 'month', "years",
    "life", "day", "thing", "something", "number", "system", "video", "months", "group",
    "home", "effort", "product", "part", "cup", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
    "Oct", "Nov", "Dec", "company", "companies", "business", "’", "'", '"', "go",
    "new", "January", "February", "March", "April", "June", "July", "August", "September", "October", "November",
    "December", "time", "year", "week", "month", "years", "people", "life", "day", "thing", "something", "number",
    "Subscribe", "EST", "READ", "News", "New", "York", "Images", "Politics", "newsletter", "ago", "live", "updates",
    "exclusive",
    "producers", "hour"
])
# strip stray letters
STOPWORDS.extend(list(string.ascii_lowercase))
STOPWORDS.extend(list(string.ascii_uppercase))
STOPWORDS.extend(list(string.punctuation))

PIPELINE = [
    tnorm.hyphenated_words,
    tnorm.quotation_marks,
    tnorm.unicode,
    tnorm.whitespace,
    trem.accents,
    trem.brackets,
    trem.punctuation,
    Pipelines.tokenize,
    Pipelines.expand_contractions,
    partial(Pipelines.remove_stop, stopwords=STOPWORDS),
    Pipelines.lemmatize,
    Pipelines.pos_filter,
    lambda x: ' '.join(x)
]


def generate_wordcloud(headlines: list[str], path: str, pipeline: Optional[list[Callable]] = None):
    if pipeline is None:
        pipeline = PIPELINE
    logger.info("Generating wordcloud for %s articles...", len(headlines))
    text = pd.DataFrame(headlines, columns=['title'])
    logger.info("Cleaning text...")
    text['cleaned'] = text['title'].apply(prepare, pipeline=pipeline)
    logger.info("Vectorizing text...")
    vec = CountVectorizer(ngram_range=(1, 3), lowercase=False, max_features=1000)
    mat = vec.fit_transform(text['cleaned'])
    logger.info("Creating dataframe from vector...")
    df = pd.DataFrame(mat.todense().tolist(), columns=(vec.get_feature_names_out()))
    wc: WordCloud = WordCloud(background_color="white", max_words=100, width=800, height=400)
    logger.info("Generating frequency dictionary...")
    freq_dict = df.T.sum(axis=1)
    logger.info("Generating wordcloud for real this time...")
    wc.generate_from_frequencies(freq_dict)
    logger.info("Saving wordcloud to %s", path)
    wc.to_file(path)


def calculate_xkeyscore(df):
    n_features = 1000
    df['prepared'] = df['title'].apply(lambda x: prepare(x, pipeline=PIPELINE))
    dense = CountVectorizer(max_features=n_features, ngram_range=(1, 3), lowercase=False).fit_transform(
        df['prepared']
    ).todense()
    top_indices = np.argsort(np.sum(dense, axis=0).A1)[-n_features:]
    df['score'] = [sum(doc[0, i] for i in top_indices if doc[0, i] > 0) for doc in dense]
    df = df.sort_values(by='score', ascending=False)
    df.drop('prepared', axis=1, inplace=True)
    return df
