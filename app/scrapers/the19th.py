from app.scraper import FeedScraper


class The19th(FeedScraper):
    url: str = 'https://19thnews.org/'
    agency: str = "The 19th"
    feed: str = 'https://19thnews.org/feed/'
