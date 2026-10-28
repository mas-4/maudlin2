from app.sinclair import StationScraper


class KUTV(StationScraper):
    """KUTV, Salt Lake City's CBS station (2News), owned by Sinclair since 2012. Research only (app/sinclair.py)."""
    url: str = 'https://kutv.com/'
    agency: str = "KUTV Salt Lake City"
    market: str = 'Salt Lake City'
