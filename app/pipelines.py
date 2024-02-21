import regex as re
from textacy.preprocessing import normalize as tnorm, remove as trem, replace as trep
import string
import nltk
from functools import partial

nltk.download('stopwords')
STOPWORDS = set(nltk.corpus.stopwords.words('english'))
include_stopwords = {'dear', 'New York Times', 'Getty Images',
                     'AP', "'s", "’", "``", "''", "—", "–", "“", "”", "‘", "’",
                     "the", "of", "in"}
include_stopwords.update(string.punctuation)
exclude_stopwords = {'not', 'no', 'nor', 'none', 'neither', 'never', 'nothing',
                     'nowhere', 'nobody', 'noone', 'nought', 'nay', 'nix', 'nil', 'negatory', 'nay', 'nope', 'nah',
                     'naw', 'no way', 'no way', 'ago', 'said', 'go'}
STOPWORDS |= include_stopwords
STOPWORDS -= exclude_stopwords

def remove_stop(tokens: list[str], stopwords=None):
    if stopwords is None:
        stopwords = STOPWORDS
    return [tok for tok in tokens if tok not in stopwords]


POS = ['NN', 'NNS', 'NNP', 'NNPS']

def pos_filter(text, pos=POS): # noqa
    return [word for word, tag in nltk.pos_tag(text) if tag in pos]

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

def tokenize(text: str) -> list[str]:
    return re.findall(r'[\w-]*\p{L}[\w-]*', text)

def decontract(tokens: list[str]):
    return [CONTRACTION_MAP.get(tok, tok) for tok in tokens]

def lemmatize(tokens: list[str]):
    lemmatizer = nltk.WordNetLemmatizer()
    return [lemmatizer.lemmatize(tok) for tok in tokens]

def ngrams(tokens, n=2, sep=' ', stopwords=None):
    if stopwords is None:
        stopwords = set()
    return [sep.join(ngram) for ngram in zip(*[tokens[i:] for i in range(n)]) if not any(tok in stopwords for tok in ngram)]

def split_camelcase(tokens: str):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', tokens)


default_pipeline = [
    split_camelcase,
    tnorm.hyphenated_words,
    tnorm.quotation_marks,
    tnorm.unicode,
    tnorm.whitespace,
    trem.accents,
    trem.brackets,
    trem.punctuation,
    str.lower,
    tokenize,
    decontract,
    partial(remove_stop, stopwords=string.ascii_lowercase)
]


def prepare(text, pipeline=None):
    if pipeline is None:
        pipeline = default_pipeline
    for transform in pipeline:
        text = transform(text)
    return text