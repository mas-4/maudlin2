from app.scraper import FeedScraper


class StraightArrowNews(FeedScraper):
    url: str = 'https://san.com/'
    agency: str = "Straight Arrow News"
    feed: str = 'https://san.com/feed/'
