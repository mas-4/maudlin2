from app.scraper import FeedScraper


class AmericanProspect(FeedScraper):
    url: str = 'https://prospect.org/'
    agency: str = "The American Prospect"
    feed: str = 'https://prospect.org/feed/'
