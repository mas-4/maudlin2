from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class Telegraph(FeedScraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://www.telegraph.co.uk/us'
    agency: str = "The Telegraph"
    feed: str = 'https://www.telegraph.co.uk/rss.xml'
    country: Country = Country.gb
