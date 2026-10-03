from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class DailyWire(FeedScraper):
    url: str = 'https://www.dailywire.com/'
    agency: str = "The Daily Wire"
    feed: str = 'https://www.dailywire.com/feeds/rss.xml'
