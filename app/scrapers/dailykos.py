from app.scraper import FeedScraper


class DailyKos(FeedScraper):
    url: str = 'https://www.dailykos.com'
    agency: str = "The Daily Kos"
    feed: str = 'https://www.dailykos.com/blogs/main.rss'
