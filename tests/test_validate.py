"""scripts/validate.py: a label check's verdict goes straight onto the headline as hand labels."""
import importlib.util
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis import newsfilter
from app.models import Agency, Article, Base, Headline

spec = importlib.util.spec_from_file_location('validate', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'validate.py'))
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(validate.labels, 'Session', session)
    with session() as s:
        agency = Agency(name='AP', url='x', _bias=0, _credibility=0, _country=0)
        h = Headline(title='Storm hits coast', article=Article(url='u', agency=agency), event_score=-1.0,
                     loaded_score=1.0, emotion='fear', emotion_ranks='fear,sadness', scored_by='qwen3:8b rubric:x')
        s.add(h)
        s.commit()
        return session, h.id


def test_a_correction_becomes_the_headlines_hand_labels(db):
    session, hid = db
    validate.labels.apply_label({'headline_id': hid, 'model': {'mood': -1, 'spice': 1, 'feelings': ['fear', 'sadness']},
                          'mood': {'ok': False, 'should': -2}, 'spice': {'ok': True},
                          'feelings': {'ok': False, 'should': ['sadness', 'surprise']}})
    with session() as s:
        h = s.get(Headline, hid)
        assert (h.event_score, h.loaded_score, h.emotion_ranks, h.scored_by) == (-2.0, 1.0, 'sadness,surprise',
                                                                               newsfilter.HAND_JUDGE)


def test_an_incomplete_verdict_changes_nothing(db):
    session, hid = db
    with pytest.raises(ValueError):
        validate.labels.apply_label({'headline_id': hid, 'model': {'mood': -1, 'spice': 1, 'feelings': []},
                              'mood': {'ok': True}})
    with session() as s:
        assert s.get(Headline, hid).scored_by == 'qwen3:8b rubric:x'


def test_the_motif_board_regroups_moves_merges_and_unfiles(monkeypatch, tmp_path):
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    claim = lambda t: {'claim': t, 'source': 'Snopes'}  # noqa: E731
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001'], mi.key('b'): ['M002'], mi.key('c'): ['M003']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'blame shifting', 'claims': [claim('a')]},
        'M002': {'id': 'M002', 'name': 'large group', 'claims': [claim('b')]},
        'M003': {'id': 'M003', 'name': 'blame the poor', 'claims': [claim('c')]}}})
    validate.board_action({'action': 'group_add', 'name': 'the enemy within'})
    validate.board_action({'action': 'group_assign', 'id': 'M001', 'group': 'G01'})
    validate.board_action({'action': 'move', 'claim': 'b', 'source': 'M002', 'target': 'M001'})  # M002 emptied: it goes
    validate.board_action({'action': 'merge', 'source': 'M003', 'target': 'M001'})
    validate.board_action({'action': 'move_new', 'claim': 'a', 'source': 'M001', 'name': 'the crowd as threat'})
    validate.board_action({'action': 'unfile', 'claim': 'c', 'id': 'M001'})
    board = mi.board()
    assert board['groups'] == [{'id': 'G01', 'name': 'the enemy within'}]
    assert [(e['id'], e['name'], e['group'], [c['claim'] for c in e['claims']]) for e in board['entries']] == [
        ('M001', 'blame shifting', 'G01', ['b']), ('M004', 'the crowd as threat', None, ['a'])]
    validate.board_action({'action': 'also', 'claim': 'a', 'source': 'M004', 'target': 'M001'})  # kept in M004 too
    assert [len(e['claims']) for e in mi.board()['entries']] == [2, 1] and mi.load()['claims'][mi.key('a')] == ['M004', 'M001']
    # In a second group too, then out of the first: a motif can be in several
    validate.board_action({'action': 'group_add', 'name': 'archetypes'})
    validate.board_action({'action': 'group_member', 'id': 'M001', 'group': 'G02'})
    assert mi.board()['entries'][0]['groups'] == ['G01', 'G02']
    validate.board_action({'action': 'group_member', 'id': 'M001', 'group': 'G01', 'on': False})
    assert mi.board()['entries'][0]['groups'] == ['G02']
    validate.board_action({'action': 'group_assign', 'id': 'M001', 'group': 'G01'})  # this group only
    validate.board_action({'action': 'group_delete', 'group': 'G01'})
    assert mi.board()['entries'][0]['group'] is None and mi.board()['entries'][0]['groups'] == []
    with pytest.raises(ValueError):
        validate.board_action({'action': 'move', 'claim': 'b', 'source': 'M001', 'target': 'M999'})


