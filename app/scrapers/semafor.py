from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class Semafor(FeedScraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.semafor.com'
    agency: str = "Semafor"
    feed: str = 'https://www.semafor.com/rss.xml'
