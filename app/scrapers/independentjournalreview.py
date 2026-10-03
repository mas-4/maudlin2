from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class IndependentJournalReview(FeedScraper):
    url: str = 'https://ijr.com/'
    agency: str = "Independent Journal Review"
    feed: str = 'https://ijr.com/feed/'
