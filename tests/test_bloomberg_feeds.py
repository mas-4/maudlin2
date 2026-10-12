"""app/scrapers/bloomberg.py: Bloomberg through its own section feeds (its front page answers with a captcha)"""
from bs4 import BeautifulSoup as Soup

from app.scrapers.bloomberg import Bloomberg

FEED = """<rss><channel><title>Bloomberg Politics</title><link>http://bloomberg.com/politics/</link>
<item><title>Trump Signs a Deal</title><link>https://www.bloomberg.com/news/articles/2026-10-12/trump-signs-a-deal</link></item>
<item><title>A video</title><link>https://www.bloomberg.com/news/videos/2026-10-12/a-video</link></item>
<item><title>Trump Signs a Deal</title><link>https://www.bloomberg.com/news/articles/2026-10-12/trump-signs-a-deal?cmpid=x</link></item>
</channel></rss>"""


def test_articles_only_once_each_tagged_as_the_front_page_did():
    b = Bloomberg.__new__(Bloomberg)
    b.downstream = []
    seen = set()
    for _ in range(2):  # the same article in two sections' feeds
        b.setup(Soup(FEED, 'xml'), seen)
    assert b.downstream == [('https://www.bloomberg.com/news/articles/2026-10-12/trump-signs-a-deal?srnd=homepage-americas',
                             'Trump Signs a Deal')]
