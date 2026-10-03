from app.scraper import FeedScraper


class Zeteo(FeedScraper):
    url: str = 'https://zeteo.com/'
    agency: str = "Zeteo"
    feed: str = 'https://zeteo.com/feed'
