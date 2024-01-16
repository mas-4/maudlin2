import time
from threading import Thread

import requests as rq
from bs4 import BeautifulSoup as Soup

from scraper.config import Config
from scraper.logger import get_logger

logger = get_logger(__name__)


class CNNScraper(Thread):
    def __init__(self):
        super().__init__()
        self.url = 'https://lite.cnn.com/'
        self.downstream = []
        self.done = False

    def setup(self):
        response = rq.get(self.url)
        soup = Soup(response.content, 'lxml')
        for li in soup.find_all('li', class_='card--lite'):
            a = li.find('a')
            href = self.url + a.get('href')[1:]
            title = a.text.strip()
            self.downstream.append((href, title))

    def consume(self):
        if not self.downstream:
            self.done = True
            return

        href, title = self.downstream.pop()
        response = rq.get(href)
        if not response.ok:
            print("Error: ", response.status_code)
            return
        soup = Soup(response.content, 'lxml')
        story = []
        for p in soup.find('article').find_all('p'):
            story.append(p.text.strip())
        logger.info(f"Title: {title}")
        logger.info(f"URL: {href}")
        logger.info(f"Story: {' '.join(story)}")

    def run(self):
        self.setup()
        while not self.done:
            self.consume()
            time.sleep(Config.time_between_requests())
