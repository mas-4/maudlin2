"""Render the site's pages through their real page classes from the session `data_handler` (read from the database)
and check their structure. Each page is generated once for the module.

Kept offline and read-only: no language model (llm.backend is None), the embedder loads from the local model cache
(or a stand-in when there is none), sockets refuse to connect, story syncing/labeling (which write to the database)
are stubbed, and a guard fails the run on any INSERT/UPDATE/DELETE. Pages go to a scratch build folder."""
import copy
import glob
import json
import os
import re
import socket
import zlib
from datetime import datetime as dt

import numpy as np
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event

from app.analysis import abtests, clustering, llm, sagas, scotus
from app.models import engine
from app.site import page_agencies, page_headlines as ph
from app.site.page_agencies import AgenciesPage
from app.site.page_court import CourtPage
from app.site.page_trackers import FOLKLORE, TRACKERS
from app.site.page_edits import EditsPage
from app.site.page_emotions import EmotionsPage
from app.site.page_glossary import GlossaryPage
from app.site.page_sagas import SagasPage
from app.site.page_names import NamesPage
from app.utils.config import Config

PAGES = ['index.html', 'headlines.html', 'glossary.html', 'emotions.html', 'agencies.html', 'edits.html', 'court.html',
         'sagas.html', 'names.html']
NAV_LINKS = ['headlines.html', 'agencies.html', 'edits.html', 'sagas.html', 'names.html', 'court.html', 'beyond.html', 'emotions.html', 'archive.html',
             'feed.xml', 'folklore.html', 'rumors.html', 'motifs.html', 'glossary.html']
# Fewer headlines than a real build: enough for stories to form, a fraction of the time
MAIN_HEADLINES = 1000
STORY_HEADLINES = 2500
WRITES = re.compile(r'^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER)\b', re.I)


def stand_in_embed(texts):
    """Bag of hashed words, for machines without the embedding model cached."""
    out = np.zeros((len(texts), 256))
    for i, t in enumerate(texts):
        for w in re.findall(r'\w+', t.lower()):
            out[i, zlib.crc32(w.encode()) % 256] += 1
    out[:, 0] += 1e-6
    return out


# The saga tracker: one canned saga with a part on the front pages now and an earlier one
SAGA = {'id': 7, 'name': 'Fairford <plot>', 'now': True, 'first': dt(2026, 10, 3, 12), 'last': dt(2026, 10, 5, 13),
        'outlets': 41, 'left': 17, 'center': 12, 'right': 10, 'unrated': 2,
        'parts': [{'story': 26, 'label': 'Man bailed over <RAF> plot', 'first': dt(2026, 10, 3, 12),
                   'last': dt(2026, 10, 5, 7), 'now': False, 'outlets': 19, 'first_outlets': ['AP', 'BBC'],
                   'first_title': 'UK-Iranian bailed'},
                  {'story': 70, 'label': 'US pulls bombers', 'first': dt(2026, 10, 4, 22), 'last': dt(2026, 10, 5, 13),
                   'now': True, 'outlets': 39, 'first_outlets': ['A', 'B', 'C', 'D'], 'first_title': 'Bombers leave'}]}


AB_TEST = {'url': 'https://slate.com/a.html', 'agency': 'Slate', 'bias': -2, 'state': 'won', 'winner': 'Kept <wording>',
           'started': dt(2026, 10, 4, 12), 'latest': dt(2026, 10, 4, 15),
           'variants': [{'text': 'Kept <wording>', 'default': True, 'live': True, 'won': True, 'hours': 3},
                        {'text': 'Dropped wording', 'default': False, 'live': False, 'won': False, 'hours': 0.5}]}


COURT_ROW = {'title': 'Justices weigh <Suncor> climate suit', 'first': dt(2026, 10, 5, 14), 'agency': 'Fox News',
             'bias': 2, 'rated': True, 'url': 'https://example.com/a?b=1&c=2', 'stage': 'argument', 'side': 'right',
             'topics': ['climate'], 'cases': ['25-170'], 'named': '25-170', 'event_score': -1.0, 'afinn': -2.0,
             'vader_compound': -0.4, 'loaded_score': 1.5, 'emotion_ranks': 'anger,fear', 'country': 'United States'}
