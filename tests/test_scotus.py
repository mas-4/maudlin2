"""Supreme Court coverage (#144): reading the Court's Granted & Noted list, tying headlines to one case by a distinctive
party or by issue, and the language model's cached judgments. No network and no model: both are stubbed."""
from datetime import datetime as dt

import pytest

from app.analysis import llm, scotus as sc

GRANTED = """             SUPREME COURT OF THE UNITED STATES
                    GRANTED & NOTED LIST

24-1016    CFX   RISEANDSHINE CORP. V. PEPSICO, INC.
                 Court: USCA-2                            Granted: 6/29/26


25-170     CSX   SUNCOR ENERGY (U.S.A.) INC. V. COMMISSIONERS OF BOULDER COUNTY
                 Court: SC-Colo.                        Granted: 2/23/26
                 Argument Date: 10/5/26


25-238)1   CFX   VIRAMONTES V. COOK COUNTY
25-566)2   CFX   GRANT V. HIGGINS
                 Court: 1USCA-7; 2USCA-2                  Granted: 6/30/26
                 Argument Date: 12/2/26


25-735     CFX   JOHNSON V. UNITED STATES CONGRESS
                 Court: USCA-DC                           Granted: 6/1/26
                 Argument Date: 10/5/26

25-1017    CFX   REPUBLICAN NATIONAL COMMITTEE V. MI FAMILIA VOTA
                 Court: USCA-9                            Granted: 6/1/26
"""


@pytest.fixture
def cases():
    return sc.parse_granted(GRANTED)


def test_parse_granted(cases):
    assert [c['docket'] for c in cases] == ['24-1016', '25-170', '25-238', '25-566', '25-735', '25-1017']
    suncor = cases[1]
    assert suncor['name'] == 'Suncor Energy (U.S.A.) Inc. v. Commissioners of Boulder County'
    assert (suncor['granted'], suncor['argued']) == ('2/23/26', '10/5/26')
    assert cases[0]['argued'] is None
    # Consolidated cases share their group's dates
    assert cases[2]['argued'] == cases[3]['argued'] == '12/2/26'
    assert cases[2]['granted'] == cases[3]['granted'] == '6/30/26'


def test_term():
    assert sc.term(dt(2026, 10, 4)) == 2026
    assert sc.term(dt(2027, 6, 30)) == 2026
    assert sc.term(dt(2027, 10, 1)) == 2027


def test_match_by_distinctive_party_only(cases):
    match = sc.matcher(cases)
    assert match('Burned cattle and the SCOTUS case to make Exxon and Suncor pay')['docket'] == '25-170'
    assert match('Boulder climate case reaches the justices')['docket'] == '25-170'
    assert match('Justices weigh RNC bid on mail ballots')['docket'] == '25-1017'
    assert match('Supreme Court rules for Congress') is None  # a party too common in court news
    assert match('Speaker Johnson criticizes the Court') is None
    assert match('Suncor and PepsiCo both lose') is None  # more than one case: none


PENDING = """<table class="wikitable"><tr><th>Case</th><th>Docket no.</th><th>Question(s) presented</th>
<th>Certiorari granted</th><th>Oral argument</th></tr>
<tr><td>Suncor Energy v. Boulder County</td><td>25-170</td><td>Whether federal law precludes state-law claims over
global climate change .</td><td>Feb 2026</td><td>(October 5, 2026)</td></tr>
<tr><td>Viramontes v. Cook County Grant v. Higgins</td><td>25-238 25-566</td><td>Whether the Second Amendment guarantees
the right to possess AR-15 platform rifles .</td><td>June 2026</td><td></td></tr>
<tr><td>Republican National Committee v. Mi Familia Vota</td><td>25A1017</td><td>Whether Arizona may require proof of
citizenship to register voters.</td><td>June 2026</td><td></td></tr>
</table>"""


