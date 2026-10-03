from app.scraper import FeedScraper


class Mediaite(FeedScraper):
    url: str = 'https://www.mediaite.com/'
    agency: str = "Mediaite"
    feed: str = 'https://www.mediaite.com/feed/'
