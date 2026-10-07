from app.scraper import FeedScraper


class Jacobin(FeedScraper):
    url: str = 'https://jacobin.com'
    agency: str = "Jacobin"
    feed: str = 'https://jacobin.com/feed'
