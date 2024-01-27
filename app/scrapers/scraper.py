import re
import time
from abc import ABC, abstractmethod
from threading import Thread

import requests as rq
from bs4 import BeautifulSoup as Soup
from nltk.sentiment import SentimentIntensityAnalyzer

from app.config import Config
from app.constants import Credibility, Bias
from app.logger import get_logger
from app.models import Session, Article, Agency

logger = get_logger(__name__)


class Scraper(ABC, Thread):
    agency: str = ''
    url: str = ''
    bias: Bias = None
    credibility: Credibility = None
    strip: list[str] = []

    def __init__(self):
        super().__init__()
        if not self.agency:
            raise ValueError("Agency name must be set")
        if not self.url:
            raise ValueError("URL must be set")
        self.downstream: list[tuple[str, str]] = []
        self.done: bool = False
        self.results: list[dict[str, str]] = []
        with Session() as session:
            agency = session.query(Agency).filter_by(name=self.agency).first()
            if not agency:
                agency = Agency(name=self.agency, url=self.url)
                agency.bias = self.bias
                agency.credibility = self.credibility
                session.add(agency)
                session.commit()
            self.agency_id = agency.id

    @abstractmethod
    def setup(self, soup: Soup):
        pass

    @abstractmethod
    def consume(self, page: Soup, href: str, title: str) -> bool:
        pass

    def strip_text(self, text: str) -> str:
        for regex in self.strip:
            text = re.sub(regex, '', text)
        return text

    def process(self):
        sid: SentimentIntensityAnalyzer = SentimentIntensityAnalyzer()
        for result in self.results:
            result['body'] = self.strip_text(result['body'])
            result.update({f"art{k}": v for k, v in sid.polarity_scores(result['body']).items()})
            result.update({f"head{k}": v for k, v in sid.polarity_scores(result['title']).items()})
            with Session() as session:
                article = Article(**result, agency_id=self.agency_id)
                session.add(article)
                session.commit()
                logger.info(f"Adding to database: %s", article)
        self.results = []

    @staticmethod
    def get_page(url: str):
        response: rq.Response = rq.get(url)
        if not response.ok:
            raise ValueError("Bad response")
        else:
            logger.info(f"Downloaded {url}")
        return Soup(response.content, 'lxml')

    def run(self):
        self.setup(self.get_page(self.url))
        while self.downstream:
            href, title = self.downstream.pop()
            with Session() as s:
                if article := s.query(Article).filter_by(url=href).first():
                    logger.info("Article already exists, updating last_accessed: %s", article)
                    article.update_last_accessed()
                    s.commit()
                    continue
            try:
                time.sleep(Config.time_between_requests())  # we sleep before a query
                page = self.get_page(href)
            except ValueError:
                continue
            self.consume(page, href, title)
            self.process()

        self.done = True
