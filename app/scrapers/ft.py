from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class FT(FeedScraper):
    url: str = 'https://www.ft.com'
    agency: str = "Financial Times"
    feed: str = 'https://www.ft.com/rss/home'
    country = Country.gb
