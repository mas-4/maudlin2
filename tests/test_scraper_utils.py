"""Scraper helpers that don't need the network or the database: href cleanup, feed parsing, the dataframe filters
and the text extraction they rely on. Scrapers are built without __init__ (which registers the outlet in the
database) and fed canned pages."""
import pytest
from bs4 import BeautifulSoup as Soup

from app.analysis.preprocessing import extract_text, preprocess, strip_story_attributions
from app.scraper import FeedScraper, GoogleNewsScraper, Scraper
from app.scrapers.ap import AP
from app.scrapers.guardian import Guardian
from app.scrapers.npr import NPR
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
    ('Photo by Jane Doe/Getty Images', 'Photo by Jane Doe/Getty Images'),  # only a bare credit is dropped
])
def test_preprocess(text, expected):
    assert preprocess(text) == expected


def test_strip_story_attributions_keeps_longer_text():
    assert strip_story_attributions('A long caption about Getty Images') == 'A long caption about Getty Images'
