from app.scraper import FeedScraper


class RealClearPolitics(FeedScraper):
    url: str = 'https://www.realclearpolitics.com'
    agency: str = "Real Clear Politics"
    feed: str = 'https://www.realclearpolitics.com/index.xml'
