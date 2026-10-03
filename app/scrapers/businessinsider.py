from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class BusinessInsider(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.businessinsider.com'
    agency: str = "Business Insider"
    feed: str = 'https://feeds.businessinsider.com/custom/all'
