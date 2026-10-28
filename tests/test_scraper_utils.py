"""Scraper helpers that don't need the network or the database: href cleanup, feed parsing, the dataframe filters
and the text extraction they rely on. Scrapers are built without __init__ (which registers the outlet in the
database) and fed canned pages."""
import os
import sqlite3

import pytest
from bs4 import BeautifulSoup as Soup

from app.analysis.preprocessing import extract_text, is_photo_credit, preprocess, strip_story_attributions
from app.scraper import FeedScraper, GoogleNewsScraper, Scraper
from app.scrapers.abc import ABC
from app.scrapers.ap import AP
from app.scrapers.christiansciencemonitor import ChristianScienceMonitor
from app.scrapers.cnn import CNN
from app.scrapers.gatewaypundit import GatewayPundit
from app.scrapers.guardian import Guardian
from app.scrapers.nbc import NBC
from app.scrapers.npr import NPR
from app.scrapers.redstate import RedState
from app.scrapers.scrippsnews import ScrippsNews
from app.scrapers.townhall import Townhall
from app.scrapers.vox import Vox
from app.utils.constants import Constants


def bare(cls):
    """A scraper instance with only the state setup() and the filters use; nothing touches the database."""
    scraper = cls.__new__(cls)
    scraper.downstream = []
    return scraper


# clean_href()

@pytest.mark.parametrize('href, expected', [
    ('https://www.theguardian.com/world/1', 'https://www.theguardian.com/world/1'),
    ('http://insecure.example/a', 'http://insecure.example/a'),
    ('//cdn.example/a', 'https://cdn.example/a'),  # protocol-relative
    ('/world/2024/oct/01/story', 'https://www.theguardian.com/us/world/2024/oct/01/story'),
    ('story.html', 'https://www.theguardian.com/us/story.html'),
    ('https://x.example/a  ', 'https://x.example/a'),
])
def test_clean_href(href, expected):
    assert bare(Guardian).clean_href(href) == expected


@pytest.mark.parametrize('href', ['  https://x.example/a', '\n/world/a'])
def test_clean_href_leading_whitespace(href):
    assert ' ' not in bare(Guardian).clean_href(href)
    assert '\n' not in bare(Guardian).clean_href(href)


def test_clean_href_root_url_trailing_slash_not_doubled():
    assert bare(NPR).clean_href('/nx-s1-123') == 'https://text.npr.org/nx-s1-123'
    assert bare(NPR).clean_href('nx-s1-123') == 'https://text.npr.org/nx-s1-123'


def test_repr():
    assert repr(bare(NPR)) == '(Scraper: NPR)' == str(bare(NPR))


