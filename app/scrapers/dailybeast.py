from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class DailyBeast(FeedScraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.thedailybeast.com/'
    agency: str = "The Daily Beast"
    feed: str = 'https://www.thedailybeast.com/arc/outboundfeeds/rss/articles/'
