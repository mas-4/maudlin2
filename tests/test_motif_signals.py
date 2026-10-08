"""app/analysis/motif_signals.py: the keyword signal reads a motif's note, name and claims; held out, a claim already
filed doesn't find itself in its own motif."""
import numpy as np

from app.analysis import motif_signals as ms


class NoVectors:
    def __call__(self, texts):
        return np.ones((len(texts), 4)) / 2


def index():
    return {'entries': {
        'M1': {'id': 'M1', 'name': 'Hatch Act', 'note': 'officials campaigning on government time',
               'claims': [{'claim': 'The secretary campaigned for the senator during an official visit'},
                          {'claim': 'A cabinet member broke the Hatch Act at a rally'}]},
        'M2': {'id': 'M2', 'name': 'Sharia takeover', 'note': 'immigrants said to be imposing religious law',
               'claims': [{'claim': 'Sharia courts are spreading in Dearborn'}]}}}


def test_keywords_find_distinctive_words_and_hold_the_claim_out():
    sig = ms.Signals(index(), NoVectors())
    s = sig.keywords('Another Hatch Act violation by a cabinet member', leave_out=False)
    assert s[sig.at['M1']] > 0 and s[sig.at['M2']] == 0
    own = 'Sharia courts are spreading in Dearborn'
    full, held = sig.keywords(own, leave_out=False)[sig.at['M2']], sig.keywords(own, leave_out=True)[sig.at['M2']]
    assert full > held > 0  # held out, only the motif's name still matches ('Sharia'), not the claim's own words
    assert sig.keywords('courts spreading in Dearborn', leave_out=False)[sig.at['M2']] > 0
    ix = index()
    ix['entries']['M2']['claims'] = [{'claim': 'Another claim'}]
    other = ms.Signals(ix, NoVectors())
    assert other.keywords('courts spreading in Dearborn', leave_out=False)[other.at['M2']] == 0


def test_tokens_drop_little_words_and_plurals():
    assert ms.tokens("The courts' rulings are Sharia's") == ['court', 'ruling', 'sharia']


def test_news_out_takes_the_headlines_main_directions_away(tmp_path):
    rng = np.random.default_rng(0)
    topic = np.eye(6)[0]
    heads = {f'h{i}': v for i, v in enumerate(rng.normal(size=(60, 6)) * 0.1 + np.outer(rng.normal(size=60) * 3, topic))}
    old = ms.NEWS_DIRECTIONS
    ms.NEWS_DIRECTIONS = 1
    try:
        basis = ms.news_directions(lambda ts: np.array([heads[t] for t in ts]), lambda: list(heads), str(tmp_path / 'n.npz'))
        assert abs(abs(basis[1][0] @ topic) - 1) < 0.05  # the direction the news varies along most
        again = ms.news_directions(None, list, str(tmp_path / 'n.npz'))  # kept a day: not worked out again
        assert np.allclose(again[1], basis[1])
    finally:
        ms.NEWS_DIRECTIONS = old
    v = ms.news_out(np.array([[1.0, 1, 0, 0, 0, 0]]), (np.zeros(6), topic[None]))
    assert np.allclose(v, [[0, 1, 0, 0, 0, 0]])
    assert ms.news_directions(None, lambda: ['one'], str(tmp_path / 'none.npz')) is None


def test_news_signal_holds_the_claim_out_of_its_motif():
    class Vectors:
        def __call__(self, texts):
            return np.array([[1.0, 0, 0] if 'Sharia' in t else [0, 1.0, 0] if 'Hatch' in t else [0, 0, 1.0] for t in texts])
    sig = ms.Signals(index(), Vectors())
    sig._news = (np.zeros(3), np.zeros((0, 3)))
    own = 'Sharia courts are spreading in Dearborn'
    note, near = sig.news(own, leave_out=False)
    assert near[sig.at['M2']] == 1.0
    assert sig.news(own, leave_out=True)[1][sig.at['M2']] == -1.0  # its only claim, held out
    flat = ms.Signals(index(), Vectors())
    flat._news = False
    assert not flat.news(own, False)[0].any()


def test_a_claims_layers_meet_each_motifs_note_and_the_layer_of_its_genre():
    class Vectors:
        def __call__(self, texts):
            return np.array([[1.0, 0] if 'campaign' in t.lower() else [0, 1.0] for t in texts])
    ix = index()
    ix['entries']['M1']['facets'] = {'genre': 'Plots'}
    sig = ms.Signals(ix, Vectors())
    sig.layered[mi_key('A claim')] = {'character': 'none', 'plot': 'An official campaigns from office', 'theory': 'none',
                                      'argument': 'none', 'value': 'none'}
    best, of_genre = sig.layers('A claim', ask=False)
    assert best[sig.at['M1']] == 1.0 and of_genre[sig.at['M1']] == 1.0  # its plot meets the Plots motif's note
    assert of_genre[sig.at['M2']] == -1.0  # no genre: no layer of its genre
    assert sig.layers('Unread claim', ask=False)[0].tolist() == [-1.0, -1.0]


def mi_key(text):
    from app.analysis import motif_index
    return motif_index.key(text)
