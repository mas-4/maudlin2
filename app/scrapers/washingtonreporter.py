from app.scraper import FeedScraper


class WashingtonReporter(FeedScraper):
    url: str = 'https://www.washingtonreporter.news/'
    agency: str = "Washington Reporter"
    feed: str = 'https://www.washingtonreporter.news/feed/'
