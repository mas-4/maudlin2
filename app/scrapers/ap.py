from bs4 import BeautifulSoup as Soup

from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class AP(FeedScraper):
    """AP blocks scrapers outright, so we read its last day of stories through Google News. The links are
    Google redirects rather than apnews.com urls, and the order is Google's rather than AP's front page."""
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://apnews.com/'
    agency: str = "AP"
    feed: str = 'https://news.google.com/rss/search?q=site:apnews.com+when:1d&hl=en-US&gl=US&ceid=US:en'
    suffix = ' - AP News'

    def setup(self, soup: Soup):
        super().setup(soup)
        self.downstream = [(href, title.removesuffix(self.suffix)) for href, title in self.downstream]