LEFT_ROW = {**COURT_ROW, 'title': 'Boulder "fights back" for its climate', 'agency': 'CNN', 'bias': -1, 'side': 'left',
            'loaded_score': 0.5}
SUNCOR = {'docket': '25-170', 'name': 'Suncor Energy v. Commissioners of Boulder County', 'raw': 'SUNCOR V. BOULDER',
          'granted': '2/23/26', 'argued': '10/5/26', 'from': 'SC-Colo.', 'gloss': 'Boulder <climate> suit',
          'question': 'Whether federal law precludes state-law claims', 'outlets': 2,
          'sides': {'right': 1, 'left': 1}, 'stages': {'argument': 2}, 'headlines': [COURT_ROW, LEFT_ROW]}
COURT = {'term': 2026, 'source': 'https://www.supremecourt.gov/orders/26grantednotedlist.pdf', 'window_days': 14,
         'total': 3, 'covered': [SUNCOR],
         'cases': [SUNCOR, {'docket': '25-1311', 'name': 'Apple Inc. v. Epic Games, Inc.', 'raw': 'X', 'granted': '6/1/26',
                            'argued': None, 'from': 'USCA-9', 'gloss': 'Apple contempt fight', 'question': 'Q',
                            'outlets': 0, 'sides': {}, 'stages': {}, 'headlines': []}],
         'other': {'outlets': 1, 'sides': {'left': 1}, 'stages': {'the justices': 1}, 'topics': [('retirement', 1)],
                   'headlines': [{**LEFT_ROW, 'title': 'Alito <speaks>', 'stage': 'the justices',
                                  'topics': ['retirement'], 'cases': [], 'named': None}]},
         'glosses': {}}


def refuse_connection(*args, **kwargs):
    raise RuntimeError('network access in a test')


@pytest.fixture(scope='module')
def site(data_handler, tmp_path_factory):
    build = tmp_path_factory.mktemp('site-build')
    writes = []

    def no_writes(conn, cursor, statement, parameters, context, executemany):
        if WRITES.match(statement):
            writes.append(statement)
            raise RuntimeError(f'database write in a test: {statement[:80]}')

    event.listen(engine, 'before_cursor_execute', no_writes)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Config, 'build', str(build))
        from app.site import wordcloudgen
        mp.setattr(wordcloudgen, 'CLOUD_HISTORY', str(build / 'cloud_history.json'))  # never the real history
        mp.setattr(socket.socket, 'connect', refuse_connection)
        mp.setattr(llm, 'backend', lambda: None)
        mp.setattr(ph, 'sync_stories', lambda df: {})
        mp.setattr(ph, 'label_stories', lambda df, stories: {})
        mp.setattr(ph, 'link_sagas', lambda headlines, stories, story_of: {})  # writes sagas to the database
        # A/B tests: a canned one, so the section renders before the database has the table (prod migrates it)
        mp.setattr(abtests, 'tests', lambda: [AB_TEST])
        mp.setattr(sagas, 'history', lambda: [dict(SAGA, parts=[dict(p) for p in SAGA['parts']])])
        from app.analysis import entities
        mp.setattr(entities, 'history', lambda: [{'name': 'Donald <Trump>', 'first': dt(2026, 10, 3, 12), 'last': dt(2026, 10, 5, 13),
            'outlets': 66, 'left': 30, 'center': 10, 'right': 20, 'unrated': 6, 'stories': [
                {'id': 26, 'label': 'Trump <rallies>', 'first': dt(2026, 10, 3, 12), 'last': dt(2026, 10, 4, 1), 'outlets': 20},
                {'id': 70, 'label': 'Trump defends tariffs', 'first': dt(2026, 10, 4, 22), 'last': dt(2026, 10, 5, 13), 'outlets': 40}]}])
        # The Supreme Court page: canned coverage (the real one asks the language model and reads the docket file)
        mp.setattr(scotus, 'coverage', lambda: COURT)
        mp.setattr(scotus, 'refresh_docket', lambda: None)
        mp.setattr(scotus, 'story_glosses', lambda groups: ['<Named> story'] * len(groups))
        mp.setattr(page_agencies, 'generate_wordcloud', lambda df, path: None)  # a png nobody checks here; slow
        snapshot = sorted(glob.glob(os.path.expanduser(
            '~/.cache/huggingface/hub/models--minishlab--potion-base-8M/snapshots/*/model.safetensors')))
        if clustering._embedder is None and snapshot:
            mp.setattr(clustering, 'EMBEDDING_MODEL', os.path.dirname(snapshot[-1]))
        elif clustering._embedder is None:
            for module in (ph, sagas):
                mp.setattr(module, 'embed', stand_in_embed)
            mp.setattr(ph, 'prepare_embedding_cosine',
                       lambda texts: clustering.cosine_similarity(stand_in_embed(list(texts))))

        dh = copy.copy(data_handler)
        dh.main_headline_df = data_handler.main_headline_df.head(MAIN_HEADLINES).copy()
        dh.story_headline_df = data_handler.story_headline_df.head(STORY_HEADLINES).copy()
        headlines = ph.HeadlinesPage(dh)
        try:
            headlines.generate()
            for page in (GlossaryPage, EmotionsPage, EditsPage, AgenciesPage, CourtPage, SagasPage, NamesPage):
                page(data_handler).generate()
        finally:
            event.remove(engine, 'before_cursor_execute', no_writes)
    assert writes == []
    html = {}
    for name in PAGES:
        with open(build / name, encoding='utf-8') as f:
            html[name] = f.read()
    return {'html': html, 'soup': {k: BeautifulSoup(v, 'html.parser') for k, v in html.items()},
            'context': headlines.context, 'build': build}


