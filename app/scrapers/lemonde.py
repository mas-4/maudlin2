from app.scraper import FeedScraper
from app.utils.constants import Country


class LeMonde(FeedScraper):
    url: str = 'https://www.lemonde.fr/en'
    agency: str = "Le Monde"
    feed: str = 'https://www.lemonde.fr/en/rss/une.xml'
    country: Country = Country.fr
