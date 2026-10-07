"""app/analysis/pipelines.prepare remembers results; a list result is a fresh copy each time, so a caller changing it
can't change what the next caller gets."""
from app.analysis import pipelines as pl


def test_prepare_remembers_and_hands_out_copies():
    calls = []

    def split(text):
        calls.append(text)
        return text.split()
    steps = [str.lower, split]
    first = pl.prepare('Storm Hits Coast', steps)
    first.append('changed')
    again = pl.prepare('Storm Hits Coast', steps)
    assert again == ['storm', 'hits', 'coast'] and len(calls) == 1


def test_prepare_with_a_step_that_cannot_be_a_key():
    class Step:
        __hash__ = None

        def __call__(self, text):
            return text.upper()
    assert pl.prepare('a', [Step()]) == 'A'
