from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class MarketWatch(FeedScraper):
    url: str = 'https://www.marketwatch.com/'
    agency: str = "MarketWatch"
    feed: str = 'https://feeds.content.dowjones.io/public/rss/mw_topstories'
