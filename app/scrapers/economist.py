from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class Economist(FeedScraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.economist.com'
    agency: str = "The Economist"
    feed: str = 'https://www.economist.com/latest/rss.xml'
    country: Country = Country.gb
