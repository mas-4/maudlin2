from app.scraper import FeedScraper


class WashingtonTimes(FeedScraper):
    """The front page has refused us (403) since Oct 22, 2026, whatever the user agent; the news feed answers"""
    url: str = 'https://www.washingtontimes.com/'
    agency: str = "The Washington Times"
    feed: str = 'https://www.washingtontimes.com/rss/headlines/news/'
