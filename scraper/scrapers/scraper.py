import time
from abc import ABC, abstractmethod
from threading import Thread

import requests as rq
from bs4 import BeautifulSoup as Soup
from nltk.sentiment import SentimentIntensityAnalyzer

from scraper.config import Config
from scraper.logger import get_logger
from scraper.models import Session, Article, Agency

logger = get_logger(__name__)


class Scraper(ABC, Thread):
    agency = ''
    url = ''

    def __init__(self):
        super().__init__()
        if not self.agency:
            raise ValueError("Agency name must be set")
        if not self.url:
            raise ValueError("URL must be set")
        self.downstream = []
        self.done = False
        self.results = []
        with Session() as session:
            agency = session.query(Agency).filter_by(name=self.agency).first()
            if not agency:
                agency = Agency(name=self.agency, url=self.url)
                session.add(agency)
                session.commit()
            self.agency_id = agency.id

    @abstractmethod
    def setup(self, soup: Soup):
        pass

    @abstractmethod
    def consume(self, page: Soup, href: str, title: str) -> bool:
        pass

    def process(self):
        sid = SentimentIntensityAnalyzer()
        for result in self.results:
            result.update({f"art{k}": v for k, v in sid.polarity_scores(result['body']).items()})
            result.update({f"head{k}": v for k, v in sid.polarity_scores(result['title']).items()})
            logger.info(f"Summary: {result}")
            with Session() as session:
                article = Article(**result, agency_id=self.agency_id)
                session.add(article)
                session.commit()

    @staticmethod
    def get_page(url: str):
        response = rq.get(url)
        if not response.ok:
            raise ValueError("Bad response")
        else:
            logger.info(f"Downloaded {url}")
        return Soup(response.content, 'lxml')

    def run(self):
        self.setup(self.get_page(self.url))
        while self.downstream:
            href, title = self.downstream.pop()
            with Session() as session:
                if session.query(Article).filter_by(url=href).first():
                    continue
            try:
                time.sleep(Config.time_between_requests())  # we sleep before a query
                page = self.get_page(href)
            except ValueError:
                self.downstream.remove((href, title))
                continue
            self.consume(page, title, href)
            if self.results:
                self.process()

        self.done = True
