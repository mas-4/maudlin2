"""scripts/validate.py: a label check's verdict goes straight onto the headline as hand labels."""
import importlib.util
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
    monkeypatch.setattr(validate, 'Session', session)
    with session() as s:
        agency = Agency(name='AP', url='x', _bias=0, _credibility=0, _country=0)
        h = Headline(title='Storm hits coast', article=Article(url='u', agency=agency), event_score=-1.0,
                     loaded_score=1.0, emotion='fear', emotion_ranks='fear,sadness', scored_by='qwen3:8b rubric:x')
        s.add(h)
        s.commit()
        return session, h.id


def test_a_correction_becomes_the_headlines_hand_labels(db):
    session, hid = db
    validate.apply_label({'headline_id': hid, 'model': {'mood': -1, 'spice': 1, 'feelings': ['fear', 'sadness']},
                          'mood': {'ok': False, 'should': -2}, 'spice': {'ok': True},
                          'feelings': {'ok': False, 'should': ['sadness', 'surprise']}})
    with session() as s:
        h = s.get(Headline, hid)
        assert (h.event_score, h.loaded_score, h.emotion_ranks, h.scored_by) == (-2.0, 1.0, 'sadness,surprise',
                                                                               newsfilter.HAND_JUDGE)


def test_an_incomplete_verdict_changes_nothing(db):
    session, hid = db
    with pytest.raises(ValueError):
        validate.apply_label({'headline_id': hid, 'model': {'mood': -1, 'spice': 1, 'feelings': []},
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
    monkeypatch.setattr(validate, 'batch', lambda n=12: [{'headline_id': 1, 'title': "It's <a> headline", 'agency': 'AP',
                                                          'mood': 0, 'spice': 1, 'feelings': ['fear'], 'url': ''}])
    monkeypatch.setattr(validate, 'VERDICTS', str(tmp_path / 'verdicts.jsonl'))
    pages = {'label check': validate.page(), 'motif check': validate.motif_page(),
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
    fam = next(g['id'] for g in mi.board()['groups'] if g['name'] == 'Family')
    assert [e['id'] for e in mi.live(mi.load()) if fam in mi.groups_of(e)] == ['M001', 'M003']
    validate.workbench_action({'action': 'check', 'claim': 'c', 'id': 'M002', 'answer': 'yes'})
    assert '"answer": "yes"' in open(tmp_path / 'v.jsonl').read()
    for bad in ({'action': 'batch', 'steps': [{'action': 'batch', 'steps': []}]}, {'action': 'check', 'claim': 'c', 'id': 'M002', 'answer': 'maybe'},
                {'action': 'not_same', 'a': 'M001', 'b': 'M001'}, {'action': 'new_with', 'name': '', 'claims': []}):
        with pytest.raises(ValueError):
            validate.workbench_action(bad)


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
