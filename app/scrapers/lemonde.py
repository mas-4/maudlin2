from app.scraper import FeedScraper
from app.utils.constants import Bias, Credibility, Country


class LeMonde(FeedScraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.lemonde.fr/en'
    agency: str = "Le Monde"
    feed: str = 'https://www.lemonde.fr/en/rss/une.xml'
    country: Country = Country.fr
