from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class WallStreetJournal(FeedScraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.wsj.com/'
    agency: str = "The Wall Street Journal"
    feed: str = 'https://feeds.content.dowjones.io/public/rss/RSSUSnews'
