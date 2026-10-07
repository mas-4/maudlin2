from app.scraper import FeedScraper


class StarTribune(FeedScraper):
    url: str = 'https://www.startribune.com'
    agency: str = "Star Tribune"
    feed: str = 'https://www.startribune.com/rss/'
