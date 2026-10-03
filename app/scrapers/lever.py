from app.scraper import FeedScraper


class Lever(FeedScraper):
    url: str = 'https://www.levernews.com/'
    agency: str = "The Lever"
    feed: str = 'https://www.levernews.com/rss/'
