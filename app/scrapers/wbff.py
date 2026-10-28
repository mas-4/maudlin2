from app.sinclair import StationScraper


class WBFF(StationScraper):
    """WBFF, Baltimore's Fox station (FOX45), in Sinclair's home market; Wikipedia lists it as run by Sinclair under
    an operating agreement. Research only (app/sinclair.py)."""
    url: str = 'https://foxbaltimore.com/'
    agency: str = "WBFF Baltimore"
    market: str = 'Baltimore'
