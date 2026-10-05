from app.analysis import focus_group as fg

PART = ("I just know Vivek is extremely rich. Not that that's a bad thing, but most of the people in power are and "
        "they just have no clue what it's like to be a middle class person right now. If he's one of Trump's boys, "
        "that tells me all I need to know. She is pro-choice.")


def claim(text, quote):
    return {'claim': text, 'quote': quote, 'side': 'Trump voter', 'at': 0}


def test_a_claim_needs_its_own_quote_from_the_transcript():
    kept, dropped = fg.checked([
        claim('Vivek is rich and out of touch', "I just know Vivek is extremely rich. Not that that's a bad thing"),
        # The same quote again, a little longer, for a claim it doesn't support
        claim('Amy Acton is not credible', "I just know Vivek is extremely rich. Not that that's a bad thing, but "
              "most of the people in power are"),
        claim('Acton is pro-choice', 'She is pro-choice.'),  # short quotes are checked whole
        claim('Prices are up', 'Everything costs twice what it did'),  # not said here
    ], PART)
    assert [c['claim'] for c in kept] == ['Vivek is rich and out of touch', 'Acton is pro-choice']
    assert [(c['claim'], c['why']) for c in dropped] == [
        ('Amy Acton is not credible', 'quote already used for another claim'),
        ('Prices are up', 'quote not in the transcript')]


def test_extraction_keeps_only_checked_claims(monkeypatch, tmp_path):
    monkeypatch.setattr(fg, 'STORE', str(tmp_path / 'fg.json'))
    monkeypatch.setattr(fg.llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(fg, 'episodes', lambda: [{'title': 'Ep', 'url': 'u', 'date': '2026-10-01',
                                                  'chunks': [{'at': 0.0, 'text': PART}]}])
    monkeypatch.setattr(fg.llm, 'complete_json', lambda *a, **k: {'reason': 'voters', 'claims': [
        {'claim': 'Vivek is rich and out of touch', 'quote': 'they just have no clue what it is like', 'side': 'Trump voter'},
        {'claim': 'Ohio has the best schools in America', 'quote': 'our schools are the best', 'side': ''}]})
    store = fg.extract()
    assert [c['claim'] for c in store['u']['claims']] == ['Vivek is rich and out of touch']
    assert store['u']['dropped'][0]['why'] == 'quote not in the transcript'
    assert [c['claim'] for c in fg.claims()] == ['Vivek is rich and out of touch']