@pytest.fixture(scope='module')
def front(site):
    return site['soup']['index.html']


@pytest.fixture(scope='module')
def table(site):
    return site['soup']['headlines.html']


# <editor-fold desc="every page">
def test_every_page_was_written_to_the_scratch_build(site):
    for name in PAGES + ['newsletter.html', ph.TABLE_FILE]:
        assert (site['build'] / name).stat().st_size > 0, name
    assert os.path.realpath(site['build']) != os.path.realpath(os.path.join(os.path.dirname(Config.data), '_build'))


@pytest.mark.parametrize('name', PAGES)
def test_no_unrendered_jinja(site, name):
    html = site['html'][name]
    for marker in ('{{', '{%', '%}', '{#'):
        assert marker not in html, f'{marker} in {name}'


@pytest.mark.parametrize('name', PAGES)
def test_nav_links_every_page(site, name):
    nav = site['soup'][name].select_one('nav.navbar')
    assert nav is not None
    hrefs = [a['href'] for a in nav.select('.nav-links a')]
    assert hrefs == NAV_LINKS
    assert nav.select_one('a.nav-brand')['href'] == 'index.html'
    assert nav.select_one('.updated')['data-built']


@pytest.mark.parametrize('name', PAGES)
def test_assets_carry_the_build_version(site, name):
    soup = site['soup'][name]
    css = [l['href'] for l in soup.select('link[rel=stylesheet]') if 'style.css' in l['href']]
    js = [s['src'] for s in soup.select('script[src]') if 'index.js' in s['src']]
    assert len(css) == 1 and len(js) == 1
    for url in css + js:
        assert re.search(r'\?v=\d{12}$', url), url
    assert css[0].split('?v=')[1] == js[0].split('?v=')[1]


@pytest.mark.parametrize('name', PAGES)
def test_page_has_title_and_footer(site, name):
    soup = site['soup'][name]
    if name in ('index.html', 'headlines.html'):  # the home page and its copy
        assert soup.title.string == 'Big News Day'
    else:
        assert soup.title.string.startswith(f'{Config.site_name} - ')
    assert soup.select_one('.site-footer') is not None
    assert soup.html['lang'] == 'en'


@pytest.mark.parametrize('name', PAGES)
def test_ids_are_unique(site, name):
    ids = [el['id'] for el in site['soup'][name].select('[id]')]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})
