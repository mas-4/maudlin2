"""Clustering helpers: form_clusters (both the C extension and the pure-Python fallback), the tf-idf cosine matrix,
cluster labels, and the embedding cosine with the model replaced by fixed vectors."""
import importlib.util
import sys

import numpy as np
import pandas as pd
import pytest

from app.analysis import clustering


def _python_module():
    """Load clustering.py again with the C extension hidden, so its pure-Python form_clusters stays in place."""
    saved = sys.modules.get('app.analysis.maudlinlib')
    sys.modules['app.analysis.maudlinlib'] = None  # makes the import raise ImportError
    try:
        spec = importlib.util.spec_from_file_location('_clustering_python', clustering.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            del sys.modules['app.analysis.maudlinlib']
        else:
            sys.modules['app.analysis.maudlinlib'] = saved
    return module


PYTHON = _python_module().form_clusters
IMPLEMENTATIONS = {'default': clustering.form_clusters, 'python': PYTHON}


def as_sets(clusters):
    return sorted(sorted(int(i) for i in c) for c in clusters)


TWO_PAIRS = np.array([[1, .9, .1, 0],
                      [.9, 1, .2, 0],
                      [.1, .2, 1, .8],
                      [0, 0, .8, 1]])
CHAIN = np.array([[1, .6, 0],
                  [.6, 1, .6],
                  [0, .6, 1]])


@pytest.fixture(params=list(IMPLEMENTATIONS))
def form_clusters(request):
    return IMPLEMENTATIONS[request.param]


HAS_C = importlib.util.find_spec('app.analysis.maudlinlib') is not None


@pytest.mark.skipif(not HAS_C, reason='C extension not built; default is already the Python fallback')
def test_python_fallback_is_really_python():
    assert PYTHON.__module__ == '_clustering_python'
    assert PYTHON is not clustering.form_clusters


def test_two_pairs(form_clusters):
    assert as_sets(form_clusters(TWO_PAIRS.copy(), 2, .5)) == [[0, 1], [2, 3]]


def test_min_samples_filters_small_clusters(form_clusters):
    assert form_clusters(TWO_PAIRS.copy(), 3, .5) == []


def test_transitive_chain_joins(form_clusters):
    # 0 and 2 aren't similar, but both are to 1, so they land in one cluster
    assert as_sets(form_clusters(CHAIN.copy(), 2, .5)) == [[0, 1, 2]]


def test_threshold_is_inclusive(form_clusters):
    m = np.array([[1, .5, 0], [.5, 1, 0], [0, 0, 1]])
    assert as_sets(form_clusters(m.copy(), 2, .5)) == [[0, 1]]
    assert form_clusters(m.copy(), 2, .51) == []


def test_higher_threshold_splits(form_clusters):
    assert as_sets(form_clusters(TWO_PAIRS.copy(), 2, .85)) == [[0, 1]]


def test_no_similarity_no_clusters(form_clusters):
    assert form_clusters(np.eye(4), 2, .5) == []


def test_float32_input_accepted(form_clusters):
    assert as_sets(form_clusters(TWO_PAIRS.astype(np.float32), 2, .5)) == [[0, 1], [2, 3]]


def test_large_block_matrix(form_clusters):
    rng = np.random.default_rng(0)
    n = 60
    m = rng.uniform(0, .3, (n, n))
    m = (m + m.T) / 2
    m[:20, :20] = .9  # one block of twenty
    m[30:45, 30:45] = .8  # one of fifteen
    clusters = as_sets(form_clusters(m.copy(), 10, .5))
    assert clusters == [list(range(20)), list(range(30, 45))]


def test_default_input_is_modified_in_place():
    # Documents behavior: the matrix is used as scratch space (callers pass a fresh one)
    m = TWO_PAIRS.copy()
    clustering.form_clusters(m, 2, .5)
    assert np.all(np.diag(m) == 0)


def test_implementations_agree_on_singletons():
    assert as_sets(clustering.form_clusters(np.eye(3), 1, .5)) == as_sets(PYTHON(np.eye(3), 1, .5))


# prepare_cosine()

def test_prepare_cosine():
    m = clustering.prepare_cosine(['the cat sat', 'the cat sat', 'dogs run fast'])
    assert m.shape == (3, 3)
    assert np.allclose(np.diag(m), 1)
    assert m[0, 1] == pytest.approx(1)
    assert m[0, 2] == pytest.approx(0)
    assert np.allclose(m, m.T)


def test_prepare_cosine_feeds_form_clusters():
    titles = ['Storm hits Florida coast', 'Florida coast hit by storm', 'Senate passes budget', 'Budget passes Senate']
    clusters = as_sets(clustering.form_clusters(clustering.prepare_cosine(titles), 2, .5))
    assert clusters == [[0, 1], [2, 3]]


# prepare_embedding_cosine() with a fake model

def test_prepare_embedding_cosine(monkeypatch):
    vectors = {'a': [1, 0], 'b': [2, 0], 'c': [0, 3]}
    monkeypatch.setattr(clustering, 'embed', lambda texts: np.array([vectors[t] for t in texts], dtype=np.float32))
    m = clustering.prepare_embedding_cosine(['a', 'b', 'c'])
    assert m.dtype == np.float64  # the C code needs doubles
    assert m == pytest.approx(np.array([[1, 1, 0], [1, 1, 0], [0, 0, 1]]))


def test_prepare_embedding_cosine_accepts_series(monkeypatch):
    seen = []
    monkeypatch.setattr(clustering, 'embed', lambda texts: seen.append(list(texts)) or np.eye(len(seen[-1])))
    clustering.prepare_embedding_cosine(pd.Series(['x', 'y']))
    assert seen == [['x', 'y']]


# label_clusters()

def test_label_clusters():
    df = pd.DataFrame({'title': list('abcde')})
    out = clustering.label_clusters(df, [{0, 2}, {4}])
    assert out['cluster'].tolist() == [0, -1, 0, -1, 1]
    assert out is df  # labels are added in place


def test_label_clusters_none():
    df = clustering.label_clusters(pd.DataFrame({'title': ['a', 'b']}), [])
    assert df['cluster'].tolist() == [-1, -1]


def test_label_clusters_from_form_clusters():
    df = pd.DataFrame({'title': list('abcd')})
    clustering.label_clusters(df, clustering.form_clusters(TWO_PAIRS.copy(), 2, .5))
    assert df.groupby('cluster').size().to_dict() == {0: 2, 1: 2}
    assert df.loc[0, 'cluster'] == df.loc[1, 'cluster'] != df.loc[2, 'cluster'] == df.loc[3, 'cluster']


# money() and unlink_money_conflicts(): different sums keep similar-sounding stories apart (#148)

@pytest.mark.parametrize('title, amounts', [
    ('Trump Promises $100 Checks for 20 Million Seniors', [100.0]),
    ('Trump again promises $5,000 checks', [5000.0]),
    ('Deal worth $1.2 billion', [1.2e9]),
    ('A $3bn bailout and a $40k bonus', [3e9, 40e3]),
    ('Nearly $100, up from $90', [100.0, 90.0]),
    ('No money here', []),
])
def test_money(title, amounts):
    assert clustering.money(title) == pytest.approx(amounts)


def test_unlink_money_conflicts():
    titles = ['Trump sends $90 checks to seniors', 'Trump promises nearly $100 checks', 'Trump promises $5,000 checks',
              'Trump announces checks for seniors']
    m = np.full((4, 4), 0.9)
    out = clustering.unlink_money_conflicts(m, titles)
    assert out[0, 1] == 0.9  # $90 ~ $100: ordinary rounding, still linked
    assert out[0, 2] == 0 and out[2, 0] == 0  # $90 vs $5,000: different money
    assert out[1, 2] == 0
    assert out[2, 3] == 0.9 and out[0, 3] == 0.9  # no amount: left alone
