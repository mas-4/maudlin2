from datetime import datetime as dt
from datetime import timedelta as td

from app.analysis import llm, motif_index as mi, watch_list as wl


def setup(monkeypatch, tmp_path, texts=None):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(wl, 'STORE', str(tmp_path / 'watch.json'))
    monkeypatch.setattr(wl, 'REFILE_LOG', str(tmp_path / 'refile.jsonl'))
    looked = []

    def known(index):
        looked.append(1)
        return {mi.key(t): {'claim': t, 'source': 'narrative', 'date': '2026-10-01', **extra}
                for t, extra in (texts or {}).items()}
    monkeypatch.setattr(wl, 'known_texts', known)
    from app.analysis import narrative_threads
    monkeypatch.setattr(narrative_threads, 'load', lambda: {'threads': {}})
    mi.save({'next': 3, 'claims': {mi.key('Polls closed at eight'): ['M001'], mi.key('The Senate met'): [],
                                   mi.key('The House met'): [], mi.key('The count was rigged'): ['M002'],
                                   mi.key('Lost words'): []},
             'entries': {
                 'M001': {'id': 'M001', 'name': 'Straight news', 'watch': True, 'claims': [
                     {'claim': 'Polls closed at eight', 'source': 'narrative', 'date': '2026-09-30', 'story': 5}]},
                 'M002': {'id': 'M002', 'name': 'Rigged count', 'not_claims': [mi.key('The House met')], 'claims': [
                     {'claim': 'The count was rigged', 'source': 'narrative', 'date': '2026-10-03', 'checked': 'yes'}]}}})
    return looked


def test_a_watched_motifs_claims_and_claims_with_no_motif_are_watched(monkeypatch, tmp_path):
    looked = setup(monkeypatch, tmp_path, {'The Senate met': {'story': 5}, 'The House met': {}})
    store = wl.sync()
    ws = {w['claim']: w for w in store['claims'].values()}
    assert {c: (w['why'], w['plain']) for c, w in ws.items()} == {
        'Polls closed at eight': ('watched motif', True), 'The Senate met': ('no motif', True),
        'The House met': ('no motif', True)}  # the told claim isn't watched; 'Lost words' has no words to file
    assert ws['Polls closed at eight']['date'] == '2026-09-30' and ws['Polls closed at eight']['story'] == 5
    assert store['unfound'] == {mi.key('Lost words'): dt.now().strftime('%Y-%m-%d')}
    wl.sync(store=store)
    assert len(looked) == 1  # a claim whose words weren't found is looked for once a day
    # The plain report is the story's baseline, with no motif too
    from app.analysis import stories
    monkeypatch.setattr(stories, 'merges', dict)
    wl.save(store)
    assert [(r['claim'], r['motif'], r['plain']) for r in mi.story_motifs(5)] == [
        ('Polls closed at eight', 'M001', True), ('The Senate met', None, True)]


def test_a_plain_report_later_told_as_a_motif_is_filed_unchecked_and_dated(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, {'The Senate met': {'story': 5}, 'The House met': {}})
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')

    class Lister:
        def __init__(self, index, claims, budget=None):
            pass

        def __call__(self, index, claim):
            return mi.live(index)

        def save(self):
            pass
    monkeypatch.setattr('app.analysis.motif_filing.Shortlister', Lister)
    picks = {'Polls closed at eight': ['M001'], 'The Senate met': ['M002'], 'The House met': ['M002']}
    monkeypatch.setattr('app.analysis.motif_filing.name_claim', lambda claim, shown: {
        'existing': [e for e in shown if e['id'] in picks[claim]], 'new': []})
    assert wl.refile(budget=None) == {'still plain': 1, 'told': 1, 'none': 1}
    index = mi.load()
    rec = next(c for c in index['entries']['M002']['claims'] if c['claim'] == 'The Senate met')
    today = dt.now().strftime('%Y-%m-%d')
    assert rec['refiled'] == {'at': today, 'was': 'no motif'} and not rec.get('checked')  # for the person to judge
    assert rec['date'] == '2026-10-01' and rec['story'] == 5  # still the day it was reported
    assert index['claims'][mi.key('The Senate met')] == ['M002']
    assert index['claims'][mi.key('The House met')] == []  # a person took it out of M002: not filed there again
    assert [(r['claim'], r['reported'], r['at'][:10], r['motifs']) for r in wl.told_later()] == [
        ('The Senate met', '2026-10-01', today, ['M002'])]
    assert wl.due(wl.load(), index) == []  # filed again: nothing due for a week
    later = [w['claim'] for w, why in wl.due(wl.sync(index), index, now=dt.now() + td(days=8))]
    assert sorted(later) == ['Polls closed at eight', 'The House met']  # the told claim isn't watched now
    mi.check('The Senate met', 'M002', 'no')  # the person says no: back to no motif, and watched again
    assert wl.sync()['claims'][mi.key('The Senate met')]['plain']


def test_a_narrative_told_again_on_a_later_day_is_filed_again_at_once(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, {'The Senate met': {}})
    from app.analysis import narrative_threads
    monkeypatch.setattr(narrative_threads, 'load', lambda: {'threads': {'N0001': {'days': [
        {'claim': 'The Senate met', 'date': '2026-10-01'}, {'claim': 'The Senate met again', 'date': '2026-10-05'}]}}})
    store = wl.sync()
    for w in store['claims'].values():
        w['refiled'] = '2026-10-02T03:00:00'
    found = wl.due(store, mi.load(), now=dt(2026, 10, 6))
    assert [(w['claim'], why) for w, why in found] == [('The Senate met', 'told again on 2026-10-05')]


def test_a_motif_not_marked_watched_holds_tellings_not_plain_news(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, {})
    mi.set_watch('M001', on=False)  # Straight news by name alone isn't a watch list: the person's mark makes it one
    assert [w['claim'] for w in wl.sync()['claims'].values() if w['plain']] == []
