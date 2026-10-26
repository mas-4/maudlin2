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
    assert sc.claims() == []  # filing and the checker read what the last run kept (RETOLD), not worked out again
    monkeypatch.setattr(sc.llm, 'backend', lambda: 'test')
    monkeypatch.setattr(sc, 'read_episodes', lambda store, budget: 0)
    sc.extract()  # a run with no RETOLD yet keeps one
    assert [x['source'] for x in sc.claims()] == [sc.SOURCE]


def test_two_show_claims_on_one_topic_are_not_one_claim_unless_close(monkeypatch):
    """Oct 25: "Trump says ... a jihadist" and Megyn Kelly's "the Harris campaign's Hitler comparisons" (0.81 alike)
    were grouped as one claim, and the pair made it "retold" though each was told on one show"""
    import app.narratives
    vec = {'Trump calls the candidate a jihadist.': [1.0, 0.0], 'The Harris campaign used Hitler comparisons.': [0.81, 0.586],
           'Trump says the candidate is a jihadist.': [0.95, 0.312]}
    monkeypatch.setattr(app.narratives, 'embed', lambda texts: np.array([vec[t] for t in texts]))
    c = lambda claim: {'claim': claim, 'quote': 'q', 'speaker': 'host', 'at': 0}  # noqa: E731
    ep = lambda show, claim: {'show': show, 'date': '2026-10-25', 'lean': 'right', 'claims': [c(claim)]}  # noqa: E731
    assert sc.retold({'u1': ep('MeidasTouch', 'Trump calls the candidate a jihadist.'),
                      'u2': ep('Megyn Kelly', 'The Harris campaign used Hitler comparisons.')}) == []  # 0.81: two claims
    got = sc.retold({'u1': ep('MeidasTouch', 'Trump calls the candidate a jihadist.'),
                     'u2': ep('Pod Save America', 'Trump says the candidate is a jihadist.')})  # 0.95: one claim, retold
    assert len(got) == 1 and got[0]['shows'] == ['MeidasTouch', 'Pod Save America']


def test_a_news_briefings_presenter_is_not_a_teller(monkeypatch):
    """Oct 18: a briefing's presenter reads the news; its clips and guests still tell"""
    import app.narratives
    monkeypatch.setattr(app.narratives, 'embed', lambda texts: np.array([[1.0] + [0.0] * 7 for _ in texts]))
    c = lambda speaker: {'claim': 'Russia broke the energy ceasefire.', 'quote': 'q', 'speaker': speaker, 'at': 0}  # noqa: E731
    ep = lambda source, show, speaker: {'source': source, 'show': show, 'date': '2026-10-15', 'lean': 'center',  # noqa: E731
                                        'claims': [c(speaker)]}
    assert sc.retold({'u1': ep('bbcglobal', 'BBC', 'host'), 'u2': ep('cnn5things', 'CNN', 'host')}) == []
    got = sc.retold({'u1': ep('bbcglobal', 'BBC', 'clip'), 'u2': ep('cnn5things', 'CNN', 'guest')})
    assert len(got) == 1 and got[0]['shows'] == ['BBC', 'CNN']


def test_show_claims_group_around_a_centre_and_keep_their_filed_words(monkeypatch):
    """Oct 25: chains of alike claims joined a topic into one group (149 tellings, "Trump falls asleep" to "the Epstein
    files"), and a regrouping filed 270 claims told before under new words"""
    import app.narratives
    angle = {'A sleeps.': 0, 'A dozes.': 5, 'A snoozes.': -5, 'A naps.': 30, 'A lies.': 60}  # a chain: sleeps, naps, lies
    vec = {t: [np.cos(np.radians(d)), np.sin(np.radians(d))] for t, d in angle.items()}
    monkeypatch.setattr(app.narratives, 'embed', lambda texts: np.array([vec[t] for t in texts]))
    c = lambda claim: {'claim': claim, 'quote': 'q', 'speaker': 'host', 'at': 0}  # noqa: E731
    store = {f'u{n}': {'show': f'Show {n}', 'date': '2026-10-25', 'lean': 'left', 'claims': [c(t)]}
             for n, t in enumerate(angle)}
    got = sc.retold(store)
    assert len(got) == 1 and 'A lies.' not in {t['claim'] for t in got[0]['told']}  # alike a neighbour, not the centre
    assert sc.retold(store, lambda text: text == 'A naps.')[0]['claim'] == 'A naps.'  # the filed words kept
