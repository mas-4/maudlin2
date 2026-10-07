from app.scraper import FeedScraper


class Salon(FeedScraper):
    url: str = 'https://www.salon.com'
    agency: str = "Salon"
    feed: str = 'https://www.salon.com/feed/'
