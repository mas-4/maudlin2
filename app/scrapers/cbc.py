from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country, Constants


class CBC(FeedScraper):
    headers = Constants.Headers.firefox
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.cbc.ca'
    agency: str = "CBC"
    feed: str = 'https://www.cbc.ca/webfeed/rss/rss-topstories'
    country: str = Country.ca
