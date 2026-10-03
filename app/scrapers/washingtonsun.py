from app.scraper import FeedScraper


class WashingtonSun(FeedScraper):
    url: str = 'https://www.washingtonsun.com/'
    agency: str = "The Washington Sun"
    feed: str = 'https://www.washingtonsun.com/index.rss'
