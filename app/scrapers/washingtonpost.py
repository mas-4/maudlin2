from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class WashingtonPost(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.washingtonpost.com'
    agency: str = "The Washington Post"
    feed: str = 'https://feeds.washingtonpost.com/rss/national'
