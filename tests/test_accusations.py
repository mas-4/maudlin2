"""The accusations screen (app/analysis/accusations.py): a named private person accused of a crime is swapped out for
who they are, or the claim is held back; public officials stay named; fact-checkers' claims pass as written."""
from app.analysis import accusations as ac

GELLER = 'Jacob Geller is a rapist who has avoided accountability and continues to profit from his actions.'


def person(names, who='a YouTuber', known=False, crime='rape'):
    return {'names': names, 'who': who, 'well_known': known, 'crime': crime}


def test_private_person_swapped_out():
    v = {'accused': [person(['Jacob Geller'])]}
    assert ac.redacted(GELLER, v) == 'A YouTuber is a rapist who has avoided accountability and continues to profit from his actions.'


def test_every_mention_swapped_and_a_leftover_surname_holds_it_back():
    claim = 'Jacob Geller hid it, and Geller still profits.'
    assert ac.redacted(claim, {'accused': [person(['Jacob Geller', 'Geller'])]}) == 'A YouTuber hid it, and a YouTuber still profits.'
    assert ac.redacted(claim, {'accused': [person(['Jacob Geller'])]}) is None


def test_name_not_in_the_claim_holds_it_back():
    assert ac.redacted(GELLER, {'accused': [person(['J. Geller'])]}) is None


def test_an_appositive_name_doesnt_double_up():
    claim = 'A Chinese national, Wanying Zhang, was arrested for spying.'
    v = {'accused': [person(['Wanying Zhang'], 'a Chinese national', crime='spying')]}
    assert ac.redacted(claim, v) == 'A Chinese national was arrested for spying.'


def test_no_crime_named_no_swap():
    claim = 'Jacob Geller is rude.'
    assert ac.redacted(claim, {'accused': [person(['Jacob Geller'], crime='')]}) == claim
    assert ac.redacted(claim, {'accused': [person(['Jacob Geller'], crime='none')]}) == claim


def test_blacklist_swaps_names_whatever_the_model_said(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, 'CACHE', str(tmp_path / 'accusations.json'))
    (tmp_path / 'never.json').write_text('{"Jacob Geller": "a YouTuber"}')
    monkeypatch.setattr(ac, 'NEVER_NAMED', str(tmp_path / 'never.json'))
    s = ac.Screen(reader=lambda claim: {'accused': []})
    assert s.shown('Geller did it, says Jacob Geller.') == 'A YouTuber did it, says a YouTuber.'


def test_people_the_headlines_name_stay():
    claim = 'Christa Pike murdered a classmate.'
    v = {'accused': [person(['Christa Pike'], 'a death row inmate', crime='murder')]}
    assert ac.redacted(claim, v, in_news=lambda name: name == 'Christa Pike') == claim
    assert ac.redacted(claim, v) == 'A death row inmate murdered a classmate.'


def test_always_named_list(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, 'CACHE', str(tmp_path / 'accusations.json'))
    (tmp_path / 'always.json').write_text('["Don Huffines"]')
    monkeypatch.setattr(ac, 'ALWAYS_NAMED', str(tmp_path / 'always.json'))
    s = ac.Screen(reader=lambda claim: {'accused': [person(['Don Huffines'], 'a businessman', crime='fraud')]})
    assert s.shown('Don Huffines committed fraud.') == 'Don Huffines committed fraud.'


def test_well_known_people_and_groups_stay():
    claim = 'Trump, a convicted rapist, expresses sympathy for the Cornell 7 accused rapists.'
    v = {'accused': [person(['Trump'], 'a former president', True), person(['the Cornell 7'], 'a group')]}
    assert ac.redacted('Elon Musk stole the election.', {'accused': [person(['Elon Musk'], 'a businessman', True)]}) \
        == 'Elon Musk stole the election.'
    assert ac.redacted(claim, v) == claim
    assert ac.redacted('Nothing here.', {'accused': []}) == 'Nothing here.'


def test_screen_reads_new_claims_up_to_its_limit_and_holds_back_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, 'CACHE', str(tmp_path / 'accusations.json'))
    asked = []

    def reader(claim):
        asked.append(claim)
        return {'accused': [person(['Jacob Geller'])]} if 'Geller' in claim else {'accused': []}

    s = ac.Screen(read_new=2, reader=reader)
    s.named = {'Jacob Geller': 0}
    assert s.shown(GELLER).startswith('A YouTuber is')
    assert s.shown('Prices are up.') == 'Prices are up.'
    assert s.shown('Not read yet.') is None  # over the limit: held back until a later build reads it
    assert s.shown(GELLER, 'Snopes') == GELLER  # a fact-checker's claim, as they wrote it
    assert s.changes(GELLER) and not s.changes('Prices are up.')
    s.save()
    again = ac.Screen(read_new=0, reader=reader)
    assert again.shown('Prices are up.') == 'Prices are up.' and len(asked) == 2
