from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class BusinessInsider(FeedScraper):
    url: str = 'https://www.businessinsider.com'
    agency: str = "Business Insider"
    feed: str = 'https://feeds.businessinsider.com/custom/all'
