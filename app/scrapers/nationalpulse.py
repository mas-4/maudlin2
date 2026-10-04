from app.scraper import FeedScraper


class NationalPulse(FeedScraper):
    url: str = 'https://thenationalpulse.com/'
    agency: str = "The National Pulse"
    feed: str = 'https://thenationalpulse.com/feed/'
