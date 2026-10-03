from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class RealClearPolitics(FeedScraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.realclearpolitics.com'
    agency: str = "Real Clear Politics"
    feed: str = 'https://www.realclearpolitics.com/index.xml'
