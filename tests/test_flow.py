"""app/analysis/flow.py: news stories into retellings, over time"""
from datetime import datetime as dt

from app.analysis import flow, motif_index as mi, stories


def test_a_story_and_the_motifs_it_was_told_as_in_time_order(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    c = lambda t, d, sid, src='narrative': {'claim': t, 'source': src, 'date': d, 'story': sid, 'checked': 'yes'}  # noqa: E731
    mi.save({'next': 4, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Graft', 'facets': {'genre': 'Plots'}, 'claims': [c('he took a bribe', '2026-10-08', 5)]},
        'M002': {'id': 'M002', 'name': 'Straight news', 'watch': True, 'claims': [c('a contract was signed', '2026-10-07', 5)]},
        'M003': {'id': 'M003', 'name': 'Cover-up', 'claims': [c('they hid it', '2026-10-10', 6, 'Snopes'),
                                                              {'claim': 'no story', 'source': 'shows', 'date': '2026-10-10'}]}}})
    monkeypatch.setattr(stories, 'merges', lambda: {6: 5})  # story 6 was folded into 5
    monkeypatch.setattr(flow, 'story_rows', lambda ids: {5: {'label': 'A shipyard deal', 'first': '2026-10-07T09:00',
                                                             'last': '2026-10-09T09:00'}} if 5 in ids else {})
    got = flow.flow()
    (s,) = got['stories']
    assert [(f['motif'], f['lag'], f['source'], f['plain']) for f in s['filings']] == [
        ('M002', 0, 'posts', True), ('M001', 1, 'posts', False), ('M003', 3, 'fact-check', False)]
    assert s['motifs'] == 2 and got['motifs']['M001'] == {'name': 'Graft', 'genre': 'Plots', 'stories': 1, 'plain': False}
    assert got['lags'] == [1, 3] and dt.fromisoformat(got['made'])
