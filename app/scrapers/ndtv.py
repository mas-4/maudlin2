from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class NDTV(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.ndtv.com/'
    agency: str = "NDTV"
    feed: str = 'https://feeds.feedburner.com/ndtvnews-top-stories'
    country = Country.in_