# FeedScraper.setup()

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Here&amp;#8217;s why rates fell</title><link>https://www.vox.com/a</link></item>
<item><title>Plain &amp; simple</title><link>  https://www.vox.com/b  </link></item>
<item><title></title><link>https://www.vox.com/empty-title</link></item>
<item><title>No link</title></item>
<item><link>https://www.vox.com/no-title</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title type="html">Atom &amp;amp; html title</title><link rel="alternate" href="https://www.vox.com/c"/></entry>
<entry><title>Empty href</title><link href=""/></entry>
</feed>"""


def test_feed_setup_rss_unescapes_and_skips_incomplete():
    scraper = bare(Vox)
    scraper.setup(Soup(RSS, 'xml'))
    assert scraper.downstream == [('https://www.vox.com/a', 'Here’s why rates fell'),
                                  ('https://www.vox.com/b', 'Plain & simple')]


def test_feed_setup_atom_uses_href():
    scraper = bare(Vox)
    scraper.setup(Soup(ATOM, 'xml'))
    assert scraper.downstream == [('https://www.vox.com/c', 'Atom & html title')]


def test_feed_scraper_requires_feed():
    class NoFeed(FeedScraper):
        url = 'https://example.org/'
        agency = 'Example'

    with pytest.raises(ValueError, match='Feed must be set'):
        bare(NoFeed).run_setup()


def test_feed_scraper_parses_xml():
    assert FeedScraper.parser == 'xml' and Scraper.parser == 'lxml'


# GoogleNewsScraper

def test_google_news_feed_url():
    assert bare(AP).feed == \
        'https://news.google.com/rss/search?q=site:apnews.com+when:1d&hl=en-US&gl=US&ceid=US:en'


def test_google_news_strips_suffix():
    feed = """<rss><channel>
    <item><title>Storm hits coast - AP News</title><link>https://news.google.com/rss/articles/1</link></item>
    <item><title>No suffix here</title><link>https://news.google.com/rss/articles/2</link></item>
    <item><title>Mentions - AP News mid-title - AP News</title><link>https://news.google.com/rss/articles/3</link></item>
    <item><title>Google tags by domain now too - apnews.com</title><link>https://news.google.com/rss/articles/4</link></item>
    </channel></rss>"""
    scraper = bare(AP)
    scraper.setup(Soup(feed, 'xml'))
    assert [t for _, t in scraper.downstream] == ['Storm hits coast', 'No suffix here', 'Mentions - AP News mid-title',
                                                 'Google tags by domain now too']


def test_google_news_scraper_is_a_feed_scraper():
    assert issubclass(GoogleNewsScraper, FeedScraper)


# Site-specific setup() on canned pages

def test_guardian_setup_picks_dated_links_with_labels():
    page = """<html><body>
    <a href="/world/2024/oct/01/storm" aria-label="Storm hits the coast">x</a>
    <a href="/world/2024/oct/01/no-label">no label</a>
    <a href="/about" aria-label="About us">About</a>
    </body></html>"""
    scraper = bare(Guardian)
    scraper.setup(Soup(page, 'lxml'))
    assert scraper.downstream == [('/world/2024/oct/01/storm', 'Storm hits the coast')]


def test_npr_setup_builds_absolute_links():
    page = '<html><body><a class="topic-title" href="/nx-s1-1">Headline one</a><a href="/other">x</a></body></html>'
    scraper = bare(NPR)
    scraper.setup(Soup(page, 'lxml'))
    [(href, tag)] = scraper.downstream
    assert href == 'https://text.npr.org/nx-s1-1'
    assert tag.get_text() == 'Headline one'


# process_dataframe(): the filters every scraper's headlines go through

def long_title(n):
    return ' '.join(['word'] * n)


def test_process_dataframe_filters():
    scraper = bare(Guardian)
    repeated = 'Sign up for our newsletter today'
    downstream = [
        ('/world/2024/oct/01/a', '<a>Storm hits the coast tonight</a>'),  # kept, relative href made absolute
        ('https://ok.example/b', 'Senate passes the budget bill'),  # kept
        ('not a url at all', 'Valid looking headline with words'),  # bad url after cleaning (has spaces)
        ('https://ok.example/c', 'Too short'),  # under the minimum words
        ('https://ok.example/d', long_title(Constants.Thresholds.max_headline_words + 1)),  # a summary paragraph
        *[(f'https://ok.example/r{i}', repeated) for i in range(Constants.Thresholds.page_repeat_limit)],  # chrome
    ]
    df = scraper.process_dataframe(downstream)
    assert df['title'].tolist() == ['Storm hits the coast tonight', 'Senate passes the budget bill']
    assert df['href'].tolist() == ['https://www.theguardian.com/us/world/2024/oct/01/a', 'https://ok.example/b']
    assert df['row'].tolist() == [0, 1]  # page position survives the drops
    assert df['processed'].tolist() == ['Storm hits the coast tonight', 'Senate passes the budget bill']


def test_process_dataframe_keeps_boundary_lengths():
    lo, hi = Constants.Thresholds.min_headline_words, Constants.Thresholds.max_headline_words
    df = bare(Guardian).process_dataframe([('https://ok.example/a', long_title(lo)),
                                           ('https://ok.example/b', long_title(hi))])
    assert df['word_count'].tolist() == [lo, hi]


def test_process_dataframe_repeats_below_limit_kept():
    n = Constants.Thresholds.page_repeat_limit - 1
    df = bare(Guardian).process_dataframe([(f'https://ok.example/{i}', 'The same story twice over') for i in range(n)])
    assert len(df) == n


def test_process_dataframe_drops_empty_processed():
    # A photo credit has enough words but preprocesses to nothing
    df = bare(Guardian).process_dataframe([('https://ok.example/a', 'Jane Doe / AP'),
                                           ('https://ok.example/b', 'Jane Doe / AP reports more')])
    assert df['title'].tolist() == ['Jane Doe / AP reports more']


# extract_text() and preprocess(), which the filters lean on

@pytest.mark.parametrize('raw, expected', [
    ('<a href="/x">Storm <b>hits</b> coast</a>', 'Storm hits coast'),
    ('<a>Visible<!-- hidden comment --></a>', 'Visible'),
    ('<a>Headline<script>var x = 1;</script></a>', 'Headline'),
    ('<a>Text {"json": true} after</a>', 'Text  after'),
    ('plain text', 'plain text'),
])
def test_extract_text(raw, expected):
    assert extract_text(raw) == expected


@pytest.mark.parametrize('text, expected', [
    ('“Quoted” headline’s here', '"Quoted" headline\'s here'),
    ('War — and peace', 'War -- and peace'),
    ('Storm hits coast 5m ago', 'Storm hits coast'),
    ('Storm hits coast Updated 2h ago', 'Storm hits coast Updated'),  # only the lowercase 'updated' prefix is cut
    ('Storm   hits\ncoast', 'Storm hits coast'),
    ('Storm hits coast.', 'Storm hits coast'),
    ('Jane Doe/Getty Images', ''),
    ('Jane Doe / AP', ''),
    ('Reuters/Jane Doe', ''),
    ('Photo by Jane Doe/Getty Images', ''),
    ('Koch agrees to buy Getty Images', 'Koch agrees to buy Getty Images'),  # only a bare credit is dropped
])
def test_preprocess(text, expected):
    assert preprocess(text) == expected


def test_strip_story_attributions_keeps_longer_text():
    assert strip_story_attributions('A long caption about Getty Images') == 'A long caption about Getty Images'


# Bylines, section labels and view counts inside the headline's link are taken out (Oct 28)

TOWNHALL_CARD = """<html><body><a class="th-ts-item" href="/news/amy-curtis/2026/10/27/gallup-poll-n2685361">
<div><img alt="VIP" class="thm-vip-badge" src="x.svg"/></div>
<div class="th-ts-body"><div class="th-ts-eye">Polling</div>
<div class="th-ts-hed">This Gallup Poll Shows Another Stark Difference</div><div class="th-ts-by">Amy Curtis</div></div>
</a><a class="th-brk-item" href="/smoosieq/2026/10/27/scotus-n2208687"><div class="th-brk-body">
<div class="th-brk-hed">SCOTUS Won't Revive Biden-Era Rule</div><div class="th-brk-by">Susie Moore</div></div></a>
</body></html>"""


@pytest.mark.parametrize('cls', [Townhall, RedState])
def test_townhall_cards_lose_byline_and_section(cls):
    scraper = bare(cls)
    scraper.setup(Soup(TOWNHALL_CARD, 'lxml'))
    assert [' '.join(extract_text(tag).split()) for _, tag in scraper.downstream] == [
        'This Gallup Poll Shows Another Stark Difference', "SCOTUS Won't Revive Biden-Era Rule"]


def test_gateway_pundit_trending_loses_view_count():
    page = """<html><body><a class="pa-trending__link" href="https://www.thegatewaypundit.com/2026/10/translation/">
    <span class="pa-trending__headline"><span class="pa-trending__views" data-pa-f="views">86.3K views</span>
    <span data-pa-f="title">Translation Reveals a Message</span></span></a></body></html>"""
    scraper = bare(GatewayPundit)
    scraper.setup(Soup(page, 'lxml'))
    [(_, tag)] = scraper.downstream
    assert ' '.join(extract_text(tag).split()) == 'Translation Reveals a Message'


def test_scripps_promo_loses_category_and_author():
    page = """<html><body><a class="promo__link" href="https://www.scrippsnews.com/sports/final-four">
    <h6 class="promo__category">Sports</h6><h3 class="promo__title"> Could the Final Four be coming? </h3>
    <div class="promo__author"> Justin Boggs </div></a></body></html>"""
    scraper = bare(ScrippsNews)
    scraper.setup(Soup(page, 'lxml'))
    [(_, tag)] = scraper.downstream
    assert ' '.join(extract_text(tag).split()) == 'Could the Final Four be coming?'


# Photo credits: a story's photo is a link of its own, and its credit was read as a headline (Oct 28). The fixtures
# are links as the database stored them (tests/fixtures/photo_credits), the photo's link and the headline's.

CREDIT_PAGES = os.path.join(os.path.dirname(__file__), 'fixtures', 'photo_credits')


def credit_page(name):
    with open(os.path.join(CREDIT_PAGES, f'{name}.html')) as f:
        return Soup(f.read(), 'lxml')


@pytest.mark.parametrize('cls, page, headlines', [
    (NBC, 'nbc', ['Judge directs Trump to sit for deposition in his $10 billion lawsuit against the BBC']),
    (CNN, 'cnn', ['‘They wanted my voice gone’: A swing-seat, pro-Israel Democrat is fending off criticism from both '
                  'parties', 'She exchanged 40,000 texts with her alleged killer. At his trial, they’re being used to '
                  'tell two different stories']),  # and the orangutan video's caption, credit and label are gone
    (ABC, 'abc', ['Alexander brothers sentenced to 30 years in federal sex trafficking case']),
    (ChristianScienceMonitor, 'csm', ['From the Magazine In Ukraine, holding on to childhood in a time of war']),
])
def test_photo_links_lose_their_credit(cls, page, headlines):
    scraper = bare(cls)
    scraper.setup(credit_page(page))
    texts = [' '.join(extract_text(tag).split()) for _, tag in scraper.downstream]
    assert [t for t in texts if t] == headlines  # the photo's link reads as nothing: no credit, caption or label
    df = scraper.process_dataframe(scraper.downstream)
    assert [' '.join(t.split()) for t in df['title']] == headlines


@pytest.mark.parametrize('text', [
    'Saul Loeb / AFP via Getty', 'Marco Bello/Bloomberg via Getty Images', 'Chelsea Stahl / NBC News',
    'Gauthier Bedrignans/Hans Lucas/AFP/Getty Images', 'Dominika Zarzycka / SOPA Images/LightRocket via Getty',
    'Centers for Disease Control and Prevention/Getty Images', 'Tim Boyle/Getty Images, FILE',
    'Brandon Bell / Getty Images file', 'Arturo Holmes/Getty Images for Disney', 'U.S. Navy / via Getty',
    'Photographer: Natalia Kolesnikova/AFP/Getty Images', 'Photo illustration : 731; Getty Images',
    'Justin Tallis/AFP via Getty Images | Allan Lewis/AFP via Getty Images', 'Moscow City Court Press Service via AP',
    '• For Subscribers     Justin Lane/EPA-EFE/Shutterstock', 'Bob Donnan/IMAGN IMAGES via Reuters Connect',
    'Scott Peterson/Getty Images/The Christian Science Monitor', 'Jane Doe/Reuters',
])
def test_photo_credits_are_not_headlines(text):
    assert is_photo_credit(text)
    assert preprocess(text) == ''


@pytest.mark.parametrize('text', [
    'AP sources: Trump to name new Fed chair this week',
    'Reuters poll shows Harris ahead in Pennsylvania',
    'Koch agrees to buy Getty Images',
    'Getty Images files for bankruptcy, advances restructuring plan',
    ' GETTY Images to File for Bankruptcy, Go Private In Restructuring Deal...',
    'Nice Work If You Can Getty',
    'Anthropic warns government attitudes may hurt customer ties, IPO prospectus shows: Reuters',
    'US increasing Middle East military buildup – AP',
    'OPEC+ agrees to keep November oil output targets steady - Reuters',
    "UAE had shared details about FlyDubai flight with Israel, officials tell AP",
    'Exclusive: Iran shipped drones to Russia via Caspian Sea, sources tell Reuters',
    'Is 24/7 news coverage good for CNN',
    'A long caption about Getty Images',
    '',
])
def test_headlines_naming_an_agency_are_kept(text):
    assert not is_photo_credit(text)


def test_clean_photo_credits_lists_credit_only_rows():
    """The old rows' script re-reads the stored html: a photo's link held only its credit, the headline stays"""
    from scripts.clean_photo_credits import changes
    con = sqlite3.connect(':memory:')
    con.executescript("""create table agency (id integer primary key, name text);
        create table article (id integer primary key, agency_id integer);
        create table headline (id integer primary key, article_id integer, title text, raw text);
        insert into agency values (1, 'NBC News'); insert into article values (1, 1);""")
    links = [str(a) for a in credit_page('nbc').find_all('a')]
    con.executemany('insert into headline values (?, 1, ?, ?)', [
        (1, 'Saul Loeb / AFP via Getty', links[0]),
        (2, 'Judge directs Trump to sit for deposition in his $10 billion lawsuit against the BBC', links[1]),
        (3, 'Jane Doe / AP', '<a>Jane Doe / AP</a>'),  # no credit element, but only a credit
        (4, 'Biden/Harris rally draws crowds', '<a>Biden/Harris rally draws crowds</a>')])
    assert list(changes(con)) == [(1, 'NBC News', 'Saul Loeb / AFP via Getty', None),
                                  (3, 'NBC News', 'Jane Doe / AP', None)]
