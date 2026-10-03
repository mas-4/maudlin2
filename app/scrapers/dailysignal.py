from app.scraper import FeedScraper


class DailySignal(FeedScraper):
    url: str = 'https://www.dailysignal.com/'
    agency: str = "The Daily Signal"
    feed: str = 'https://www.dailysignal.com/feed/'
