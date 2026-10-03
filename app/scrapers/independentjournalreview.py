from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class IndependentJournalReview(FeedScraper):
    bias = Bias.right
    credibility = Credibility.mostly_factual
    url: str = 'https://ijr.com/'
    agency: str = "Independent Journal Review"
    feed: str = 'https://ijr.com/feed/'