# </editor-fold>


# <editor-fold desc="the front page and the table page">
def test_front_page_has_the_cloud(front):
    figure = front.select_one('figure.wordcloud')
    assert figure is not None
    assert figure.select_one('#cloud') is not None
    assert figure.select('.cloud-sort button')


def test_front_page_has_the_floating_section_rail(front):
    toc = front.select_one('nav.page-toc')
    assert toc is not None
    assert front.select_one('button.toc-toggle') is not None
    hrefs = [a['href'] for a in toc.select('a')]
    assert '#top' in hrefs
    assert 'headlines.html' in hrefs


def test_front_page_section_links_land(front):
    for a in front.select('nav.page-toc a[href^="#"]'):
        if a['href'] != '#top':
            assert front.select_one(a['href']) is not None, a['href']


def test_front_page_has_no_table(front, site):
    assert front.select_one('#wrapper') is None
    assert front.select_one('h1') is None
    assert ph.TABLE_FILE not in site['html']['index.html']
    # but it points readers to the table page outside the nav, too
    assert [a for a in front.select('a[href="headlines.html"]') if not a.find_parent('nav', class_='navbar')]


def test_front_page_story_cards_match_the_clusters(front, site):
    clusters = site['context']['clusters']
    cards = front.select('div.stories > div.story')
    assert len(cards) == len(clusters)
    assert cards, 'no stories formed from the sample of headlines'
    for card, c in zip(cards, clusters):
        assert card['id'] == f'story-{c["cluster"]}'
        assert card.select_one('h4').get_text(strip=True)
        assert card.select('.meter-dot')


def test_story_card_chips(front, site):
    for card in front.select('div.stories > div.story'):
        chips = card.select('.chips a.storylink')
        assert chips
        assert all(re.match(r'chip-(fresh|live|gone)', ' '.join(a['class'][1:])) for a in chips)
        assert all(a.select_one('.outlet-icon') is not None for a in chips)


def test_story_links_point_at_cards(front):
    ids = {el['id'] for el in front.select('[id]')}
    for a in front.select('a[href^="#story-"]'):
        assert a['href'][1:] in ids, a['href']


def test_news_day_sticker(front, site):
    day = site['context']['newsday']
    if day is None:
        pytest.skip('nothing live in the sample')
    assert day['kind'] in ph.NEWS_DAY_LABELS
    assert day['label'] in front.select_one('figure.wordcloud').get_text()


def test_table_page_has_the_table(table):
    assert table.select_one('#wrapper') is not None
    assert table.select_one('h1').get_text(strip=True) == 'Every headline right now'


def test_table_page_has_no_front_page_sections(table):
    assert table.select('.story') == []
    assert table.select_one('figure.wordcloud') is None
    assert table.select_one('nav.page-toc') is None


def test_table_rows_file_is_linked(site):
    assert ph.TABLE_FILE in site['html']['headlines.html']
    import json
    packed = json.loads((site['build'] / ph.TABLE_FILE).read_text())
    assert packed['version'] == 1 and len(packed['columns']) == len(packed['rows'][0]) if packed['rows'] else True
    rows = ph.unpack_table(packed)
    if rows:
        assert {'agency', 'bias', 'url', 'title', 'buzz', 'story'} <= set(rows[0])
        assert all(r['url'].startswith('http') for r in rows)
    assert 'unpackTable' in site['html']['headlines.html']  # the page unpacks it, and the download saves named rows
# </editor-fold>


# <editor-fold desc="how it works">
def section_terms(soup, section_id):
    """The term cards between a section heading and the next heading."""
    heading = soup.find('h2', id=section_id)
    assert heading is not None, section_id
    box = heading.find_next_sibling('div', class_='terms')
    return box.find_all('div', class_='term', recursive=False)


def test_glossary_build_history(site):
    terms = section_terms(site['soup']['glossary.html'], 'built')
    assert [t.select_one('.term-emoji').get_text() for t in terms] == ['✍️', '🛠️', '🧠']
    titles = [t.select_one('h3').get_text() for t in terms]
    assert '2024' in titles[0] and '2026' in titles[1] and 'Two different AIs' in titles[2]
    assert [t['id'] for t in terms] == ['history', 'rebuilt', 'two-ais']


