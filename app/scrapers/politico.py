from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class Politico(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.politico.com'
    agency: str = "Politico"
    feed: str = 'https://rss.politico.com/politics-news.xml'
