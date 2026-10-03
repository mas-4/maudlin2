from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class Atlantic(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.theatlantic.com/'
    agency: str = "The Atlantic"
    feed: str = 'https://www.theatlantic.com/feed/all/'
