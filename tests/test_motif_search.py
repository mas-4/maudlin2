"""Keyword search on the motif index page (app/site/motif_search.py, app/site/static/motif-search.js): the index the
build writes, the ranking, and the script ranking the same way under node."""
import json
import os
import shutil
import subprocess

import pytest

from app.analysis import motif_index
from app.site import motif_search as ms
from app.site import page_motifs
from app.utils import Config

SCRIPT = os.path.join(Config.assets, 'motif-search.js')


class PassScreen:
    """Every claim shown as told"""
    def shown(self, claim, source=''):
        return claim

    def save(self):
        pass


def motif(mid, name, note, claims, genre='Theories', phrases=(), carrying=(), done=True):
    cs = [{'claim': c, 'source': 'shows', 'date': f'2026-10-{10 + i:02d}',
           **({'carrying': list(carrying)} if i == 0 and carrying else {})} for i, c in enumerate(claims)]
    e = {'id': mid, 'name': name, 'note': note, 'note_by': 'person', 'claims': cs, 'phrases': list(phrases),
         'facets': {'genre': genre} if genre else {}, 'first_seen': '2026-10-10'}
    if done:
        e['done'] = [motif_index.key(c) for c in claims]
    return e


def corpus() -> dict:
    entries = [
        motif('M001', 'Deep state', 'Unelected officials secretly run the government and thwart the elected leader.',
              ['The bureaucracy is sabotaging the president.', 'FBI agents are working against him from inside.'],
              carrying=['the deep state']),
        motif('M002', "They're going to steal it", 'The side in power is said to be readying to rig the coming election.',
              ['Democrats are going to steal the midterms.', 'They will cheat with mail ballots again.']),
        motif('M003', 'Rigged election', 'The election was stolen: the vote was rigged and the result hidden.',
              ['The 2020 election was stolen.', 'Machines flipped votes in Georgia.'], phrases=['rigged elections']),
        motif('M004', 'The guardrails will hold', 'The courts and the states are trusted to stop the worst.',
              ['The states run elections, so no one can steal one at scale.'], genre='Arguments'),
        motif('M005', 'Pain at the pump', 'Gas prices are blamed on whoever holds power.',
              ['Gas prices are too high because of the president.', 'Drivers pay more at the pump every week.'],
              genre='Plots'),
        motif('M006', 'State secrets', 'The government hides what it knows about a disaster.',
              ['The state is hiding the real death toll.'], genre='Plots'),
        motif('M007', 'A model guess nobody checked', 'Not verified.', ['The deep state is everywhere.'], done=False),
    ]
    return {'next': 8, 'claims': {}, 'groups': {}, 'entries': {e['id']: e for e in entries}}


@pytest.fixture
def built():
    index = corpus()
    cat = page_motifs.catalog(index, PassScreen())
    return index, cat, ms.build(cat['entries'], index)


def test_stems_join_plurals_and_verb_forms():
    assert ms.tokens("They're stealing the elections!") == ['steal', 'election']
    assert ms.tokens('rigged') == ms.tokens('rig') == ['rig']
    assert ms.tokens('stolen') == ms.tokens('steals') == ['steal']
    assert ms.tokens('Prices') == ms.tokens('price') and ms.tokens('Trump’s') == ['trump']
    assert ms.tokens('Café naïve') == ['caf', 'naiv']


def test_the_index_holds_only_the_motifs_with_pages_and_their_shown_words(built):
    _, cat, data = built
    docs = {d['i']: d for d in data['docs']}
    assert set(docs) == {e['id'] for e in cat['entries']} and 'M007' not in docs  # only what a person verified
    deep = docs['M001']
    assert deep['n'] == 'Deep state' and deep['g'] == 'Theories' and deep['k'] == 2
    assert deep['u'] in ('motif-m001.html', 'motifs.html#M001')
    assert deep['p'] == ['the deep state'] and docs['M003']['p'] == ['rigged elections']
    assert 'Machines flipped votes in Georgia.' in docs['M003']['c']


