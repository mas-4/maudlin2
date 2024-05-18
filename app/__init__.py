import nltk

nltks = ['vader_lexicon', 'punkt', 'averaged_perceptron_tagger', 'wordnet', 'stopwords']

for nlt in nltks:
    nltk.download(nlt, quiet=True)
