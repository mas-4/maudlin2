from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class StarTribune(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.startribune.com'
    agency: str = "Star Tribune"
    feed: str = 'https://www.startribune.com/rss/'
