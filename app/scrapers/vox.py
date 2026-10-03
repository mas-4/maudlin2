from app.scraper import FeedScraper


class Vox(FeedScraper):
    # The homepage stopped matching the old link pattern (one link found on Oct 3, 2026); its Atom feed is the
    # latest stories
    url: str = 'https://www.vox.com/'
    agency: str = "Vox"
    feed: str = 'https://www.vox.com/rss/index.xml'
