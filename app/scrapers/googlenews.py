from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility


class GoogleNews(FeedScraper):
    bias = Bias.left_center  # really? Isn't it an algorithm?
    credibility = Credibility.mostly_factual
    url: str = 'https://news.google.com/home?hl=en-US&gl=US&ceid=US:en'
    agency: str = "Google News"
    feed: str = 'https://news.google.com/rss'
