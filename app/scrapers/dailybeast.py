from app.scraper import FeedScraper


class DailyBeast(FeedScraper):
    url: str = 'https://www.thedailybeast.com/'
    agency: str = "The Daily Beast"
    feed: str = 'https://www.thedailybeast.com/arc/outboundfeeds/rss/articles/'
