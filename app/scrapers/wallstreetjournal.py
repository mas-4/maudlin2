from app.scraper import FeedScraper


class WallStreetJournal(FeedScraper):
    url: str = 'https://www.wsj.com/'
    agency: str = "The Wall Street Journal"
    feed: str = 'https://feeds.content.dowjones.io/public/rss/RSSUSnews'
