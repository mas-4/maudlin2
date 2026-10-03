import nltk

nltks = ['vader_lexicon', 'punkt_tab', 'averaged_perceptron_tagger_eng', 'wordnet', 'stopwords']

for nlt in nltks:
    nltk.download(nlt, quiet=True)
