from bs4 import BeautifulSoup as Soup

from app import sinclair
from app.scraper import Scraper


class NationalDesk(Scraper):
    """Sinclair's national news (on air as The National News Desk), whose pieces its local stations run as their own.
    An ordinary outlet; its homepage is also kept as Sinclair sightings, to tell which station headlines are its
    pieces (app/sinclair.py)."""
    url: str = 'https://thenationaldesk.com/'
    agency: str = sinclair.NATIONAL_DESK

    def setup(self, soup: Soup):
        items = sinclair.national_desk_items(soup, self.url)
        self.sightings = [(url, text) for url, text, _ in items]
        self.downstream.extend((url, tag) for url, _, tag in items)

    def post_run(self):
        super().post_run()
        sinclair.record(self.agency_id, getattr(self, 'sightings', []))
