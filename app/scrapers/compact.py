from app.scraper import FeedScraper


class Compact(FeedScraper):
    url: str = 'https://www.compactmag.com/'
    agency: str = "Compact"
    feed: str = 'https://www.compactmag.com/rss/'
