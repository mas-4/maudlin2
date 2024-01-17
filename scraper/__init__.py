import nltk

try:
    nltk.data.find('tokenizers/punkt.zip')
except LookupError:
    nltk.download('vader_lexicon')