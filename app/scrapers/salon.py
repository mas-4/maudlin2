from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class Salon(FeedScraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.salon.com'
    agency: str = "Salon"
    feed: str = 'https://www.salon.com/feed/'
