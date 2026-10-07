from app.scraper import FeedScraper


class Politico(FeedScraper):
    url: str = 'https://www.politico.com'
    agency: str = "Politico"
    feed: str = 'https://rss.politico.com/politics-news.xml'
