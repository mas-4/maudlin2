from app.scraper import FeedScraper


class WesternJournal(FeedScraper):
    url: str = 'https://www.westernjournal.com/'
    agency: str = "The Western Journal"
    feed: str = 'https://www.westernjournal.com/feed/'
