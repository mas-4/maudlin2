from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper, without
from app.utils.logger import get_logger

logger = get_logger(__name__)

# A card's photo or video is a link of its own whose text is the credit, a caption and the label on the photo
# ("• Analysis  Mark Felix/AFP/Getty Images"): about 420 were kept as headlines until Oct 28. The headline's own link
# never holds the media block, so without it a photo's link reads as nothing and is dropped.
PHOTO_PARTS = '.container__item-media-wrapper'


class CNN(Scraper):
    url: str = 'https://www.cnn.com'
    agency: str = "CNN"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-link-type': 'article'}):
            href = self.url + a['href']
            if 'cnn-underscored' in href:
                continue
            if '/wbd/' in href:
                continue
            self.downstream.append((href, without(a, PHOTO_PARTS)))
