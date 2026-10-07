from app.scraper import FeedScraper


class DailyWire(FeedScraper):
    url: str = 'https://www.dailywire.com/'
    agency: str = "The Daily Wire"
    feed: str = 'https://www.dailywire.com/feeds/rss.xml'
