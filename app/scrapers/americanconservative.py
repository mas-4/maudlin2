from app.scraper import FeedScraper


class AmericanConservative(FeedScraper):
    url: str = 'https://www.theamericanconservative.com/'
    agency: str = "The American Conservative"
    feed: str = 'https://www.theamericanconservative.com/feed/'