def test_long_claims_are_cut_and_only_the_latest_go_in():
    index = corpus()
    e = index['entries']['M001']
    many = [f'Claim number {n} about the bureaucracy ' + 'word ' * 80 for n in range(ms.CLAIMS_EACH + 10)]
    index['entries']['M001'] = motif('M001', e['name'], e['note'], many)
    cat = page_motifs.catalog(index, PassScreen())
    doc = next(d for d in ms.build(cat['entries'], index)['docs'] if d['i'] == 'M001')
    assert len(doc['c']) == ms.CLAIMS_EACH and all(len(c) <= ms.CLAIM_CHARS for c in doc['c'])
    assert doc['c'][0].endswith('…')


@pytest.mark.parametrize('query, first, among', [
    ('deep state', 'Deep state', None),
    ("they're stealing the election", None, {"They're going to steal it", 'Rigged election'}),
    ('stolen election', 'Rigged election', None),
    ('gas prices too high', 'Pain at the pump', None),
])
def test_visitor_queries_find_their_motifs(built, query, first, among):
    _, _, data = built
    top = ms.Search(data['docs']).top(query, 5)
    if first:
        assert top[0] == first, top
    if among:
        assert among <= set(top[:3]), top


def test_a_query_with_no_known_word_finds_nothing(built):
    assert ms.Search(built[2]['docs']).top('zebra quokka') == []


def test_the_page_writes_its_index_and_a_search_box(monkeypatch, tmp_path):
    index = corpus()
    monkeypatch.setattr(motif_index, 'load', lambda: index)
    monkeypatch.setattr(page_motifs.accusations, 'screen', lambda: PassScreen())
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    page_motifs.MotifsPage().generate()
    data = json.loads((tmp_path / ms.FILE).read_text())
    assert {d['n'] for d in data['docs']} >= {'Deep state', 'Rigged election'}
    html = (tmp_path / 'motifs.html').read_text()
    assert 'role="search"' in html and 'for="motifs-search-q"' in html and 'id="motifs-search-q"' in html
    assert f'data-index="{ms.FILE}?v=' in html and 'src="motif-search.js?v=' in html
    assert 'data-text=' not in html  # the old word filter's copy of every claim is gone


@pytest.mark.skipif(shutil.which('node') is None, reason='needs node')
def test_the_script_ranks_and_tokenizes_as_python_does(built, tmp_path):
    _, _, data = built
    queries = ['deep state', "they're stealing the election", 'stolen election', 'gas prices too high', 'state',
               'the government hides it', 'Café naïve Trump’s', 'zebra']
    (tmp_path / 'index.json').write_text(json.dumps(data))
    (tmp_path / 'queries.json').write_text(json.dumps(queries))
    js = """const M = require(process.argv[1]); const fs = require('fs');
    const d = JSON.parse(fs.readFileSync(process.argv[2])); const qs = JSON.parse(fs.readFileSync(process.argv[3]));
    const s = new M.Search(d.docs);
    console.log(JSON.stringify({top: qs.map((q) => s.top(q, 8).map((x) => x.doc.n)), tokens: qs.map(M.tokens),
                                snippet: M.snippet(d.docs.find((x) => x.n === 'Rigged election'), 'stolen election')}));"""
    out = subprocess.run(['node', '-e', js, SCRIPT, str(tmp_path / 'index.json'), str(tmp_path / 'queries.json')],
                         capture_output=True, text=True, timeout=30, check=True)
    got = json.loads(out.stdout)
    search = ms.Search(data['docs'])
    assert got['top'] == [search.top(q, 8) for q in queries]
    assert got['tokens'] == [ms.tokens(q) for q in queries]
    # the note, which has both words, with them marked
    assert got['snippet'] == 'The <mark>election</mark> was <mark>stolen</mark>: the vote was rigged and the result hidden.'