def test_questions_from_wikipedia_by_docket_or_party(cases):
    pending = sc.parse_pending(PENDING)
    assert pending[1]['dockets'] == ['25-238', '25-566']
    assert pending[0]['question'].endswith('global climate change.')  # spacing before punctuation tidied
    sc.add_questions(cases, pending)
    by = {c['docket']: c for c in cases}
    assert 'AR-15' in by['25-238']['question'] and by['25-238']['question'] == by['25-566']['question']
    assert 'Arizona' in by['25-1017']['question']  # a different number on Wikipedia: matched by party
    assert 'question' not in by['25-735']


@pytest.fixture
def glossed(cases, monkeypatch, tmp_path):
    sc.add_questions(cases, sc.parse_pending(PENDING))
    monkeypatch.setattr(sc, 'GLOSSES', str(tmp_path / 'glosses.json'))
    monkeypatch.setattr(llm, 'model', lambda: 'stub')
    glosses = {'Suncor': ('Boulder climate suit', ['climate change', 'Boulder', 'oil companies']),
               'Viramontes': ('Cook County AR-15 ban', ['AR-15', 'gun ban']),
               'Grant': ('AR-15 rights', ['AR-15', 'Second Amendment']),
               'Republican': ('Arizona voter citizenship proof', ['Arizona', 'voter registration', 'First Step'])}
    asked = []

    def answer(prompt, schema, max_tokens):
        asked.append(prompt)
        gloss, keywords = next(v for k, v in glosses.items() if f'case: {k}' in prompt)
        return {'gloss': gloss + '.', 'keywords': keywords}
    monkeypatch.setattr(llm, 'complete_json', answer)
    sc.add_glosses(cases)
    sc.add_glosses(cases)
    assert len(asked) == 4  # cached; no question, no gloss
    return cases


def test_glosses_and_cues(glossed):
    by = {c['docket']: c for c in glossed}
    assert by['25-170']['gloss'] == 'Boulder climate suit' and 'gloss' not in by['25-735']
    assert by['25-170']['keywords'] == ['climate change', 'Boulder', 'oil companies']
    assert sc.origin_state('SC-KY') == 'Kentucky' and sc.origin_state('SC-Colo.') == 'Colorado'
    assert sc.origin_state('USCA-9') == ''
    cue = sc.cue_sets(glossed)
    assert {'boulder', 'climat', 'colorado'} <= cue['25-170']  # gloss, question and the court it came from
    keys = sc.keyword_sets(glossed)
    assert keys['25-170']['names'] == {'boulder', 'suncor'}  # Colorado: a state, so a subject the model checks
    assert 'colorado' in keys['25-170']['subjects']
    assert {'climat', 'oil'} <= keys['25-170']['subjects']
    # Consolidated cases (one question) share their words; "First", "Second" and "Amendment" are no one's name
    assert 'ar-15' in keys['25-238']['names'] and 'ar-15' in keys['25-566']['names']
    assert not {'first', 'step', 'second', 'amend'} & (keys['25-1017']['names'] | keys['25-566']['names'])


def test_judge_ties_by_name_and_confirms_subjects(glossed, monkeypatch):
    calls = []

    def answer(prompt, schema, max_tokens):
        calls.append(prompt)
        if 'refers' in str(schema):
            return {'reason': 'r', 'refers': 'Boulder climate suit' in prompt}
        return {'reason': 'r', 'us_supreme_court': True, 'cases': ['25-1017', 'bogus'],
                'topics': ['Climate', 'law', 'climate'], 'stage': 'term preview'}
    monkeypatch.setattr(llm, 'complete_json', answer)
    cache = {}
    row = {'title': 'Climate and AR-15s top the Court docket', 'agency': 'CNN', 'country': 'United States'}
    verdict = sc.judge(row, cache, glossed)
    assert verdict['suggested'] == ['25-1017']  # unknown numbers dropped
    # AR-15 is the consolidated pair's name: tied outright. Climate is one case's subject: asked about, told it's
    # the only climate case, and confirmed. Arizona shares no word with the headline: never asked
    assert set(verdict['cases']) == {'25-238', '25-566', '25-170'}
    confirms = [c for c in calls if 'refers' in c]
    assert len(confirms) == 1 and 'the only case this term about "climate change"' in confirms[0]
    assert verdict['topics'] == ['climate']  # vague words dropped, one spelling
    assert 'Boulder climate suit' in calls[0] and 'CNN (United States)' in calls[0]
    sc.judge(row, cache, glossed)
    assert len(calls) == 2  # cached
    assert sc.judge({**row, 'title': 'Something else'}, cache, glossed, ask=False) is None