@pytest.mark.skipif(__import__('shutil').which('node') is None, reason='needs node to parse the scripts')
def test_every_checker_pages_script_parses(monkeypatch, tmp_path):
    """An unescaped apostrophe ('won't' in a confirm) once broke the motif organizer's whole script, silently"""
    import re
    import subprocess
    from app.analysis import entities, motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 3, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': "it's one", 'claims': [{'claim': "a 'quoted' claim", 'source': 's'}]},
        'M002': {'id': 'M002', 'name': 'two', 'claims': [{'claim': 'b', 'source': 's'}]}}})
    monkeypatch.setattr(mi, 'suggestions', lambda: [('M001', 'M002', 0.9)])
    monkeypatch.setattr(entities, 'CACHE', str(tmp_path / 'e.json'))
    monkeypatch.setattr(entities, 'ALIASES', str(tmp_path / 'a.json'))
    monkeypatch.setattr(validate, 'MOTIF_VERDICTS', str(tmp_path / 'v.jsonl'))
    monkeypatch.setattr(validate.labels, 'batch', lambda n=12: [{'headline_id': 1, 'title': "It's <a> headline", 'agency': 'AP',
                                                          'mood': 0, 'spice': 1, 'feelings': ['fear'], 'url': ''}])
    monkeypatch.setattr(validate.labels, 'VERDICTS', str(tmp_path / 'verdicts.jsonl'))
    pages = {'label check': validate.labels.page(validate.render), 'motif check': validate.motif_page(),
             'names': validate.entities_page()}
    pages.update({f: validate.render(f, '/x') for f in validate.STATIC_PAGES.values()})
    scripts = [(name, js) for name, html in pages.items() for js in re.findall(r'<script>(.*?)</script>', html, re.S)]
    static = os.path.join(validate.CHECKER, 'static')
    scripts += [(f, open(os.path.join(static, f)).read()) for f in os.listdir(static) if f.endswith('.js')]
    for name, js in scripts:
        path = tmp_path / 'page.js'
        path.write_text(js)
        result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f'{name}: {result.stderr[:300]}'
    # Every page has the one shared nav, and the label check (it writes the database) no undo button
    assert all(html.count('<nav') == 1 and '/motif-map' in html and '/motif-workbench' in html for html in pages.values())
    assert 'undo-btn' not in pages['label check'] and all('undo-btn' in h for n, h in pages.items() if n != 'label check')
    assert "It&#39;s &lt;a&gt; headline" in pages['label check']  # escaped by the templates


