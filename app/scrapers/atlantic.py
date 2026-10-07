from app.scraper import FeedScraper


class Atlantic(FeedScraper):
    url: str = 'https://www.theatlantic.com/'
    agency: str = "The Atlantic"
    feed: str = 'https://www.theatlantic.com/feed/all/'