def test_glossary_limits(site):
    terms = section_terms(site['soup']['glossary.html'], 'limits')
    assert len(terms) == 3
    assert all(t.select_one('h3').get_text(strip=True) for t in terms)


def test_glossary_numbers_come_from_the_settings(site):
    text = site['soup']['glossary.html'].get_text(' ')
    assert site['soup']['glossary.html'].select_one('h1').get_text() == 'How it works'
    assert str(ph.BLINDSPOT_MIN_OUTLETS) in text
    assert f'{round(100 * ph.BLINDSPOT_SHARE)}%' in text


def test_glossary_lists_every_feeling(site):
    from app.analysis.newsfilter import EMOTIONS
    text = site['soup']['glossary.html'].get_text(' ')
    for e in EMOTIONS:
        assert e in text
# </editor-fold>


# <editor-fold desc="other pages">
def test_emotions_page(site):
    soup = site['soup']['emotions.html']
    from app.analysis.newsfilter import EMOTIONS
    tables = soup.select('table.emotion-matrix')
    assert tables
    header = [th.get('title') for th in tables[0].select('thead th') if th.get('title')]
    assert sorted(header) == sorted(EMOTIONS)


def test_agencies_page(site):
    soup = site['soup']['agencies.html']
    assert soup.select_one('h1').get_text(strip=True) == 'The outlets'


def test_edits_page(site):
    soup = site['soup']['edits.html']
    assert soup.find('h2', string='Headline changes') is not None
    assert soup.select_one('details.how-it-works') is not None
# </editor-fold>


def test_edits_page_shows_ab_tests_escaped(site):
    page = site['soup']['edits.html']
    test = page.select_one('.ab-test.ab-won')
    assert test is not None and '🏆' in test.get_text()
    assert test.select_one('.ab-won a').get_text() == 'Kept <wording>'  # escaped, not parsed as a tag
    assert 'shown without javascript' in test.select_one('.ab-won').get_text()
    assert test.select_one('.ab-lost').get_text().startswith('Dropped wording')


def test_court_page(site):
    court = site['soup']['court.html']
    [card] = court.select('.court-cards #case-25-170')
    assert card.select_one('h4').get_text() == 'Boulder <climate> suit'  # escaped gloss as the title
    assert card.select_one('.court-meta a')['href'].endswith('/25-170.html')
    assert 'argued Oct 5' in card.get_text()
    left, right = card.select('.court-frame')
    assert 'court-frame-left' in left['class'] and 'CNN' in left.get_text()
    assert right.select_one('.court-frame-title').get_text() == '“Justices weigh <Suncor> climate suit”'
    assert right['href'] == 'https://example.com/a?b=1&c=2'
    assert card.select_one('.quote-chip').get_text().startswith('“fights back”')
    assert len(card.select('.story-outlets .storylink')) == 2
    assert len(card.select('.meter')) == 3  # lean, mood, spice
    [topic] = court.select('.court-topic')
    assert topic.select_one('h4').get_text() == 'retirement' and 'Alito <speaks>' in topic.get_text()
    covered, quiet = court.select('.court-quiet')  # the term's cases, by argument date (no date last)
    assert covered['href'] == '#case-25-170' and 'covered' in covered['class']
    assert covered.select_one('.court-gloss-tag').get_text() == 'Boulder <climate> suit'
    assert 'Apple contempt fight' in quiet.get_text() and quiet['href'].endswith('/25-1311.html')
    assert 'no coverage' in quiet.get_text()
    assert [a['href'] for a in court.select('.page-toc a')] == ['#court-cases', '#court-singles', '#court-term']


def test_nav_trackers_and_folklore_menus(site):
    menus = site['soup']['edits.html'].select('nav .nav-menu')
    assert [m.select_one('summary').get_text(strip=True) for m in menus] == ['trackers', 'folklore']
    assert [a['href'] for a in menus[0].select('.nav-menu-list a')] == [t['href'] for t in TRACKERS]
    assert [a['href'] for a in menus[1].select('.nav-menu-list a')] == [t['href'] for t in FOLKLORE]


