from app.scraper import FeedScraper


class TheFreePress(FeedScraper):
    url: str = 'https://www.thefp.com/'
    agency: str = "The Free Press"
    feed: str = 'https://www.thefp.com/feed'
