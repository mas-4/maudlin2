from collections import deque

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# Function to form clusters
def form_clusters(cosine_sim, min_samples=10, threshold=0.5):
    print("Clustering with python.")
    # zero out diagonal
    np.fill_diagonal(cosine_sim, 0)
    # drop everything less than threshold
    cosine_sim[cosine_sim < threshold] = 0
    clusters = []
    while np.any(cosine_sim):
        # Start with the first available row
        first_index = np.where(np.any(cosine_sim, axis=1))[0][0]
        # Get all indices where similarity >= threshold
        involved_indices = np.where(cosine_sim[first_index] >= threshold)[0]
        # Add all connected components
        queue = deque(involved_indices)
        cluster = set(queue)
        while queue:
            current = queue.popleft()
            connected_indices = np.where(cosine_sim[current] >= threshold)[0]
            new_indices = set(connected_indices) - cluster
            queue.extend(new_indices)
            cluster.update(new_indices)
        # Mark these rows and columns as processed
        for idx in cluster:
            cosine_sim[idx, :] = 0
            cosine_sim[:, idx] = 0
        # Store the cluster
        if len(cluster) >= min_samples:
            clusters.append(cluster)
            print(f"Cluster len: {len(cluster)}, clusters formed: {len(clusters)}")
    return clusters


try:  # If the C extension is available, use it
    from app.analysis.maudlinlib import form_clusters as _c_form_clusters

    def form_clusters(cosine_sim, min_samples=10, threshold=0.5):
        # The C code reads the buffer as contiguous doubles with no checks, so anything else corrupts memory
        return _c_form_clusters(np.ascontiguousarray(cosine_sim, dtype=np.float64), min_samples, threshold)
except ImportError:
    pass


def prepare_cosine(data):
    # TF-IDF Vectorizer
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(data)
    # Cosine Similarity
    cosine_sim = cosine_similarity(tfidf_matrix)
    return cosine_sim


EMBEDDING_MODEL = 'minishlab/potion-base-8M'
_embedder = None


def embed(texts: list[str]) -> np.ndarray:
    """Static sentence embeddings (model2vec). Matches headlines by meaning rather than shared words, so
    differently worded coverage of one story still clusters. Numpy only, a few ms per thousand headlines."""
    global _embedder
    if _embedder is None:
        from model2vec import StaticModel
        _embedder = StaticModel.from_pretrained(EMBEDDING_MODEL)
    return _embedder.encode(list(texts))


def prepare_embedding_cosine(texts):
    return cosine_similarity(embed(texts)).astype(np.float64)


def label_clusters(data, clusters):
    cluster_labels = [-1] * len(data)
    for cluster_id, cluster_indices in enumerate(clusters):
        for idx in cluster_indices:
            cluster_labels[idx] = cluster_id
    data['cluster'] = cluster_labels
    return data
