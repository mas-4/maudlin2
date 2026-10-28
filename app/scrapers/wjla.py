from app.sinclair import StationScraper


class WJLA(StationScraper):
    """WJLA-TV, Washington's ABC station (7News), owned by Sinclair since 2014. Research only (app/sinclair.py)."""
    url: str = 'https://wjla.com/'
    agency: str = "WJLA Washington"
    market: str = 'Washington, D.C.'
