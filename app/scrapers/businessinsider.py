from app.scraper import FeedScraper


class BusinessInsider(FeedScraper):
    url: str = 'https://www.businessinsider.com'
    agency: str = "Business Insider"
    feed: str = 'https://feeds.businessinsider.com/custom/all'
