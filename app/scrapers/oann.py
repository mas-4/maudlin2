from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class OneAmericaNewsNetwork(FeedScraper):
    url: str = 'https://www.oann.com'
    agency: str = "One America News Network"
    feed: str = 'https://www.oann.com/feed/'
    country: str = Country.us
