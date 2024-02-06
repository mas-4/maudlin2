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

STRIPS = [
    "News Digital",
    "News",
    "Getty Images", "Getty",
    "Refinitiv", "Lipper", 
]


class Scraper(ABC, Thread):
    agency: str = ''
    url: str = ''
    bias: Bias = None
    credibility: Credibility = None
    strip: list[str] = []
    headers: dict[str, str] = {}
    parser: str = 'lxml'

    def __init__(self):
        super().__init__()
        self.added = 0
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
        self.strip.extend(STRIPS)

    @abstractmethod
    def setup(self, soup: Soup):
        pass

    @abstractmethod
    def consume(self, page: Soup, href: str, title: str) -> bool:
        pass

    def strip_text(self, text: str) -> str:
        for regex in self.strip:
            text = re.sub(regex, '', text)
        re.sub(r'\s+', ' ', text)
        re.sub('  +', ' ', text)
        re.sub('\n\n', '\n', text)
        return text

    def process(self):
        sid: SentimentIntensityAnalyzer = SentimentIntensityAnalyzer()
        with Session() as session:
            for result in self.results:
                result['body'] = self.strip_text(result['body'])
                if Config.dev_mode:
                    logger.debug("%s", result['body'])
                result.update({f"art{k}": v for k, v in sid.polarity_scores( result['body']).items()})
                result.update({f"head{k}": v for k, v in sid.polarity_scores(result['title']).items()})
                article = Article(**result, agency_id=self.agency_id)
                session.add(article)
                session.commit()
                logger.info(f"Adding to database: %s", article)
                self.added += 1
        self.results = []

    def add_stub(self, href: str, title: str):
        with Session() as session:
            session.add(Article(title=title, url=href, agency_id=self.agency_id, failure=True))
            session.commit()

    def get_page(self, url: str):
        response: rq.Response = rq.get(url, headers=self.headers)
        if not response.ok:
            raise ValueError("Bad response")
        else:
            logger.info(f"Downloaded {url}")
        return Soup(response.content, self.parser)

    def run(self):
        self.setup(self.get_page(self.url))
        while self.downstream:
            href, title = self.downstream.pop()
            # todo this can be a single query to filter the articles by just querying for all urls
            # todo change the filtration method to be based on headline?
            with Session() as s:
                if article := s.query(Article).filter_by(url=href).first():
                    logger.info("Article already exists, updating last_accessed: %s", article)
                    article.update_last_accessed()
                    s.commit()
                    continue
            time.sleep(Config.time_between_requests())  # we sleep before a query
            try:
                logger.info("%d articles left to check", len(self.downstream))
                page = self.get_page(href)
                self.consume(page, href, title)
                self.process()
            except:  # noqa
                logger.exception("Failed to get page: %s", (href, title))
                self.add_stub(href, title)

        self.done = True
        logger.info("Added %d articles to %s", self.added, self.agency)
