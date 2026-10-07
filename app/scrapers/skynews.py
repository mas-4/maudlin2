from app.scraper import FeedScraper
from app.utils.constants import Country


class SkyNews(FeedScraper):
    url: str = 'https://news.sky.com'
    agency: str = "Sky News"
    feed: str = 'https://feeds.skynews.com/feeds/rss/home.xml'
    country: str = Country.gb