def test_coverage_cards_by_case_with_the_rest_by_topic(glossed, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, 'JUDGMENTS', str(tmp_path / 'judgments.json'))
    monkeypatch.setattr(sc, 'docket', lambda: {'term': 2026, 'source': 'u', 'cases': glossed})
    monkeypatch.setattr(sc, 'add_glosses', lambda cases: None)
    monkeypatch.setattr(sc, 'MAX_NEW_JUDGMENTS', 3)
    rows = [{'title': t, 'first': dt(2026, 10, 5, 12 - i), 'agency': a, 'bias': b, 'rated': r, 'url': 'u',
             'country': c} for i, (t, a, b, r, c) in enumerate([
                ('Justices hear Suncor climate case', 'Fox News', 2, True, 'United States'),
                ('Supreme Court weighs Boulder suit', 'CNN', -1, True, 'United States'),
                ('Justices hear Suncor climate case again', 'Fox News', 2, True, 'United States'),
                ('Supreme Court orders payment', 'NDTV', 0, False, 'India'),
                ('Alito speaks at dinner', 'NPR', -1, True, 'United States')])]
    monkeypatch.setattr(sc, 'candidates', lambda since: rows)

    def answer(prompt, schema, max_tokens):
        first = prompt.split('\n')[0]
        if 'refers' in str(schema):
            return {'reason': 'r', 'refers': True}
        return {'reason': 'r', 'us_supreme_court': 'India' not in prompt.split('\n')[1],
                'cases': [] if 'Alito' in first else ['25-170'], 'topics': ['retirement'] if 'Alito' in first
                else ['climate'], 'stage': 'argument'}
    monkeypatch.setattr(llm, 'complete_json', answer)
    out = sc.coverage(now=dt(2026, 10, 5, 13))
    assert out['total'] == 3  # only three judged this run (the cap); the rest wait for the next
    [suncor] = out['covered']
    assert suncor['docket'] == '25-170' and suncor['outlets'] == 2 and suncor['sides'] == {'right': 1, 'left': 1}
    out = sc.coverage(now=dt(2026, 10, 5, 13))
    assert out['total'] == 4  # India's court is judged and left out
    assert [h['title'] for h in out['other']['headlines']] == ['Alito speaks at dinner']
    assert out['other']['topics'] == [('retirement', 1)]


def test_nice_name():
    assert sc.nice_name('DEPARTMENT OF AIR FORCE V. PRUTEHI GUAHAN') == 'Department of Air Force v. Prutehi Guahan'
    assert sc.nice_name('DEPTARTMENT OF HOMELAND SECURITY V. D. V. D.').endswith('v. D. V. D.')
    assert sc.nice_name('HOFFMANN V. WBI ENERGY TRANSMISSION, INC.') == 'Hoffmann v. WBI Energy Transmission, Inc.'



def test_story_glosses_cache_and_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, 'STORY_GLOSSES', str(tmp_path / 'g.json'))
    monkeypatch.setattr(sc, 'MAX_STORY_GLOSSES', 1)
    monkeypatch.setattr(llm, 'model', lambda: 'stub')
    asked = []
    monkeypatch.setattr(llm, 'complete_json', lambda p, s, max_tokens: asked.append(p) or {'name': 'Pike execution.'})
    groups = [['Pike survives', 'Pike botched'], ['Alito retires', 'Alito stays']]
    assert sc.story_glosses(groups) == ['Pike execution', None]  # one new name a run here
    assert sc.story_glosses(groups) == ['Pike execution', 'Pike execution'] and len(asked) == 2


def test_paywall_badge_is_stripped():
    assert sc.PAYWALL.sub('', "This Content is Available for Slate Plus members only true Pike's Execution") == \
        "Pike's Execution"
