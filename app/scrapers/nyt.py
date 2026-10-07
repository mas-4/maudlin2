from app.scraper import FeedScraper


class NYT(FeedScraper):
    url: str = 'https://www.nytimes.com/'
    agency: str = "New York Times"
    feed: str = 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml'
