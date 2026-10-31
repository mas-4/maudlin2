from app.scraper import GoogleNewsScraper
from app.utils.constants import Country


class OneAmericaNewsNetwork(GoogleNewsScraper):
    """OAN's whole site, its feed too, has answered with a Cloudflare challenge (403) since Oct 31, 2026"""
    url: str = 'https://www.oann.com'
    agency: str = "One America News Network"
    country: str = Country.us
    site = 'oann.com'
    suffix = ' - One America News Network'
