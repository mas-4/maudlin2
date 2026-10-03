from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class NewsNation(FeedScraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.newsnationnow.com/'
    agency: str = "News Nation"
    feed: str = 'https://www.newsnationnow.com/feed/'
