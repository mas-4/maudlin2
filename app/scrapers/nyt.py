from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class NYT(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.nytimes.com/'
    agency: str = "New York Times"
    feed: str = 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml'
