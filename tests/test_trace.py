"""The filing pipeline's trace (app/analysis/trace.py) and the 🧠 Live page's view of it (app/analysis/trace_view.py)"""
import json
from datetime import datetime as dt
from datetime import timedelta as td

import numpy as np
import pytest

from app.analysis import motif_index as mi
from app.analysis import trace
from app.analysis import trace_view as tv


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(trace, 'FOLDER', str(tmp_path / 'trace'))
    tv._cache.clear()
    tv._files.clear()
    return tmp_path / 'trace'


def events(folder) -> list[dict]:
    return [json.loads(x) for p in sorted(folder.glob('*.jsonl')) for x in p.read_text().splitlines()]


def test_the_trace_key_is_the_motif_index_key():
    assert trace.key('  A Claim told ') == mi.key('  A Claim told ')


def test_tracing_never_raises(folder, tmp_path, monkeypatch):
    trace.emit('written', None)  # no claim
    trace.emit('written', '   ')
    trace.emit('written', 'a claim', thing=object(), arr=np.array([1.5, np.nan]), n=np.float32(0.25))
    got = events(folder)
    assert len(got) == 1 and got[0]['arr'] == [1.5, None] and got[0]['n'] == 0.25 and isinstance(got[0]['thing'], str)
    (tmp_path / 'a file').write_text('')
    monkeypatch.setattr(trace, 'FOLDER', str(tmp_path / 'a file'))  # a folder that can't be made
    trace.emit('written', 'a claim')
    trace.written_narratives(None)
    trace.written_shows(None, [{'claim': 3}])
    trace.shortlisted({}, None, None)
    trace.picked('a claim', None, [])
    trace.scored('a claim', '', ['M001'], [[1.0]], [0.1], {}, ['x'])


def test_a_narratives_claim_keeps_its_posts_keys_never_their_words(folder):
    report = {'made': '2026-10-14T04:00', 'found': [
        {'label': {'retold': True, 'narrative': 'The ruler is senile', 'genre': 'rumor'}, 'posts': 12, 'authors': 9,
         'variety': 0.8, 'examples': ['my uncle says the old man forgot his own name'], 'keys': ['k1', 'k2']},
        {'label': {'retold': False, 'narrative': 'Rain today'}, 'posts': 5, 'authors': 5, 'keys': ['k3']}]}
    trace.written_narratives(report)
    got = events(folder)
    assert [(e['s'], e['c'], e['keys'], e['posts']) for e in got] == [('written', 'The ruler is senile', ['k1', 'k2'], 12)]
    assert 'uncle' not in json.dumps(got)


def test_old_days_are_deleted(folder):
    folder.mkdir()
    old = folder / f'{dt.now() - td(days=trace.KEEP_DAYS + 1):%Y-%m-%d}.jsonl'
    old.write_text('{}\n')
    keep = folder / f'{dt.now() - td(days=2):%Y-%m-%d}.jsonl'
    keep.write_text('{}\n')
    trace.prune()
    assert not old.exists() and keep.exists()


def test_a_shortlist_is_traced_with_every_signal_for_every_motif_shown(folder, monkeypatch):
    from app.analysis import motif_retriever as mr
    entries = [{'id': f'M00{i}', 'name': f'm{i}', 'claims': [{'claim': 'x'}]} for i in range(1, 5)]
    seed = {'id': 'M009', 'name': 'a seed', 'claims': []}
    X = np.array([[0.1, 1.0], [0.9, 2.0], [0.5, 3.0], [0.3, 4.0]])
    score = X[:, 0]
    mr._keep(mi.key('the claim'), 'learned', entries, X, score, [1, 2, 3, 0], [1, 2], [3], ['today', 'votes'],
             [1.0, 0.5], -0.2, [0.0, 2.0], [1.0, 1.0])

    class Lister:
        class sig:
            shapes = {mi.key('the claim'): 'a shape'}
            layered = {mi.key('the claim'): {'plot': 'a plot'}}
    trace.shortlisted({'claim': 'the claim', 'source': 'narrative'}, [entries[1], entries[2], entries[3], seed], Lister(),
                      next_motif=10)
    shaped, sl = events(folder)
    assert shaped['s'] == 'shaped' and shaped['shape'] == 'a shape' and shaped['layers'] == {'plot': 'a plot'}
    assert sl['s'] == 'shortlist' and sl['method'] == 'learned' and sl['features'] == ['today', 'votes']
    assert sl['shown'] == ['M002', 'M003', 'M004', 'M009'] and sl['seeds'] == ['M009'] and sl['next_motif'] == 10
    assert [(r['id'], r['why'], r.get('rank')) for r in sl['rows']] == [('M002', 'top', 0), ('M003', 'top', 1),
                                                                         ('M004', 'tree', 2), ('M009', 'seed', None)]
    assert sl['rows'][0]['x'] == [0.9, 2.0] and sl['next'] == [{'id': 'M001', 'rank': 3, 'score': 0.1}]
    # another claim's shortlist isn't taken for this one's
    trace.shortlisted({'claim': 'another claim'}, [entries[0]], None)
    assert events(folder)[-1]['method'] == 'closest' and 'rows' not in events(folder)[-1]