def test_checker_serves_its_shared_scripts_and_nothing_else(monkeypatch):
    import threading
    import urllib.error
    import urllib.request
    server = validate.ThreadingHTTPServer(('127.0.0.1', 0), validate.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/checker/static/'
    try:
        with urllib.request.urlopen(base + 'drag.js') as r:
            assert r.headers['Content-Type'].startswith('text/javascript') and b'function dragZones' in r.read()
        for bad in ('../../validate.py', 'nope.js', '..%2F..%2Fvalidate.py'):
            try:
                urllib.request.urlopen(base + bad)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code == 404
    finally:
        server.shutdown()


def test_board_changes_are_logged_with_what_the_model_had_proposed(monkeypatch, tmp_path):
    """Each correction kept as a pair, the model's proposal and the person's choice, for training later"""
    import json
    import threading
    import urllib.request
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(validate, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(validate, 'CURATION_LOG', str(tmp_path / 'log.jsonl'))
    monkeypatch.setattr(validate, 'UNDO', str(tmp_path / 'undo'))  # never the real undo folder
    mi.save({'next': 3, 'claims': {mi.key('a'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Smug smirk', 'claims': [{'claim': 'a', 'source': 's'}]},
        'M002': {'id': 'M002', 'name': 'Blame shifting', 'curated': True, 'claims': []}}})
    server = validate.ThreadingHTTPServer(('127.0.0.1', 0), validate.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = json.dumps({'action': 'also', 'claim': 'a', 'source': 'M001', 'target': 'M002'}).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/motif-board', body,
                                     {'Content-Type': 'application/json'})
        urllib.request.urlopen(req).read()
    finally:
        server.shutdown()
    [entry] = [json.loads(line) for line in (tmp_path / 'log.jsonl').read_text().splitlines()]
    assert entry['page'] == 'motif board' and entry['action']['action'] == 'also'
    assert entry['before']['source']['name'] == 'Smug smirk' and entry['before']['source']['by'] == 'model'
    assert entry['before']['target']['by'] == 'person'
    assert [m['name'] for m in entry['before']['claim_motifs']] == ['Smug smirk']


def test_undo_steps_back_but_never_over_a_runs_filing(monkeypatch, tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    for k, v in {'FOLDER': tmp_path, 'CURATION_LOG': tmp_path / 'log.jsonl', 'UNDO': tmp_path / 'undo'}.items():
        monkeypatch.setattr(validate, k, str(v))
    mi.save({'next': 2, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'x', 'claims': [{'claim': 'a', 'source': 's'}]}}})
    server = validate.ThreadingHTTPServer(('127.0.0.1', 0), validate.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    post = lambda path, body=None: urllib.request.urlopen(urllib.request.Request(  # noqa: E731
        f'http://127.0.0.1:{server.server_port}{path}', json.dumps(body or {}).encode(), {'Content-Type': 'application/json'}))
    try:
        post('/motif-board', {'action': 'rename', 'id': 'M001', 'name': 'Blue Texas'})
        post('/motif-board', {'action': 'add', 'name': 'Lost golden age'})
        assert json.loads(post('/undo').read())['undid'] == 'add as “Lost golden age”'
        assert [e['name'] for e in mi.live(mi.load())] == ['Blue Texas']
        index = mi.load()  # an hourly run files something in between
        index['next'] += 1
        mi.save(index)
        with pytest.raises(urllib.error.HTTPError) as refused:
            post('/undo')
        assert refused.value.code == 409 and mi.live(mi.load())[0]['name'] == 'Blue Texas'
    finally:
        server.shutdown()


def test_the_workbench_does_every_pages_work_in_one_place(monkeypatch, tmp_path):
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(validate, 'MOTIF_VERDICTS', str(tmp_path / 'v.jsonl'))
    monkeypatch.setattr(validate, 'FOLDER', str(tmp_path))
    claim = lambda t: {'claim': t, 'source': 'narrative'}  # noqa: E731
    mi.save({'next': 4, 'claims': {mi.key('a'): ['M001'], mi.key('b'): ['M001'], mi.key('c'): ['M002']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'empty promises', 'claims': [claim('a'), claim('b')]},
        'M002': {'id': 'M002', 'name': 'rigged votes', 'claims': [claim('c')]},
        'M003': {'id': 'M003', 'name': 'stolen elections', 'claims': [], 'curated': True}}})
    state = validate.workbench_state()
    assert state['to_check'] == 3 and state['entries'][0]['stands_alone'] is False and state['not_same'] == []
    # A multi-claim drag is one batch (one undo step): both claims move into a new motif together
    validate.workbench_action({'action': 'new_with', 'name': 'liars', 'claims': [
        {'claim': 'a', 'source': 'M001', 'mode': 'move'}, {'claim': 'b', 'source': 'M001', 'mode': 'also'},
        {'claim': 'an unfiled one', 'source': '', 'src': 'fact-check', 'ref': 'u'}]})
    by = {e['id']: e for e in mi.board()['entries']}
    assert [c['claim'] for c in by['M004']['claims']] == ['a', 'b', 'an unfiled one']
    assert [c['claim'] for c in by['M001']['claims']] == ['b']
    validate.workbench_action({'action': 'batch', 'steps': [{'action': 'parent', 'id': 'M002', 'parent': 'M003'},
                                                             {'action': 'not_same', 'a': 'M001', 'b': 'M004'}]})
    assert mi.board()['entries'][1]['parents'] == ['M003'] and ['M001', 'M004'] in validate.workbench_state()['not_same']
    validate.workbench_action({'action': 'facet_remove', 'facet': 'genre', 'value': 'nothing yet'})  # none made yet: no crash
    validate.workbench_action({'action': 'facet_value', 'facet': 'genre', 'value': 'rumor'})  # the shelf's genres
    validate.workbench_action({'action': 'facet', 'id': 'M002', 'facet': 'genre', 'value': 'rumor'})
    validate.workbench_action({'action': 'facet_rename', 'facet': 'genre', 'value': 'rumor', 'to': 'whisper'})
    assert mi.load()['entries']['M002']['facets'] == {'genre': 'whisper'}
    assert 'whisper' in mi.facet_values()['genre'] and 'rumor' not in mi.facet_values()['genre']
    validate.workbench_action({'action': 'facet_remove', 'facet': 'genre', 'value': 'whisper'})
    assert 'facets' not in mi.load()['entries']['M002'] and 'whisper' not in mi.facet_values()['genre']
    validate.workbench_action({'action': 'group_new', 'name': 'Archetypes', 'id': 'M002'})  # the map's ＋ new group
    gid = next(g['id'] for g in mi.board()['groups'] if g['name'] == 'Archetypes')
    assert mi.groups_of(mi.load()['entries']['M002']) == [gid]
    validate.workbench_action({'action': 'group_new', 'name': 'Family', 'ids': ['M001', 'M003', 'nope']})  # a 💡 new group
    validate.workbench_action({'action': 'new_with', 'name': 'Proposed one', 'note': 'Posts say a thing.', 'genre': 'Plots',
                               'claims': [{'claim': 'a fresh claim', 'src': 'narrative'}]})  # a 💡 proposed motif
    made = next(e for e in mi.live(mi.load()) if e['name'] == 'Proposed one')
    assert (made['note'], mi.genre_of(made), [c['claim'] for c in made['claims']]) == ('Posts say a thing.', 'Plots', ['a fresh claim'])
    fam = next(g['id'] for g in mi.board()['groups'] if g['name'] == 'Family')
    assert [e['id'] for e in mi.live(mi.load()) if fam in mi.groups_of(e)] == ['M001', 'M003']
    validate.workbench_action({'action': 'check', 'claim': 'c', 'id': 'M002', 'answer': 'yes'})
    assert '"answer": "yes"' in open(tmp_path / 'v.jsonl').read()
    for bad in ({'action': 'batch', 'steps': [{'action': 'batch', 'steps': []}]}, {'action': 'check', 'claim': 'c', 'id': 'M002', 'answer': 'maybe'},
                {'action': 'not_same', 'a': 'M001', 'b': 'M001'}, {'action': 'new_with', 'name': '', 'claims': []}):
        with pytest.raises(ValueError):
            validate.workbench_action(bad)
    # A batch that fails midway says which steps ran, so they're logged (Oct 9: a 'no motif' that emptied a motif ran,
    # the delete after it failed, and the verdict never reached the log)
    first = {'action': 'facet', 'id': 'M002', 'facet': 'genre', 'value': 'Plots'}
    with pytest.raises(ValueError) as failed:
        validate.workbench_action({'action': 'batch', 'steps': [first, {'action': 'not_same', 'a': 'M001', 'b': 'M001'}]})
    assert failed.value.done == [first] and mi.genre_of(mi.load()['entries']['M002']) == 'Plots'
    # Later steps of a batch name the motifs earlier ones made as "$1", "$2"…, and the batch keeps the real ids
    made = {'action': 'batch', 'steps': [{'action': 'new_with', 'name': 'Seedling', 'claims': [{'claim': 'z', 'src': 'x'}]},
                                         {'action': 'facet', 'id': '$1', 'facet': 'genre', 'value': 'Beliefs'}]}
    validate.workbench_action(made)
    seed = next(e for e in mi.live(mi.load()) if e['name'] == 'Seedling')
    assert mi.genre_of(seed) == 'Beliefs' and made['steps'][1]['id'] == seed['id']
    with pytest.raises(ValueError):
        validate.workbench_action({'action': 'batch', 'steps': [{'action': 'facet', 'id': '$1', 'facet': 'genre', 'value': 'x'}]})


def test_a_claim_told_on_the_shows_says_which_shows_and_episodes(monkeypatch):
    """Oct 8: a claim from the shows showed 'fact-check' and nothing else in the workbench's 'where it came from'"""
    from app.analysis import focus_group, show_claims
    monkeypatch.setattr(show_claims, 'kept_retold', lambda: [{'claim': 'He says he is a capitalist', 'told': [
        {'show': 'Ruthless', 'url': 'gid://ep/1', 'at': 845, 'speaker': 'clip', 'claim': 'He is a capitalist', 'quote': 'I am a capitalist'},
        {'show': 'Fox News Rundown', 'url': 'https://fox.example/ep2', 'at': 0, 'speaker': 'host', 'claim': 'He says he is a capitalist', 'quote': 'a capitalist'}]}])
    monkeypatch.setattr(show_claims, 'load', lambda: {
        'gid://ep/1': {'show': 'Ruthless', 'lean': 'right', 'title': 'Deleted tweets', 'date': '2026-10-07', 'claims': []},
        'https://fox.example/ep2': {'show': 'Fox News Rundown', 'lean': 'right', 'title': 'MacCallum', 'date': '2026-10-06', 'claims': []}})
    monkeypatch.setattr(focus_group, 'context', lambda url, quote: {'before': 'so ', 'quote': quote, 'after': '.'})
    told = validate.show_tellings({'He says he is a capitalist'})
    assert [t['show'] for t in told] == ['Ruthless', 'Fox News Rundown']  # newest first
    assert told[0]['url'] is None and told[1]['url'] == 'https://fox.example/ep2'  # a feed's guid isn't a link
    assert told[0]['title'] == 'Deleted tweets' and told[0]['at'] == 845 and told[0]['context']['quote'] == 'I am a capitalist'


def test_todays_set_is_picked_once_a_day_runs_out_as_decided_and_more_can_be_asked_for(monkeypatch, tmp_path):
    from app.analysis import filing_confidence as fc, motif_index as mi, motif_proposals as mp
    c = lambda t, **k: {'claim': t, 'source': 'narrative', **k}  # noqa: E731
    index = {'entries': {
        'M1': {'id': 'M1', 'name': 'Mine', 'done': ['x'], 'curated': True,
               'claims': [c('torn a', fit=0.52), c('torn b', fit=0.30), c('sure', fit=0.95), c('checked', fit=0.5, checked='yes'),
                          c('doubted', fit=0.2, checked='yes')]},
        'M2': {'id': 'M2', 'name': 'Also mine', 'done': ['x'], 'curated': True, 'claims': [c('torn a', fit=0.45)]},
        'M3': {'id': 'M3', 'name': 'Made by the model', 'claims': [c('m'), c('n')]}}}
    monkeypatch.setattr(mi, 'load', lambda: index)
    monkeypatch.setattr(validate, 'TODAY_FILE', str(tmp_path / 'today.json'))
    monkeypatch.setattr(validate, 'TODAY', {'doubted': 4, 'torn': 1, 'new motifs': 3, 'proposals': 3})
    monkeypatch.setattr(validate, 'second_look', lambda: [{'claim': 'doubted', 'id': 'M1', 'fit': 0.2, 'better': [{'id': 'M2'}]}])
    monkeypatch.setattr(fc, 'better', lambda ix, claim: [])
    props = [{'id': 'p1', 'kind': 'relate', 'args': {'a': 'M1', 'b': 'M2'}, 'fit': 0.9},
             {'id': 'p2', 'kind': 'new_motif', 'args': {'name': 'New', 'note': '', 'genre': None, 'claims': []}}]
    monkeypatch.setattr(mp, 'open_proposals', lambda: props)
    got = validate.todays_decisions()
    assert [x['key'] for x in got['items']] == ['d|doubted|M1', 't|torn a|M1', 'n|M3', 'p|p2', 'p|p1']
    assert (got['picked'], got['done']) == (5, 0)
    index['entries']['M1']['claims'][0]['checked'] = 'yes'  # the torn one decided
    index['entries']['M1']['claims'][4]['rechecked'] = True  # the doubted one kept
    props.pop(0)
    got = validate.todays_decisions()
    assert [x['key'] for x in got['items']] == ['n|M3', 'p|p2'] and got['done'] == 3  # not filled up again
    more = validate.todays_decisions(more=True)
    assert 't|torn a|M2' in [x['key'] for x in more['items']] and more['picked'] == 6  # the claim's other filing, torn too


def test_the_check_list_goes_least_sure_first(monkeypatch):
    from app.analysis import filing_confidence as fc, motif_index as mi
    items = [{'claim': c, 'id': 'M1', 'source': ''} for c in ('sure', 'torn', 'unlikely', 'unscored')]
    monkeypatch.setattr(mi, 'to_check', lambda: [dict(x) for x in items])
    monkeypatch.setattr(mi, 'load', lambda: {'entries': {}})
    monkeypatch.setattr(validate, 'filing_fits', lambda: {f'{mi.key(c)}|M1': f for c, f in
                                                          (('sure', 0.97), ('torn', 0.52), ('unlikely', 0.1))})
    monkeypatch.setattr(fc, 'tested_sources', lambda index: set())
    monkeypatch.setattr(fc, 'can_be_sure', lambda *a: True)
    assert [x['claim'] for x in validate.check_queue()] == ['torn', 'unlikely', 'sure', 'unscored']


def test_the_service_stops_for_new_code(monkeypatch):
    import subprocess
    import threading
    heads = iter(['aaa', 'aaa', 'bbb'])
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: type('R', (), {'stdout': next(heads)})())
    stopped = threading.Event()
    validate.follow_code(type('S', (), {'shutdown': lambda self: stopped.set()})(), every=0)
    assert stopped.wait(5)


def test_each_claim_waits_once_with_why(monkeypatch):
    monkeypatch.setattr(validate, 'check_queue', lambda: [
        {'claim': 'a', 'id': 'M1', 'fit': 0.4, 'source': 'shows', 'can_be_sure': True},
        {'claim': 'a', 'id': 'M2', 'fit': 0.9, 'source': 'shows', 'can_be_sure': False},
        {'claim': 'b', 'id': 'M1', 'fit': None, 'source': 'narrative'}])
    monkeypatch.setattr(validate, 'second_look', lambda: [
        {'claim': 'a', 'id': 'M3', 'fit': 0.2, 'source': 'shows', 'better': [{'id': 'M4', 'fit': 0.7}]},
        {'claim': 'c', 'id': 'M5', 'fit': 0.1, 'source': 'shows', 'better': []}])
    q = validate.judge_queue()
    assert [x['claim'] for x in q] == ['a', 'b', 'c']  # each once: the unchecked in their order, then the doubted
    a = q[0]
    assert [(r['kind'], r['id']) for r in a['reasons']] == [('unchecked', 'M1'), ('unchecked', 'M2'), ('doubted', 'M3')]
    assert a['fits'] == {'M1': 0.4, 'M2': 0.9, 'M3': 0.2} and a['unsure'] == ['M2'] and a['better'][0]['id'] == 'M4'


def test_the_workbench_marks_a_motif_as_a_watch_list(monkeypatch, tmp_path):
    """Straight news (Oct 12): a sink whose claims are watched and filed again, marked by the person"""
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 2, 'claims': {mi.key('a'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Straight news', 'claims': [{'claim': 'a', 'source': 'narrative'}]}}})
    assert validate.workbench_state()['entries'][0]['watch'] is False
    validate.workbench_action({'action': 'watch', 'id': 'M001', 'on': True})
    assert mi.watched(mi.load()) == {'M001'} and validate.workbench_state()['entries'][0]['watch'] is True
    validate.workbench_action({'action': 'watch', 'id': 'M001', 'on': False})
    assert mi.watched(mi.load()) == set()


def test_a_filing_confirmed_lately_or_only_mildly_doubted_isnt_looked_at_again(monkeypatch):
    from app.analysis import curation_db
    now = validate.dt.now().isoformat(timespec='seconds')
    monkeypatch.setattr(curation_db, 'actions', lambda: [
        {'at': now, 'by': None, 'before': None, 'action': {'action': 'batch', 'steps': [
            {'action': 'check', 'claim': 'a firing squad is kinder', 'id': 'M459', 'answer': 'yes'}]}},
        {'at': '2026-08-01T00:00:00', 'by': None, 'before': None,
         'action': {'action': 'check', 'claim': 'old one', 'id': 'M459', 'answer': 'yes'}}])
    recent = validate.recently_confirmed()
    e = {'id': 'M459', 'done': []}
    filing = lambda t, fit: {'claim': t, 'checked': 'yes', 'fit': fit}  # noqa: E731
    assert not validate.doubted(e, filing('a firing squad is kinder', 0.1), set(), recent)  # confirmed today
    assert validate.doubted(e, filing('old one', 0.1), set(), recent)  # confirmed long ago, strongly doubted
    assert not validate.doubted(e, filing('old one', 0.42), set(), recent)  # only mildly


def test_a_claim_on_hold_leaves_the_queues_for_the_held_tab(monkeypatch, tmp_path):
    """⏸ hold (Oct 18): a claim kept aside to look at later, its filings still waiting, out of the claims to judge;
    it stays held in new words or folded into another claim, and comes back when taken off hold"""
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 2, 'claims': {mi.key('a'): ['M001'], mi.key('b'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Rigged', 'claims': [{'claim': 'a', 'source': 'narrative'},
                                                            {'claim': 'b', 'source': 'narrative'}]}}})
    monkeypatch.setattr(validate, 'check_queue', lambda: [{'claim': c, 'id': 'M001', 'fit': 0.5, 'source': 'narrative'}
                                                          for c in ('a', 'b')])
    monkeypatch.setattr(validate, 'second_look', list)
    validate.workbench_action({'action': 'hold', 'claim': 'a'})
    assert [x['claim'] for x in validate.judge_queue()] == ['b']
    assert validate.workbench_state()['held'] == ['a']
    assert [(x['claim'], x['waiting']) for x in validate.workbench_queue('held')] == [('a', 1)]
    mi.correct_claim('a', 'a, reworded')
    assert validate.workbench_state()['held'] == ['a, reworded']
    mi.same_claim('a, reworded', 'b')
    assert validate.workbench_state()['held'] == ['b']
    validate.workbench_action({'action': 'unhold', 'claim': 'b'})
    assert validate.workbench_state()['held'] == [] and validate.workbench_queue('held') == []
    with pytest.raises(ValueError):
        validate.workbench_action({'action': 'hold', 'claim': 'never filed'})


