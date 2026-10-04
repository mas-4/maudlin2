"""Render the site's pages through their real page classes from the session `data_handler` (read from the database)
and check their structure. Each page is generated once for the module.

Kept offline and read-only: no language model (llm.backend is None), the embedder loads from the local model cache
(or a stand-in when there is none), sockets refuse to connect, story syncing/labeling (which write to the database)
are stubbed, and a guard fails the run on any INSERT/UPDATE/DELETE. Pages go to a scratch build folder."""
import copy
import glob
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
from app.site.page_edits import EditsPage
from app.site.page_emotions import EmotionsPage
from app.site.page_glossary import GlossaryPage
from app.utils.config import Config

PAGES = ['index.html', 'headlines.html', 'glossary.html', 'emotions.html', 'agencies.html', 'edits.html', 'court.html']
NAV_LINKS = ['headlines.html', 'edits.html', 'emotions.html', 'agencies.html', 'court.html', 'archive.html',
             'glossary.html']
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


AB_TEST = {'url': 'https://slate.com/a.html', 'agency': 'Slate', 'bias': -2, 'state': 'won', 'winner': 'Kept <wording>',
           'started': dt(2026, 10, 4, 12), 'latest': dt(2026, 10, 4, 15),
           'variants': [{'text': 'Kept <wording>', 'default': True, 'live': True, 'won': True, 'hours': 3},
                        {'text': 'Dropped wording', 'default': False, 'live': False, 'won': False, 'hours': 0.5}]}


COURT_ROW = {'title': 'Justices weigh <Suncor> climate suit', 'first': dt(2026, 10, 5, 14), 'agency': 'Fox News',
             'bias': 2, 'rated': True, 'url': 'https://example.com/a?b=1&c=2', 'stage': 'argument',
             'issue': 'climate suit', 'side': 'right', 'via': 'party', 'tags': ['climate suit'],
             'tag_links': [{'tag': 'climate suit', 'docket': '25-170'}]}
COURT = {'term': 2026, 'source': 'https://www.supremecourt.gov/orders/26grantednotedlist.pdf', 'window_days': 14,
         'total': 2,
         'covered': [{'docket': '25-170', 'name': 'Suncor Energy v. Commissioners of Boulder County', 'raw': 'X',
                      'granted': '2/23/26', 'argued': '10/5/26', 'outlets': 1, 'sides': {'right': 1},
                      'stages': {'argument': 1}, 'headlines': [COURT_ROW]}],
         'cases': [{'docket': '25-170', 'name': 'Suncor Energy v. Commissioners of Boulder County', 'raw': 'X',
                    'granted': '2/23/26', 'argued': '10/5/26', 'outlets': 1, 'sides': {'right': 1},
                    'stages': {'argument': 1}, 'headlines': [COURT_ROW]},
                   {'docket': '25-1311', 'name': 'Apple Inc. v. Epic Games, Inc.', 'raw': 'X', 'granted': '6/1/26',
                    'argued': None, 'outlets': 0, 'sides': {}, 'stages': {}, 'headlines': []}],
         'other': {'outlets': 1, 'sides': {'left': 1}, 'stages': {'the justices': 1},
                   'tags': [('case-25-170', 'climate suit', 2), ('<guns>', '<Guns>', 2)],
                   'headlines': [{**COURT_ROW, 'title': 'Alito speaks', 'agency': 'CNN', 'bias': -1,
                                  'stage': 'the justices', 'side': 'left', 'via': None,
                                  'tag_links': [{'tag': 'climate suit', 'docket': '25-170'},
                                                {'tag': '<Guns>', 'docket': None}],
                                  'tag_keys': ['<guns>', 'case-25-170']}]}}


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
        mp.setattr(socket.socket, 'connect', refuse_connection)
        mp.setattr(llm, 'backend', lambda: None)
        mp.setattr(ph, 'sync_stories', lambda df: {})
        mp.setattr(ph, 'label_stories', lambda df, stories: {})
        mp.setattr(ph, 'link_sagas', lambda headlines, stories, story_of: {})  # writes sagas to the database
        # A/B tests: a canned one, so the section renders before the database has the table (prod migrates it)
        mp.setattr(abtests, 'tests', lambda: [AB_TEST])
        # The Supreme Court page: canned coverage (the real one asks the language model and reads the docket file)
        mp.setattr(scotus, 'coverage', lambda: COURT)
        mp.setattr(scotus, 'refresh_docket', lambda: None)
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
            for page in (GlossaryPage, EmotionsPage, EditsPage, AgenciesPage, CourtPage):
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
    rows = json.loads((site['build'] / ph.TABLE_FILE).read_text())
    assert isinstance(rows, list)
    if rows:
        assert {'agency', 'bias', 'url', 'title', 'buzz', 'story'} <= set(rows[0])
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
    cards = court.select('.court-case')
    assert len(cards) == 1
    assert cards[0].select_one('h4 a')['href'].endswith('/25-170.html')
    assert 'argued Oct 5' in cards[0].get_text() or 'to be argued Oct 5' in cards[0].get_text()
    headline = cards[0].select_one('.court-headlines a')
    assert headline.get_text() == 'Justices weigh <Suncor> climate suit'  # escaped, not markup
    assert headline['href'] == 'https://example.com/a?b=1&c=2'
    rows = court.select('.court-term tbody tr')
    assert [r.select_one('a').get_text() for r in rows][-1] == 'Apple Inc. v. Epic Games, Inc.'  # unset date last
    assert 'none yet' in rows[-1].get_text()
    assert 'Alito speaks' in court.get_text()
    other = court.select_one('#court-other li')
    assert other['data-tags'] == '<guns>|case-25-170'
    assert other.select_one('a.court-tag')['href'] == '#case-25-170'  # a docket case's tag links to its card
    assert other.select_one('button.court-tag').get_text() == '<Guns>'
    assert [b['data-tag'] for b in court.select('.court-tag-filter button')] == ['case-25-170', '<guns>']
    assert court.select_one('#case-25-170')
