from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class Jacobin(FeedScraper):
    bias = Bias.extreme_left
    credibility = Credibility.high
    url: str = 'https://jacobin.com'
    agency: str = "Jacobin"
    feed: str = 'https://jacobin.com/feed'
