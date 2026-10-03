from app.scraper import FeedScraper


class NationalReview(FeedScraper):
    # Was a Selenium scraper that timed out; the RSS feed is quicker and steadier
    url: str = 'https://www.nationalreview.com'
    agency: str = "National Review"
    feed: str = 'https://www.nationalreview.com/feed/'