def test_edits_page_is_searchable_and_sortable(site):
    edits = site['soup']['edits.html']
    if not edits.select('#rewrites > .edit'):
        pytest.skip('no rewrites in the window')
    tools = edits.select_one('.edit-tools')
    assert tools.select_one('input.edit-search')
    assert [b['data-sort'] for b in tools.select('button[data-sort]')] == ['newest', 'oldest', 'outlet']
    first = edits.select_one('#rewrites > .edit')
    assert first['data-when'].isdigit() and first['data-agency']


def test_story_outlet_chips_stay_in_their_box(front):
    # A <p> can't hold the coverage lines' own <p>s: the browser closes it early and the chips fall out of it
    cards = front.select('.story')
    assert cards and all(card.select('.story-outlets .storylink') for card in cards)


def test_story_cards_carry_a_stable_share_anchor(front, site):
    story_of = site['context'].get('story_of') or {}
    for card in front.select('.story'):
        cluster = int(card['id'].removeprefix('story-'))
        if cluster in story_of:
            assert card['data-share'] == f's-{story_of[cluster]}'


def test_folklore_page_never_publishes_posts(monkeypatch, tmp_path):
    from app.site import page_folklore as pn
    report = {'posts': 100, 'authors': 80, 'hours': 24, 'made': '2026-10-05T04:00', 'found': [
        {'authors': 12, 'posts': 14, 'variety': 0.9, 'kind': 'told', 'examples': ['A <secret> post by someone'],
         'label': {'retold': True, 'narrative': 'They are <keeping> him alive', 'genre': 'folk belief',
                   'motif_chapter': 'D Magic', 'motif': 'the kept king', 'villain': 'doctors', 'victim': '',
                   'hero': '', 'politics': True, 'side': 'left', 'rumor_class': 'dread', 'conspiracy': 'event',
                   'family': 'celebrities'},
         'story': {'label': 'Trump health', 'relation': 'same issue'}, 'voters': []},
        {'authors': 6, 'posts': 6, 'variety': 0.8, 'kind': 'told', 'examples': ['few'],
         'label': {'retold': True, 'narrative': 'Only six people say this'}},
        {'authors': 9, 'posts': 9, 'variety': 0.0, 'kind': 'copypasta', 'examples': ['Pasted <words>']}]}
    monkeypatch.setattr(pn, 'latest_report', lambda: report)
    monkeypatch.setattr(pn.motif_index, 'load', lambda: {'next': 8, 'claims': {
        pn.motif_index.key('They are <keeping> him alive'): ['M007']}, 'entries': {'M007': {
            'id': 'M007', 'name': 'the ruler kept alive in secret', 'claims': [{}, {}, {}]}}})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    from app.analysis import focus_group
    (tmp_path / 'fg.json').write_text(json.dumps({'https://ep/1': {'title': 'Ep61: Trump voters', 'date': '2026-10-03',
        'read': 1, 'claims': [{'claim': 'ChatGPT reports what you say to the government', 'side': 'Trump voter',
                               'quote': 'SECRET QUOTE probably recording everything', 'at': 60}]}}))
    monkeypatch.setattr(focus_group, 'STORE', str(tmp_path / 'fg.json'))
    for debug, shows_posts in ((False, False), (True, True)):
        monkeypatch.setattr(Config, 'debug', debug)
        pn.FolklorePage().generate()
        html = (tmp_path / 'folklore.html').read_text()
        assert 'They are &lt;keeping&gt; him alive' in html and '🔗 Same issue as' in html and 'Trump health' in html
        assert 'These are rumors, not facts.' in html
        # What voters say in focus groups: the claim in our words, never the quote
        assert 'ChatGPT reports what you say to the government' in html and 'SECRET QUOTE' not in html
        assert '😨 dread rumor' in html and 'data-rumor="dread"' in html
        assert ('🕵️ event conspiracy' in html) is shows_posts  # held to previews until it's reliable
        # Not a bare "left"/"right" (reads as "correct"); the model's guess only in previews
        assert ('🏛️ left-wing (model' in html) is shows_posts
        assert 'Only six people' not in html and '1 more told by fewer' in html
        assert 'the kept king' not in html  # the labeler's own motif phrase isn't shown; the index entry is
        assert 'Motif-Index</a> D' not in html  # Thompson's chapters are off the site
        assert 'href="motifs.html#M007"' in html and '🧩 the ruler kept alive in secret <span class="motif-seen">×3</span></a>' in html
        assert '🦹 villain</b> doctors' in html
        assert ('A &lt;secret&gt; post' in html) is shows_posts and ('Pasted &lt;words&gt;' in html) is shows_posts