def test_a_scoring_is_traced_with_its_features_weights_and_fit(folder):
    m = {'weights': {'votes': 2.0, 'judge': 1.0}, 'bias': -1.0, 'at': '2026-10-13T13:43:09', 'test': {'sure_at': 0.85}}
    trace.scored('the claim', 'narrative', ['M001'], np.array([[1.0, 0.5]]), np.array([1.5]), m, ['votes', 'judge'])
    (e,) = events(folder)
    assert e['s'] == 'scored' and 'c' not in e and e['x'] == [[1.0, 0.5]] and e['w'] == [2.0, 1.0] and e['bias'] == -1.0
    assert e['fit'] == [round(1 / (1 + np.exp(-1.5)), 3)] and e['sure_at'] == 0.85


@pytest.fixture
def logs(folder, tmp_path, monkeypatch):
    """An index, the shortlist and refile logs, the signals' caches and a curation log, as the pipeline left them"""
    from app.analysis import curation_db, filing_confidence as fc, motif_signals as ms, watch_list
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(mi, 'SHORTLIST_LOG', str(tmp_path / 'shortlist.jsonl'))
    monkeypatch.setattr(watch_list, 'REFILE_LOG', str(tmp_path / 'refile.jsonl'))
    monkeypatch.setattr(ms, 'SHAPES', str(tmp_path / 'shapes.json'))
    monkeypatch.setattr(ms, 'LAYERED', str(tmp_path / 'layers.json'))
    monkeypatch.setattr(fc, 'CURATION_LOG', str(tmp_path / 'curation.jsonl'))
    monkeypatch.setattr(fc, 'ALTERNATIVES', str(tmp_path / 'alternatives.json'))
    monkeypatch.setattr(fc, 'MODEL', str(tmp_path / 'confidence.json'))
    monkeypatch.setattr(curation_db, 'DB', str(tmp_path / 'curation.sqlite'))
    monkeypatch.setattr(tv, '_claim_detail', lambda text: {'kind': 'fact-check', 'source': 'PolitiFact', 'title': 'Is he?',
                                                             'url': 'https://example.org/x', 'piece': 'p' * 5000})
    claim, other = 'The ruler is senile', 'The vote was rigged'
    k = mi.key(claim)
    mi.save({'next': 4, 'claims': {k: ['M001', 'M003'], mi.key(other): ['M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Senile ruler', 'done': [], 'claims': [
            {'claim': claim, 'source': 'PolitiFact', 'fit': 0.91, 'fit_model': '2026-10-13T13:43:09', 'checked': 'yes',
             'story': 7, 'story_tie': 'same event'}]},
        'M002': {'id': 'M002', 'name': 'Rigged count', 'done': [], 'claims': [
            {'claim': other, 'source': 'narrative', 'fit': 0.97, 'checked': 'yes'}]},
        'M003': {'id': 'M003', 'name': 'Doddering elder', 'claims': [{'claim': claim, 'source': 'PolitiFact'}]}}})
    with open(mi.SHORTLIST_LOG, 'w') as f:
        f.write(json.dumps({'at': '2026-01-13T10:00:00', 'key': k, 'claim': claim, 'source': 'PolitiFact', 'next': 3,
                            'shown': ['M001', 'M002'], 'seeds': [], 'picked': ['M002'], 'new': []}) + '\n')
    with open(ms.SHAPES, 'w') as f:
        json.dump({k: 'A leader is too old to rule.'}, f)
    with open(ms.LAYERED, 'w') as f:
        json.dump({k: {'character': 'an old leader', 'plot': 'none'}}, f)
    with open(fc.CURATION_LOG, 'w') as f:
        f.write(json.dumps({'at': '2026-01-13T12:00:00', 'page': 'motif workbench', 'action': {
            'action': 'move', 'claim': claim, 'source': 'M002', 'target': 'M001', 'why': 'about age, not a count'},
            'before': {'fits': {f'{k}|M002': 0.4}, 'sure_at': 0.85}}) + '\n')
        f.write(json.dumps({'at': '2026-01-13T12:05:00', 'page': 'motif workbench', 'action': {'action': 'batch', 'steps': [
            {'action': 'check', 'claim': other, 'id': 'M002', 'answer': 'yes'}]},
            'before': {'fits': {f'{mi.key(other)}|M002': 0.97}, 'sure_at': 0.85}}) + '\n')
    return claim


