from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class IndiaTimes(FeedScraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.indiatimes.com'
    agency: str = "India Times"
    feed: str = 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'
    country = Country.in_
