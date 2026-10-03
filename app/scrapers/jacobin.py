from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class Jacobin(FeedScraper):
    url: str = 'https://jacobin.com'
    agency: str = "Jacobin"
    feed: str = 'https://jacobin.com/feed'
