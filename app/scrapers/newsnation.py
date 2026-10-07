from app.scraper import FeedScraper


class NewsNation(FeedScraper):
    url: str = 'https://www.newsnationnow.com/'
    agency: str = "News Nation"
    feed: str = 'https://www.newsnationnow.com/feed/'
