from app.scraper import FeedScraper


class MarketWatch(FeedScraper):
    url: str = 'https://www.marketwatch.com/'
    agency: str = "MarketWatch"
    feed: str = 'https://feeds.content.dowjones.io/public/rss/mw_topstories'