def test_table_filters_by_feeling(table):
    picks = [b['data-value'] for b in table.select('[data-filter="feeling"]')]
    assert picks[0] == 'all' and {'fear', 'anger', 'hope'} <= set(picks) and 'neutral' not in picks


def test_satire_is_labeled_as_jokes_on_its_story(monkeypatch, tmp_path):
    from app.site import page_headlines
    monkeypatch.setattr(page_headlines.satire, 'jokes', lambda stories: {next(iter(stories)): [
        {'title': 'Area <man> wins', 'url': 'https://theonion.com/x', 'source': 'The Onion', 'group': 'left',
         'summary': '', 'published': '2026-10-04T12:00:00+00:00'}]})
    page = page_headlines.HeadlinesPage.__new__(page_headlines.HeadlinesPage)
    page.context = {'titles': {3: 'A story'}}
    page.satire_coverage([{'cluster': 3}])
    assert page.context['satire_of'][3][0]['color'] == page.SHOW_GROUP['left']


def test_folklore_cards_link_fact_checks(monkeypatch, tmp_path):
    from app.site import page_folklore as pn
    report = {'posts': 10, 'authors': 10, 'hours': 24, 'made': '2026-10-05T04:00', 'found': [
        {'authors': 12, 'posts': 14, 'variety': 0.9, 'kind': 'told', 'examples': ['x'],
         'label': {'retold': True, 'narrative': 'The pilot was a false flag'},
         'factchecks': [{'source': 'NewsGuard', 'title': 'False flag <claim>', 'url': 'https://n.example/1',
                         'published': '2026-10-02'}]}]}
    monkeypatch.setattr(pn, 'latest_report', lambda: report)
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    monkeypatch.setattr(Config, 'debug', False)
    pn.FolklorePage().generate()
    html = (tmp_path / 'folklore.html').read_text()
    assert '<b>NewsGuard</b>: False flag &lt;claim&gt;' in html


def test_folklore_withheld_claims_never_show(monkeypatch, tmp_path):
    from app.site import page_folklore as pn
    report = {'posts': 10, 'authors': 10, 'hours': 24, 'made': '2026-10-05T04:00', 'found': [
        {'authors': 12, 'posts': 14, 'variety': 0.9, 'kind': 'told', 'examples': ['x'],
         'label': {'retold': True, 'narrative': 'A misread claim'}}]}
    monkeypatch.setattr(pn, 'latest_report', lambda: report)
    monkeypatch.setattr(pn, 'withheld', lambda: {'A misread claim'})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    monkeypatch.setattr(Config, 'debug', False)
    pn.FolklorePage().generate()
    assert 'A misread claim' not in (tmp_path / 'folklore.html').read_text()


