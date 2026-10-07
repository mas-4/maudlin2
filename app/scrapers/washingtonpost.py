from app.scraper import FeedScraper


class WashingtonPost(FeedScraper):
    url: str = 'https://www.washingtonpost.com'
    agency: str = "The Washington Post"
    feed: str = 'https://feeds.washingtonpost.com/rss/national'
