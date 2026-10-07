"""The public motif map (app/site/page_motif_map.py): verified motifs only, with the claims a person saw in them, put
through the accusations screen; links only between motifs on the map; groups of two or more."""
import json

from bs4 import BeautifulSoup

from app.analysis import accusations, motif_index
from app.site import page_motif_map
from app.utils.config import Config


def entry(eid, name, claims, done=True, **more):
    cs = [{'claim': c, 'source': 'narrative', 'ref': '2026-10-06T04:39', 'date': '2026-10-06'} for c in claims]
    return {'id': eid, 'name': name, 'claims': cs, 'first_seen': '2026-10-01',
            **({'done': [motif_index.key(c) for c in claims]} if done else {}), **more}


INDEX = {'next': 9, 'claims': {}, 'related': [['M2', 'M3']],
         'groups': {'G01': {'id': 'G01', 'name': 'Archetypes'}, 'G02': {'id': 'G02', 'name': 'Aardvarks'}},
         'entries': {
             'M1': entry('M1', 'Corrupt official', ['The mayor takes bribes.', 'Jacob Geller is a rapist.'], groups=['G01']),
             'M2': entry('M2', 'Bought politician', ['The mayor takes bribes.'], parents=['M1'], groups=['G01']),
             'M3': entry('M3', 'Secret donor', ['A donor pays the senator.'], facets={'genre': 'scandal'}),
             'M4': entry('M4', 'Unchecked motif', ['Not seen by a person.'], done=False, parents=['M1'], groups=['G02'],
                         facets={'genre': 'legend'}),
         }}


def screen(tmp_path, monkeypatch):
    def reader(claim):
        return {'accused': [{'names': ['Jacob Geller'], 'who': 'a YouTuber', 'well_known': False, 'crime': 'rape'}]} \
            if 'Geller' in claim else {'accused': []}
    monkeypatch.setattr(accusations, 'CACHE', str(tmp_path / 'accusations.json'))
    s = accusations.Screen(reader=reader)
    s.named = {'Jacob Geller': 0}
    return s


def test_graph_shows_verified_motifs_screened_claims_and_their_links(tmp_path, monkeypatch):
    g = page_motif_map.graph(INDEX, screen(tmp_path, monkeypatch))
    by = {m['id']: m for m in g['motifs']}
    assert set(by) == {'M1', 'M2', 'M3'}  # M4 isn't verified
    assert 'A YouTuber is a rapist.' in [c['claim'] for c in by['M1']['claims']]
    assert not any('Geller' in json.dumps(m) for m in g['motifs'])
    kinds = {(l['source'], l['target'], l['kind']) for l in g['links']}
    assert ('M2', 'M1', 'kind') in kinds and ('M2', 'M3', 'related') in kinds
    assert not any(l['kind'] == 'shared' and {l['source'], l['target']} == {'M1', 'M2'} for l in g['links'])  # already a kind
    assert (by['M1']['broad'], by['M1']['sub'], by['M2']['broad'], by['M2']['sub']) == (True, False, False, True)
    assert not by['M3']['broad'] and not by['M3']['sub']
    # groups and genres keep their place among all of them A to Z (their color, as on the checker), shown if used here
    assert [(x['name'], x['k']) for x in g['groups']] == [('Archetypes', 1)]
    assert g['genres'] == [{'name': 'scandal', 'k': 1, 'size': 1}] and 'legend' not in json.dumps(g)  # unchecked only
    assert by['M3']['genre'] == 'scandal' and by['M1']['genre'] == ''


def test_page_renders_its_data(tmp_path, monkeypatch):
    s, real = screen(tmp_path, monkeypatch), page_motif_map.graph
    monkeypatch.setattr(page_motif_map, 'graph', lambda: real(INDEX, s))
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    page_motif_map.MotifMapPage().generate()
    soup = BeautifulSoup((tmp_path / 'motif-map.html').read_text(), 'html.parser')
    data = json.loads(soup.select_one('#mm-data').string)
    assert len(data['motifs']) == 3 and soup.select('.mm-group')[0].get_text(strip=True).startswith('📁 Archetypes')

