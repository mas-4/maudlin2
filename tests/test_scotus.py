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


def test_issue_only_headlines_join_the_case_the_model_picks(monkeypatch, cases):
    asked = []

    def answer(prompt, schema, max_tokens):
        asked.append(prompt)
        assert schema['properties']['case']['enum'] == ['25-170', 'none']  # only cases the press has named
        assert 'Supreme Court hears Suncor climate case' in prompt  # the case's own headlines describe it
        return {'reason': 'r', 'case': '25-170' if 'oil' in prompt.split('Supreme Court cases')[0] else 'none'}
    monkeypatch.setattr(llm, 'complete_json', answer)
    monkeypatch.setattr(llm, 'model', lambda: 'stub')
    by_case = {'25-170': [{'title': 'Supreme Court hears Suncor climate case', 'first': dt(2026, 10, 5),
                           'issue': 'climate suit'}], '25-1017': []}
    unnamed = [{'title': 'Big oil climate suits reach the Court', 'issue': 'climate suits', 'stage': 'argument'},
               {'title': 'Justices take church zoning case', 'issue': 'church zoning', 'stage': 'case taken'},
               {'title': 'Guns, climate, immigration top the docket', 'issue': 'docket', 'stage': 'term preview'},
               {'title': 'Alito speaks', 'issue': '', 'stage': 'the justices'}]
    cache = {}
    assert sc.by_issue(unnamed, by_case, cases, cache) == ['25-170', None, None, None]
    assert len(asked) == 2  # term previews and headlines with no case aren't asked
    assert sc.by_issue(unnamed, by_case, cases, cache) == ['25-170', None, None, None]
    assert len(asked) == 2  # cached
    assert sc.by_issue(unnamed, {'25-170': []}, cases, {}) == [None] * 4  # nothing named yet: nothing to pick


def test_judge_caches_and_never_saves_a_missing_answer(monkeypatch):
    calls = []

    def answer(prompt, schema, max_tokens):
        calls.append(prompt)
        return None if 'nothing' in prompt else {'reason': 'r', 'us_supreme_court': True, 'case': 'x',
                                                 'stage': 'ruling'}
    monkeypatch.setattr(llm, 'complete_json', answer)
    monkeypatch.setattr(llm, 'model', lambda: 'stub')
    cache = {}
    assert sc.judge('Supreme Court rules', cache)['stage'] == 'ruling'
    assert sc.judge('Supreme Court rules', cache)['stage'] == 'ruling'
    assert len(calls) == 1
    assert sc.judge('nothing back', cache) is None and len(cache) == 1
    assert sc.judge('Supreme Court rules again', cache, ask=False) is None


def test_coverage_groups_counts_sides_and_bounds_new_judgments(monkeypatch, tmp_path, cases):
    monkeypatch.setattr(sc, 'JUDGMENTS', str(tmp_path / 'judgments.json'))
    monkeypatch.setattr(sc, 'docket', lambda: {'term': 2026, 'source': 'u', 'cases': cases})
    monkeypatch.setattr(sc, 'CASES', str(tmp_path / 'cases.json'))
    monkeypatch.setattr(sc, 'by_issue', lambda unnamed, by_case, cases, cache: [None] * len(unnamed))
    monkeypatch.setattr(sc, 'MAX_NEW_JUDGMENTS', 3)
    rows = [{'title': t, 'first': dt(2026, 10, 5, 12 - i), 'agency': a, 'bias': b, 'rated': r, 'url': 'u'}
            for i, (t, a, b, r) in enumerate([
                ('Justices hear Suncor climate case', 'Fox News', 2, True),
                ('Supreme Court weighs Boulder suit', 'CNN', -1, True),
                ('Justices hear Suncor climate case again', 'Fox News', 2, True),
                ('India Supreme Court orders payment', 'NDTV', 0, False),
                ('Alito speaks at dinner', 'NPR', -1, True)])]
    monkeypatch.setattr(sc, 'candidates', lambda since: rows)
    monkeypatch.setattr(llm, 'model', lambda: 'stub')
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, schema, max_tokens: {
        'reason': 'r', 'us_supreme_court': 'India' not in prompt, 'case': '', 'stage': 'argument'})
    out = sc.coverage(now=dt(2026, 10, 5, 13))
    # Only the first three were judged this run (the cap); the rest wait for the next
    assert out['total'] == 3
    [suncor] = out['covered']
    assert suncor['docket'] == '25-170'
    assert suncor['outlets'] == 2 and suncor['sides'] == {'right': 1, 'left': 1}
    assert [h['via'] for h in suncor['headlines']] == ['party'] * 3
    out = sc.coverage(now=dt(2026, 10, 5, 13))
    assert out['total'] == 4  # India's court is judged and left out; Alito joins the other Court news
    assert [h['title'] for h in out['other']['headlines']] == ['Alito speaks at dinner']
