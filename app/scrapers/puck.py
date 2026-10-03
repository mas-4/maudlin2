from app.scraper import FeedScraper


class Puck(FeedScraper):
    url: str = 'https://puck.news/'
    agency: str = "Puck"
    feed: str = 'https://puck.news/feed/'
