from app.scraper import FeedScraper


class IndependentJournalReview(FeedScraper):
    url: str = 'https://ijr.com/'
    agency: str = "Independent Journal Review"
    feed: str = 'https://ijr.com/feed/'
