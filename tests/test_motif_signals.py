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
