from app.scraper import GoogleNewsScraper
from app.utils.constants import Bias, Credibility


class AP(GoogleNewsScraper):
    """AP blocks scrapers outright, so we read it through Google News."""
    url: str = 'https://apnews.com/'
    agency: str = "AP"
    site = 'apnews.com'
    suffix = ' - AP News'