def test_the_sure_tally_counts_unticks_take_outs_and_holds_as_needing_the_person(monkeypatch, tmp_path):
    """Oct 18: the held-out test counts only filings passed or taken out; the tally counts every sure claim"""
    from app.analysis import curation_db, motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 2, 'claims': {mi.key('d'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Rigged', 'claims': [{'claim': 'd', 'source': 'narrative', 'fit': 0.99}]}}})
    monkeypatch.setattr(validate, 'index_sure_at', lambda: 0.8)
    day = validate.dt.now().strftime('%Y-%m-%d')
    fits = {f'{mi.key(c)}|M001': f for c, f in (('a', 0.95), ('b', 0.9), ('c', 0.85), ('e', 0.5))}
    before = {'fits': fits, 'sure_at': 0.8}
    rows = [
        {'at': f'{day}T10:00:00', 'action': {'action': 'batch', 'quick': 'sure', 'unticked': ['b|M001'], 'steps': [
            {'action': 'check', 'claim': 'a', 'id': 'M001', 'answer': 'yes'},
            {'action': 'check', 'claim': 'e', 'id': 'M001', 'answer': 'yes'}]}, 'before': before},  # e: not sure
        {'at': f'{day}T10:05:00', 'action': {'action': 'unfile', 'claim': 'c', 'id': 'M001'}, 'before': before},
        {'at': f'{day}T10:06:00', 'action': {'action': 'hold', 'claim': 'd'}, 'before': {}},  # before the marker: sure now
        {'at': f'{day}T10:07:00', 'action': {'action': 'hold', 'claim': 'x', 'from': 'judge'}, 'before': {}},
        {'at': f'{day}T10:08:00', 'action': {'action': 'check', 'claim': 'a', 'id': 'M001', 'answer': 'yes'},
         'before': before, 'by': 'claude'}]
    monkeypatch.setattr(curation_db, 'actions', lambda: rows)
    assert validate.sure_tally() == [{'day': day, 'clean': 1, 'needed': 3}]


def test_pace_counts_arrivals_and_judged_claims_and_the_steady_target(monkeypatch, tmp_path):
    """📈 pace (Oct 18): arrivals from the shortlist log (a claim's first filing), claims judged from the curation log,
    the steady target the median of the last week's full days (a one-off refile doesn't set it)"""
    from datetime import timedelta
    from app.analysis import filing_confidence as fc, motif_index as mi
    now = validate.dt.now()
    day = lambda n: (now - timedelta(days=n)).strftime('%Y-%m-%dT10:00:00')  # noqa: E731
    log = tmp_path / 'shortlist.jsonl'
    rows = [{'at': day(n), 'key': f'{n}-{i}', 'picked': ['M1']} for n, count in ((3, 10), (2, 500), (1, 20)) for i in range(count)]
    rows += [{'at': day(1), 'key': '1-0', 'picked': ['M2']}, {'at': day(1), 'key': 'x', 'picked': [], 'new': None}]
    log.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr('app.analysis.motif_filing.SHORTLIST_LOG', str(log))
    # a claim counts once it reached the index (or a decision): 'leak' never did, like Rip Van Winkle's 1896 filings on Oct 15
    rows.append({'at': day(1), 'key': 'leak', 'picked': ['M1']})
    log.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr(mi, 'load', lambda: {'claims': {r['key']: ['M1'] for r in rows if r['key'] != 'leak'}, 'entries': {}})
    monkeypatch.setattr(fc, 'log_rows', lambda: [
        {'at': day(0), 'action': {'action': 'batch', 'steps': [{'action': 'check', 'claim': 'a', 'id': 'M1', 'answer': 'yes'},
                                                             {'action': 'unfile', 'claim': 'a', 'id': 'M2'},
                                                             {'action': 'check', 'claim': 'b', 'id': 'M1', 'answer': 'yes'}]}},
        {'at': day(0), 'action': {'action': 'hold', 'claim': 'c'}}])
    monkeypatch.setattr(validate, 'judge_queue', lambda: [{}] * 28)
    p = validate.pace()
    assert [d['arrived'] for d in p['days'][-4:]] == [10, 500, 20, 0] and p['days'][0]['arrived'] is None
    assert p['today'] == 2 and p['steady'] == 20 and p['waiting'] == 28 and p['clear_in_14'] == 22


def test_a_show_claim_filed_in_other_words_still_shows_its_tellings(monkeypatch):
    """Oct 20: a claim filed in reworded form, its group gone from the last run, showed no origin"""
    import numpy as np
    import app.narratives
    from app.analysis import show_claims
    store = {'u1': {'show': 'Surrounded', 'claims': [{'claim': 'The left should adopt a fighter identity.', 'quote': 'q'},
                                                     {'claim': 'Gas is cheap.', 'quote': 'q'}]}}
    monkeypatch.setattr(show_claims, 'load', lambda: store)
    monkeypatch.setattr(show_claims, 'kept_retold', list)
    vecs = {'The left should adopt the identity of a fighter.': [1, 0], 'The left should adopt a fighter identity.': [0.9, 0.1],
            'Gas is cheap.': [0, 1]}
    monkeypatch.setattr(app.narratives, 'embed', lambda texts: np.array([vecs[t] for t in texts], dtype=float) /
                        np.linalg.norm(np.array([vecs[t] for t in texts], dtype=float), axis=1, keepdims=True))
    got = validate.show_tellings({'The left should adopt the identity of a fighter.'})
    assert [t['claim'] for t in got] == ['The left should adopt a fighter identity.']


def test_a_side_split_from_a_dispute_finds_the_disputes_report(monkeypatch, tmp_path):
    """Oct 20: a side split out of a dispute claim showed "its report is gone": the report names the dispute"""
    import app.narratives
    from app.analysis import motif_index as mi
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    dispute, side = 'Arguments exist over whether X failed.', 'X brought the country back.'
    mi.save({'next': 2, 'claims': {mi.key(side): ['M001']}, 'entries': {'M001': {'id': 'M001', 'name': 'Recovery', 'claims': [
        {'claim': side, 'source': 'narrative', 'ref': '2026-10-15T04:55', 'split_from': dispute}]}}})
    monkeypatch.setattr(app.narratives, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(app.narratives, 'posts_of', lambda keys: [])
    (tmp_path / 'report-2026-10-15-0455.json').write_text(json.dumps({'made': 'm', 'found': [
        {'authors': 6, 'posts': 6, 'label': {'narrative': dispute}}]}))
    d = validate.claim_detail(side)
    assert d['kind'] == 'folklore' and d['people'] == 6 and d['split_from'] == dispute


def test_the_react_app_is_served_and_nothing_outside_it():
    """Oct 21: the checker's React app (scripts/checker/ui) at /ui/: its built files, its page for every other /ui/ path"""
    import os
    if not os.path.isfile(os.path.join(validate.UI, 'index.html')):
        return  # not built in this checkout
    assert validate.ui_file('/ui/') == (os.path.join(validate.UI, 'index.html'), False)
    assert validate.ui_file('/ui/workbench/judge')[0].endswith('index.html')
    built = next(f for f in os.listdir(os.path.join(validate.UI, 'assets')) if f.endswith('.js'))
    assert validate.ui_file(f'/ui/assets/{built}') == (os.path.realpath(os.path.join(validate.UI, 'assets', built)), True)
    assert validate.ui_file('/ui/assets/../../../validate.py') is None and validate.ui_file('/ui/assets/nope.js') is None
