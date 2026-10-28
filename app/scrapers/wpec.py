from app.sinclair import StationScraper


class WPEC(StationScraper):
    """WPEC, West Palm Beach's CBS station (CBS12), owned by Sinclair since 2012. Research only (app/sinclair.py)."""
    url: str = 'https://cbs12.com/'
    agency: str = "WPEC West Palm Beach"
    market: str = 'West Palm Beach'
