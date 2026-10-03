from app.scraper import GoogleNewsScraper
from app.utils.constants import Bias, Credibility, Country


class Reuters(GoogleNewsScraper):
    """Reuters' front page kept timing out in Selenium and it has no public feed, so we read it through Google News."""
    bias = Bias.unbiased
    credibility = Credibility.very_high
    url: str = 'https://www.reuters.com/'
    agency: str = "Reuters"
    country = Country.gb
    site = 'reuters.com'
    suffix = ' - Reuters'
