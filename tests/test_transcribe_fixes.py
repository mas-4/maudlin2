from app import transcribe


def test_known_mishearings_are_fixed_only_where_safe():
    assert transcribe.fix_text('A couple of people mentioned him taking money from APEC.') == \
        'A couple of people mentioned him taking money from AIPAC.'
    assert transcribe.fix_text('Leaders gathered for the APEC summit in Gyeongju. He took APAC money.') == \
        'Leaders gathered for the APEC summit in Gyeongju. He took AIPAC money.'  # the summit stays; the next sentence is fixed
    assert transcribe.fix_text('Funded by a PAC.') == 'Funded by a PAC.'
    assert transcribe.fix_text('Hexeth and Wattley.') == 'Hegseth and Whatley.'


def test_hotwords_hold_the_fixed_terms_and_recent_names(monkeypatch):
    from app.analysis import entities
    monkeypatch.setattr(entities, 'all_names', lambda: {'Pete Hegseth': 9, 'Abdul El-Sayed': 4, 'the economy': 3})
    words = transcribe.hotwords()
    assert words.startswith('AIPAC, ') and 'Abdul El-Sayed' in words and 'the economy' not in words
