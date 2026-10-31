from app.scraper import FeedScraper


class Forbes(FeedScraper):
    """Forbes's front page has answered 403 with a script check since Oct 27, 2026; its own feed still answers. The
    feed is every new post, contributors' too, not the editors' front page"""
    url: str = 'https://www.forbes.com/'
    agency: str = "Forbes"
    feed: str = 'https://www.forbes.com/business/feed/'
