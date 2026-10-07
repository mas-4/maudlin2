from app.scraper import FeedScraper


class Semafor(FeedScraper):
    url: str = 'https://www.semafor.com'
    agency: str = "Semafor"
    feed: str = 'https://www.semafor.com/rss.xml'
