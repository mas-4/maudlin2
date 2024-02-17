import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Axios(Scraper):
    # todo: requires chrome headless and selenium
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.axios.com'
    agency: str = "Axios"
    header = """Host: www.axios.com
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0
Accept-Language: en-US,en;q=0.5
Connection: keep-alive
Cookie: ax=eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJhZWI2YTA0Zi1jNzliLTQzYWItYTA0MC0wOWZmOWUyYTQ0NjciLCJzdGF0dXMiOiIxIiwiZXhwIjoxNzM4OTUzNTc0fQ.6WYGI9Z_o4pSndm5VoQYcYJ2dMnCnF_2qouYRZVoNyYpVDYwxFFNOfCVZgMwosTxomvKY3RuqKV6YpZk3apolA; __cf_bm=ybByIU73MMfYTd9L1az2ap31aeB15Pxswg0r5kUMOjE-1708181545-1.0-AcqCOQpAEZwHYAP3tI80Zrr82G2bKmTGlD8c1Bn3ltka8Dl50A37OASG/hyijfzDqfL/Mbj/jZNgRxIQauqJIuU=; next-auth.csrf-token=2fdc6cba5bd0b9254056b703b395366a24ca8e0fc7b8639603ef55f1a1f916e1%7Cd785d2beed5ebb7377de598f1610e75575bf7e158ae7b6002d1a3e122c4d24d6; __Secure-next-auth.callback-url=https%3A%2F%2Fwww.axios.com"""
    headers = {key:val for key, val in [i.split(': ') for i in header.split('\n')]}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
