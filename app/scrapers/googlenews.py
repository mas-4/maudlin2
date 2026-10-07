from app.scraper import FeedScraper


class GoogleNews(FeedScraper):
    url: str = 'https://news.google.com/home?hl=en-US&gl=US&ceid=US:en'
    agency: str = "Google News"
    feed: str = 'https://news.google.com/rss'