def test_a_journey_from_before_tracing_is_rebuilt_from_the_logs(logs):
    j = tv.view({'claim': '#' + mi.key(logs)[:6]})
    assert j['claim']['c'] == logs and j['traced'] is False
    assert j['written']['source']['kind'] == 'fact-check' and len(j['written']['source']['piece']) == 700
    assert j['shaped'] == {'shape': 'A leader is too old to rule.', 'layers': {'character': 'an old leader', 'plot': 'none'},
                           'traced': False}
    (p,) = j['passes']
    assert p['shortlist']['traced'] is False and p['shortlist']['shown'] == ['M001', 'M002']
    assert [(r['id'], r['picked'], r.get('verdict')) for r in p['shortlist']['rows']] == [('M001', False, True),
                                                                                          ('M002', True, False)]
    assert p['picked']['picked'] == ['M002']
    assert {x['id']: x['fit'] for x in j['scored']['now']} == {'M001': 0.91, 'M003': None}
    assert j['scored']['traced'] == []
    assert [(d['act'], d['id'], d['kept'], d.get('fit')) for d in j['decided']] == [('moved out', 'M002', False, 0.4),
                                                                                    ('moved in', 'M001', True, None)]
    assert j['decided'][0]['why'] == 'about age, not a count' and j['decided'][0]['by'] == 'person'
    assert j['motifs']['M001']['name'] == 'Senile ruler' and 'M002' in j['motifs']
    json.dumps(j)  # all plain JSON for the checker


def test_a_traced_journey_shows_the_grid_and_each_signals_push(logs):
    trace.emit('shortlist', logs, shown=['M001'], method='learned', features=['votes', 'judge'], coef=[2.0, -1.0],
               mu=[0.5, 0.0], sd=[0.5, 1.0], bias=0.0, rows=[{'id': 'M001', 'why': 'top', 'rank': 0, 'score': 1.0,
                                                               'x': [1.0, 0.5]}], of=3)
    trace.picked(logs, {'existing': [{'id': 'M001'}], 'new': [], 'reason': 'An old ruler again.'}, ['M001'])
    trace.scored(logs, 'PolitiFact', ['M001'], [[1.0, 0.5]], [1.2], {'weights': {'votes': 2.0, 'judge': -1.0},
                                                                    'bias': -0.3, 'at': 'x'}, ['votes', 'judge'])
    j = tv.view({'claim': logs})
    assert j['traced'] is True
    traced = [p for p in j['passes'] if p['shortlist']['traced']]
    (p,) = traced
    row = p['shortlist']['rows'][0]
    assert row['z'] == [1.0, 0.5] and row['push'] == [2.0, -0.5] and row['picked'] and row['verdict'] is True
    assert p['picked']['reason'] == 'An old ruler again.'
    (s,) = j['scored']['traced']
    (f,) = s['filings']
    assert [(x['f'], x['c']) for x in f['pushes']] == [('votes', 2.0), ('judge', -0.5)] and f['bias'] == -0.3
    assert all(g in tv.GLOSSARY for g in ('votes', 'judge', 'arctic2 near', 'nearest claim'))


def test_the_stream_counts_stages_and_offers_examples(logs, monkeypatch):
    trace.emit('written', logs, source='PolitiFact', ref='https://example.org/x')
    trace.emit('split_proposed', logs, split=False)
    now = dt.now().isoformat(timespec='seconds')
    d = tv.view({})
    assert [s['id'] for s in d['stages']][:3] == ['written', 'shaped', 'shortlist']
    assert d['counts']['last_hour']['written'] == 1 and d['counts']['last_hour']['split'] == 1
    assert len(d['counts']['hours']) == 24 and set(d['counts']['per_hour']) == {s['id'] for s in tv.STAGES}
    assert [e['s'] for e in d['events']] == ['written', 'split'] and d['events'][0]['c'] == logs
    assert d['examples']['recent'][0]['c'] == logs
    assert d['examples']['not on its shortlist'] == []  # M001 was on its shortlist
    assert d['examples']['passed as sure'][0]['c'] == 'The vote was rigged'  # a batch of ✓ checks past the sure line
    assert {x['k'] for x in d['examples']['taken out']} == {mi.key(logs)}
    later = tv.view({'since': now})
    assert 'stages' not in later and all(e['t'] >= now for e in later['events'])
    assert tv.view({'q': 'senile'})['found'] == [{'k': mi.key(logs), 'c': logs}]
    assert tv.view({'q': '#' + mi.key(logs)[:4]})['found'][0]['k'] == mi.key(logs)


def test_the_view_says_what_went_wrong_instead_of_failing(monkeypatch):
    monkeypatch.setattr(tv, 'journey', lambda ref: 1 / 0)
    assert 'ZeroDivisionError' in tv.view({'claim': 'x'})['error']


def test_tests_never_trace_into_the_real_data_folder():
    assert trace.FOLDER is None and 'maudlin-test-data' in trace.folder()  # Config.data, as conftest points it
