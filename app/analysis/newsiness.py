from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


def get_newsiness(headlines):
    tfidf = TfidfVectorizer(stop_words='english')
    cosim = cosine_similarity(tfidf.fit_transform(headlines))
    # Zero out the diagonal
    np.fill_diagonal(cosim, 0)
    # Zero out all values less than 0.5
    cosim[cosim < 0.5] = 0
    # Take the # of non-zero values divided by the total shape of the matrix
    return (np.count_nonzero(cosim) / cosim.size) * 10_000
