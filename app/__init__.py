import nltk

# NLTK's data, fetched only when it's missing (Oct 22: every process that imported the app asked GitHub for NLTK's index
# five times at startup, with no time limit; one such request hung the desktop widget's run from Oct 20, and the widget
# froze on that night's dimmed card for two days). Once installed, nothing goes over the network.
nltks = {'vader_lexicon': 'sentiment/vader_lexicon.zip', 'punkt_tab': 'tokenizers/punkt_tab',
         'averaged_perceptron_tagger_eng': 'taggers/averaged_perceptron_tagger_eng', 'wordnet': 'corpora/wordnet.zip',
         'stopwords': 'corpora/stopwords'}

for nlt, path in nltks.items():
    try:
        nltk.data.find(path)
    except LookupError:
        nltk.download(nlt, quiet=True)
