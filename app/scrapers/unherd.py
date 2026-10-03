from app.scraper import FeedScraper
from app.utils.constants import Country


class UnHerd(FeedScraper):
    url: str = 'https://unherd.com/'
    agency: str = "UnHerd"
    feed: str = 'https://unherd.com/feed/'
    country = Country.gb
