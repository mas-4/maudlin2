"""app/analysis/show_claims.py: claims read from the shows' transcripts keep only quotes found in the transcript,
say who told them, and reach the motif index only once retold on two shows (or by two callers)."""
import numpy as np

from app.analysis import llm
from app.analysis import show_claims as sc

TEXT = ("Welcome back. Caller from Ohio, you're on the air. Yeah, the Democrats are paying people to stuff ballot boxes "
        "in every swing state, I've seen it. Thanks for the call. Now this hour is brought to you by mattresses.")


def test_a_part_keeps_quoted_claims_with_their_speaker(monkeypatch):
    def complete(prompt, schema, **k):
        if 'claims' in schema['properties']:
            assert 'Clay & Buck' in prompt and 'a call-in radio show' in prompt
            return {'reason': 'r', 'claims': [
                {'claim': 'Democrats pay people to stuff ballot boxes in swing states.', 'speaker': 'caller',
                 'quote': 'the Democrats are paying people to stuff ballot boxes in every swing state'},
                {'claim': 'Mattresses are great.', 'speaker': 'host', 'quote': 'the best mattress you will ever own'}]}
        return {'reason': 'r', 'verdict': 'evidence'}
    monkeypatch.setattr(llm, 'complete_json', complete)
    ep = {'show': 'Clay & Buck', 'kind': sc.KINDS['call-in'], 'title': 'Hour 1'}
    kept, dropped = sc.read_part(ep, {'at': 60.0, 'text': TEXT})
    assert [(c['speaker'], c['at']) for c in kept] == [('caller', 60)]
    assert dropped[0]['why'] == 'quote not in the transcript'  # the made-up ad quote


def test_only_retold_claims_reach_the_index(monkeypatch):
    def fake_embed(texts):
        out = []
        for t in texts:
            v = np.zeros(8)
            v[0 if 'ballot' in t else 1 if 'Fed' in t else 2] = 1
            out.append(v)
        return np.array(out)
    import app.narratives
    monkeypatch.setattr(app.narratives, 'embed', fake_embed)
    c = lambda claim, speaker='host': {'claim': claim, 'quote': 'q', 'speaker': speaker, 'at': 0}  # noqa: E731
    store = {
        'u1': {'show': 'Show A', 'date': '2026-10-06', 'lean': 'right', 'claims': [c('Ballot mules stuff ballot boxes.'), c('The Fed is printing money.')]},
        'u2': {'show': 'Show B', 'date': '2026-10-07', 'lean': 'right', 'claims': [c('Paid ballot mules stuffed the boxes.')]},
        'u3': {'show': 'Show C', 'date': '2026-10-07', 'lean': 'left', 'claims': [c('Something else entirely.', 'caller')]},
    }
    got = sc.retold(store)
    assert len(got) == 1 and got[0]['shows'] == ['Show A', 'Show B'] and got[0]['tellings'] == 2  # the Fed: one show only
    sc.save(store)
    assert [x['source'] for x in sc.claims()] == [sc.SOURCE]
