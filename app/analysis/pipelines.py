import string

import nltk
import regex as re

from app.analysis import textnorm

STOPWORDS = set(nltk.corpus.stopwords.words('english'))
include_stopwords = {'dear', 'New York Times', 'Getty Images',
                     'AP', "'s", "’", "``", "''", "—", "–", "“", "”", "‘", "the", "of", "in", "ago"}
include_stopwords.update(string.punctuation)
exclude_stopwords = {'not', 'no', 'nor', 'none', 'neither', 'never', 'nothing',
                     'nowhere', 'nobody', 'noone', 'nought', 'nay', 'nix', 'nil', 'negatory', 'nope', 'nah',
                     'naw', 'no way', 'ago', 'said', 'go'}
STOPWORDS |= include_stopwords
STOPWORDS -= exclude_stopwords
STOPWORDS = [word.lower() for word in STOPWORDS]

POS = ['NN', 'NNS', 'NNP', 'NNPS']

CONTRACTION_MAP: dict[str, str] = {
    "aren't": "are not",
    "can't": "cannot",
    "couldn't": "could not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "hadn't": "had not",
    "hasn't": "has not",
    "haven't": "have not",
    "he'd": "he would",
    "he'll": "he will",
    "he's": "he is",
    "I'd": "I would",
    "I'll": "I will",
    "I'm": "I am",
    "I've": "I have",
    "isn't": "is not",
    "it's": "it is",
    "she'd": "she would",
    "she'll": "she will",
    "she's": "she is",
    "shouldn't": "should not",
}

CONTRACTION_EXPANSION_FROM_TOKEN: dict[str, str] = {
    're': 'are',
    's': 'is',
    't': 'not',
    'd': 'would',
    'll': 'will'
}


def prepare(text, pipeline=None):
    if pipeline is None:
        pipeline = default_pipeline
    for transform in pipeline:
        text = transform(text)
    return text


class Pipelines:
    @staticmethod
    def remove_stop(tokens: list[str], stopwords=None):
        if stopwords is None:
            stopwords = STOPWORDS
        return [tok for tok in tokens if tok.lower() not in stopwords]

    @staticmethod
    def pos_filter(text, pos=POS):  # noqa
        return [word for word, tag in nltk.pos_tag(text) if tag in pos]

    @staticmethod
    def expand_contractions(tokens: list[str]):
        return [CONTRACTION_MAP.get(tok, tok) for tok in tokens]

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return re.findall(r'[\w-]*\p{L}[\w-]*', text)

    @staticmethod
    def lemmatize(tokens: list[str]):
        """Plural nouns to their singular, but never to a 'word' WordNet doesn't know: its -ies rule made "dies" into
        "dy" (which WordNet knows, as dysprosium), and the word cloud showed "dy" for every death story of the day
        (Oct 6). So a lemma of two letters or fewer is never taken, and words in -ics (physics, politics) keep their form."""
        from nltk.corpus import wordnet
        lemmatizer = nltk.WordNetLemmatizer()
        out = []
        for tok in tokens:
            lemma = lemmatizer.lemmatize(tok)
            keep = lemma == tok or len(lemma) <= 2 or tok.lower().endswith('ics') or not wordnet.synsets(lemma)
            out.append(tok if keep else lemma)
        return out

    @staticmethod
    def ngrams(tokens, n=2, sep=' ', stopwords=None):
        if stopwords is None:
            stopwords = set()
        return [sep.join(ngram) for ngram in zip(*[tokens[i:] for i in range(n)]) if
                not any(tok in stopwords for tok in ngram)]

    @staticmethod
    def split_camelcase(text: str):  # invalidated function
        return text

    @staticmethod
    def decontract(tokens: list[str]):
        return [CONTRACTION_EXPANSION_FROM_TOKEN.get(tok, tok) for tok in tokens]


# The text clean-up every pipeline starts with (headline tables, topics, the word cloud): hyphens, quotes, unicode,
# spacing, accents, brackets and punctuation
NORMALIZE = [
    textnorm.hyphenated_words,
    textnorm.quotation_marks,
    textnorm.normalize_unicode,
    textnorm.whitespace,
    textnorm.accents,
    textnorm.brackets,
    textnorm.punctuation,
]

default_pipeline = [
    *NORMALIZE,
    str.lower,
    Pipelines.tokenize,
    Pipelines.decontract,
]
