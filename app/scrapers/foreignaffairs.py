from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class ForeignAffairs(FeedScraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.foreignaffairs.com'
    agency: str = "Foreign Affairs"
    feed: str = 'https://www.foreignaffairs.com/rss.xml'
