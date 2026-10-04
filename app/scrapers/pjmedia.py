from app.scraper import FeedScraper


class PJMedia(FeedScraper):
    url: str = 'https://pjmedia.com/'
    agency: str = "PJ Media"
    feed: str = 'https://pjmedia.com/feed'
