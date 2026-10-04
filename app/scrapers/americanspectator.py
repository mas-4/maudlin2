from app.scraper import FeedScraper


class AmericanSpectator(FeedScraper):
    url: str = 'https://spectator.org/'
    agency: str = "The American Spectator"
    feed: str = 'https://spectator.org/feed/'
