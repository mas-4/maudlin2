"""Story pages: retellings from each day's report tied to the saved story, and voters telling the same shape."""
from datetime import datetime as dt

from app.site import page_story as ps


STORIES = [{'id': 1, 'label': 'Russian lab worker dies in suspected plague incident', 'first': dt(2026, 10, 4), 'last': dt(2026, 10, 6)},
           {'id': 2, 'label': 'Brazil holds presidential election', 'first': dt(2026, 10, 3), 'last': dt(2026, 10, 5)},
           {'id': 3, 'label': 'Brazil holds presidential election', 'first': dt(2026, 9, 20), 'last': dt(2026, 9, 21)}]


def test_a_report_link_finds_its_story():
    on = dt(2026, 10, 5)
    assert ps.story_of({'label': 'x', 'id': 2}, STORIES, on) == 2  # its id, when the report kept it
    assert ps.story_of({'label': 'Brazil holds presidential election'}, STORIES, on) == 2  # same label: the latest
    # Reworded since: the story around then sharing most words
    assert ps.story_of({'label': 'Russian lab worker dies from suspected plague infection'}, STORIES, on) == 1
    assert ps.story_of({'label': 'Russian lab worker dies from suspected plague infection'}, STORIES, dt(2026, 9, 1)) is None
    assert ps.story_of({'label': 'Plague in Russia'}, STORIES, on) is None  # too few words in common


def test_retold_on_several_days_shows_once(monkeypatch, tmp_path):
    from app.analysis import focus_group, motif_index, narrative_threads
    from app.site import page_folklore
    group = lambda claim, label, people: {'authors': people, 'label': {'retold': True, 'narrative': claim},  # noqa: E731
                                          'story': {'label': label, 'relation': 'same event'}}
    reports = [{'made': '2026-10-06T04:39', 'file': 'report-2026-10-06-0439.json',
                'found': [group('The plague leaked from a lab', STORIES[0]['label'], 50)]},
               {'made': '2026-10-05T08:17', 'file': 'report-2026-10-05-0817.json',
                'found': [group('The plague leaked from a lab', 'Russian lab worker dies from plague', 9),
                          group('It was a bioweapon test', 'Russian lab worker dies from plague', 4)]}]
    monkeypatch.setattr(ps, 'reports_by_day', lambda days=7: reports)
    monkeypatch.setattr(motif_index, 'load', lambda: {'entries': {}, 'claims': {}, 'corrections': {}})
    monkeypatch.setattr(narrative_threads, 'load', lambda: {})
    monkeypatch.setattr(focus_group, 'load', lambda: {})
    monkeypatch.setattr(page_folklore, 'told_before', lambda *a: [])
    found = ps.folklore_by_story(STORIES)
    assert [(f['when'], f['people'], f['claim']) for f in found[1]] == [
        ('Oct 6', 50, 'The plague leaked from a lab'), ('Oct 5', 4, 'It was a bioweapon test')]


def test_voters_tell_the_same_shape(monkeypatch):
    from app.analysis import focus_group, motif_index
    key = motif_index.key
    told = {'claim': 'Seth Moulton takes corporate money', 'source': 'Focus Group', 'ref': 'https://fg/1', 'date': '2026-08-29'}
    online = {'claim': 'Billionaires bought the election', 'source': 'narrative'}
    late = {'claim': 'Filed after it was verified', 'source': 'Focus Group', 'ref': 'https://fg/1', 'date': '2026-09-01'}
    index = {'corrections': {}, 'entries': {'M1': {'id': 'M1', 'name': 'Money in politics', 'claims': [told, online, late],
                                                   'done': [key(told['claim']), key(online['claim'])]}}}
    monkeypatch.setattr(focus_group, 'load', lambda: {'https://fg/1': {'title': 'S6 Ep56: Markey'}})
    found = ps.voters_by_motif([{'motifs': [{'id': 'M1', 'name': 'Money in politics'}]}], index)
    assert [(v['claim'], v['episode']) for v in found] == [('Seth Moulton takes corporate money', 'S6 Ep56: Markey')]
