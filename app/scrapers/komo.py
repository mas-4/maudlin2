from app.sinclair import StationScraper


class KOMO(StationScraper):
    """KOMO-TV, Seattle's ABC station, owned by Sinclair since 2013. Research only (app/sinclair.py)."""
    url: str = 'https://komonews.com/'
    agency: str = "KOMO Seattle"
    market: str = 'Seattle'
