from app.scraper import FeedScraper
from app.utils.constants import Country


class IndiaTimes(FeedScraper):
    url: str = 'https://www.indiatimes.com'
    agency: str = "India Times"
    feed: str = 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'
    country = Country.in_