def test_rumors_page_lists_labeled_fact_checks(monkeypatch, tmp_path):
    from app.site import page_rumors as pr
    items = [{'url': 'https://snopes.example/1', 'title': 'Did a <bison> herd save a hiker?', 'source': 'Snopes',
              'published': '2026-10-03T12:00:00+00:00', 'summary': ''},
             {'url': 'https://snopes.example/2', 'title': 'Unlabeled', 'source': 'Snopes',
              'published': '2026-10-03T12:00:00+00:00', 'summary': ''}]
    labels = {'https://snopes.example/1': {'claim': 'A bison herd protected a hiker', 'genre': 'contemporary legend',
                                           'rumor_class': 'wish', 'conspiracy': 'not a conspiracy',
                                           'family': 'animals and nature'}}
    monkeypatch.setattr(pr.factchecks, '_items', lambda days: items)
    monkeypatch.setattr(pr.factchecks, 'label_all', lambda items: labels)
    monkeypatch.setattr(pr.circulation, 'load', lambda: {'hours': 72, 'claims': {
        'https://snopes.example/1': {'telling': 3, 'arguing': 1, 'people': 4, 'checked': 9}}})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    pr.RumorsPage().generate()
    html = (tmp_path / 'rumors.html').read_text()
    assert 'Did a &lt;bison&gt; herd save a hiker?' in html and '🌈 wish rumor' in html
    assert 'conspiracy</span>' not in html and 'Unlabeled' not in html  # no plot claimed; not labeled yet
    assert '<b>3</b> telling it, <b>1</b> arguing against it' in html
    assert 'These are rumors, not facts.' in html


def test_beyond_page_tags_pieces_and_lists_every_source(monkeypatch, tmp_path):
    from app.site import page_beyond as pb
    monkeypatch.setattr(pb.sidefeeds, 'recent', lambda **k: [
        {'title': 'Ep. 9: <the> filibuster', 'url': 'https://pod.example/9', 'summary': '', 'source': 'Show A',
         'kind': 'podcast', 'group': 'left', 'published': '2026-10-04T12:00:00+00:00'}])
    monkeypatch.setattr(pb.investigations, 'recent', lambda **k: [])
    monkeypatch.setattr(pb.subjects, 'tag', lambda items: {'https://pod.example/9': ['Congress and legislation']})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    pb.BeyondPage().generate()
    html = (tmp_path / 'beyond.html').read_text()
    assert 'Ep. 9: &lt;the&gt; filibuster' in html and 'Congress and legislation' in html
    assert 'The Jesse Kelly Show' in html and 'archived for research, not shown; transcribed' in html
    assert 'Bellingcat' in html and 'PolitiFact' in html


def test_front_page_has_no_link_list_blocks(front):
    assert front.select_one('#investigations') is None and front.select_one('#shows') is None


def test_methods_page_publishes_the_log(monkeypatch, tmp_path):
    from app.site import page_methods as pm
    log = tmp_path / 'log.md'
    log.write_text('# Methods log\n\nIntro paragraph.\n\n## 2026-10-05\n- **A change.** It <b>matters</b>.\n\n'
                   '## 2026-10-04\n- Another.\n')
    monkeypatch.setattr(pm, 'LOG', str(log))
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    pm.MethodsPage().generate()
    html = (tmp_path / 'methods.html').read_text()
    assert '<h2 id="2026-10-05">2026-10-05</h2>' in html and '<strong>A change.</strong>' in html
    assert 'href="#2026-10-04"' in html and 'Intro paragraph' not in html


def test_saga_tracker_lays_out_parts_on_a_timeline(site):
    page = site['soup']['sagas.html']
    card = page.select_one('#saga-7')
    assert card.select_one('h3').get_text() == '🧵 Fairford <plot>' and card['data-now'] == '1'
    first, second = card.select('.saga-timeline li')
    assert first.select_one('.saga-part-title').get_text() == 'Man bailed over <RAF> plot'  # escaped, no link
    assert second.select_one('a')['href'] == 'index.html#s-70'  # on the front page now: a link to its card
    assert first.select_one('.saga-bar')['style'].startswith('left: 0.0%')
    assert 'first on AP, BBC' in first.get_text() and 'first on 4 outlets at once' in second.get_text()
    assert [s.get_text() for s in card.select('.saga-lean span')] == ['17', '12', '10']


def test_names_page_tracks_each_name_day_by_day(site):
    card = site['soup']['names.html'].select_one('.name-card')
    assert card.select_one('h3').get_text() == '🗣️ Donald <Trump>' and card['data-now'] == '1'
    assert [li.select_one('.saga-part-title').get_text() for li in card.select('.saga-timeline li')] == \
        ['Trump defends tariffs', 'Trump <rallies>']  # newest first, escaped
    assert len(card.select('.name-day')) == 3  # Oct 3, 4 and 5
