from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class WashingtonPost(FeedScraper):
    url: str = 'https://www.washingtonpost.com'
    agency: str = "The Washington Post"
    feed: str = 'https://feeds.washingtonpost.com/rss/national'
