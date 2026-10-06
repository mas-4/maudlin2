"""The motif index, exported: verified motifs only by default, every format readable."""
import csv
import io
import json

import pytest

from app.analysis import motif_export as x
from app.analysis import motif_index as mi


def claim(text, **kw):
    return {'claim': text, 'source': 'narrative', 'side': 'right', 'date': '2026-10-05', **kw}


@pytest.fixture
def index():
    told = claim('The "deep state" hid it')
    late = claim('A claim filed after the motif was verified')
    return {'next': 4, 'claims': {}, 'not_same': [], 'related': [['M001', 'M003']], 'corrections': {},
            'groups': {'G01': {'id': 'G01', 'name': 'Secrets'}},
            'entries': {
                'M001': {'id': 'M001', 'name': 'Hidden hand', 'note': 'Someone powerful pulls the strings.',
                         'note_by': 'person', 'group': 'G01', 'facets': {'genre': 'conspiracy theory'},
                         'claims': [{**told, 'variants': [{'claim': 'The deep state buried it'}]}, late],
                         'done': [mi.key(told['claim'])]},
                'M002': {'id': 'M002', 'name': 'Cover-up', 'parents': ['M001'], 'note': 'drafted', 'note_by': 'model',
                         'claims': [claim('They covered it up')], 'done': [mi.key('They covered it up')]},
                'M003': {'id': 'M003', 'name': 'Unchecked', 'claims': [claim('Not looked at yet')]},
                'M004': {'id': 'M004', 'name': 'Gone', 'merged_into': 'M001', 'claims': [], 'done': []}}}


def test_verified_shows_what_the_site_shows(index):
    found = x.motifs('verified', index)
    assert [m['id'] for m in found] == ['M002', 'M001']  # by name; unverified and merged motifs left out
    m2, m1 = found
    assert [c['claim'] for c in m1['claims']] == ['The "deep state" hid it']  # not the claim filed since
    assert m1['claims'][0]['also_told'] == ['The deep state buried it']
    assert (m1['groups'], m1['genre'], m1['related']) == (['Secrets'], 'conspiracy theory', [])  # M003 isn't verified
    assert m2['note'] == '' and m2['parents'] == ['M001']  # a model's draft note isn't shown


def test_all_has_every_live_motif_and_marks_drafts(index):
    found = {m['id']: m for m in x.motifs('all', index)}
    assert sorted(found) == ['M001', 'M002', 'M003']
    assert found['M002']['note_is_draft'] and found['M003']['verified'] is False
    assert len(found['M001']['claims']) == 2 and found['M001']['related'] == ['M003']


def test_every_format_reads_back(index, monkeypatch):
    monkeypatch.setattr(mi, 'load', lambda: index)
    data = json.loads(x.export('json')[0])
    assert [m['name'] for m in data['motifs']] == ['Cover-up', 'Hidden hand']
    rows = list(csv.DictReader(io.StringIO(x.export('csv')[0])))
    assert [r['motif'] for r in rows] == ['M002', 'M001'] and rows[1]['also_told'] == 'The deep state buried it'
    md, media, name = x.export('md', 'all')
    assert '## Secrets' in md and '### Unchecked (M003)' in md and 'not yet verified' in md and name.endswith('.md')
    ttl = x.export('ttl')[0]
    assert 'bnd:M002 a skos:Concept' in ttl and 'skos:broader bnd:M001' in ttl
    assert r'skos:example "The \"deep state\" hid it"@en' in ttl  # quotes escaped
    assert 'skos:hasTopConcept bnd:M001 .' in ttl


def test_bad_format_or_scope(index):
    with pytest.raises(ValueError):
        x.export('xml')
    with pytest.raises(ValueError):
        x.motifs('some', index)
