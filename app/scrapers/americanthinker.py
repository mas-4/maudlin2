from app.scraper import FeedScraper


class AmericanThinker(FeedScraper):
    url: str = 'https://www.americanthinker.com/'
    agency: str = "American Thinker"
    feed: str = 'https://feeds.feedburner.com/americanthinker'
