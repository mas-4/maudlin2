import re
import time
import traceback as tb
from abc import ABC, abstractmethod
from threading import Thread, Lock

import requests as rq
from bs4 import BeautifulSoup as Soup
from nltk.sentiment import SentimentIntensityAnalyzer

from app.config import Config
from app.constants import Credibility, Bias, Country
from app.logger import get_logger
from app.models import Session, Article, Agency
from app.dayreport import DayReport

logger = get_logger(__name__)

STRIPS = [
    "News Digital",
    "News",
    "Getty Images", "Getty",
    "Refinitiv", "Lipper",
    "Associated Press", "AP",
    "AP Images",
]


class Scraper(ABC, Thread):
    agency: str = ''
    url: str = ''
    bias: Bias = None
    credibility: Credibility = None
    headers: dict[str, str] = {}
    parser: str = 'lxml'
    country = Country.us
    day_lock = Lock()
    sql_lock = Lock()

    def __init__(self):
        super().__init__()
        self.added = 0
        if not self.agency:
            raise ValueError("Agency name must be set")
        if not self.url:
            raise ValueError("URL must be set")
        if self.bias is None or self.credibility is None:
            raise ValueError("Bias and credibility must be set")
        self.downstream: list[tuple[str, str]] = []
        self.done: bool = False
        self.results: list[dict[str, str]] = []
        with Session() as session, self.sql_lock:
            agency = session.query(Agency).filter_by(name=self.agency).first()
            if not agency:
                agency = Agency(name=self.agency, url=self.url)
            agency.bias = self.bias
            agency.credibility = self.credibility
            agency.country = self.country
            if not agency.id:
                session.add(agency)
            session.commit()
            self.agency_id = agency.id
        self.dayreport = DayReport(self.agency)

    @abstractmethod
    def setup(self, soup: Soup):
        pass

    def process(self):
        sid: SentimentIntensityAnalyzer = SentimentIntensityAnalyzer()
        with Session() as session, self.sql_lock:
            for result in self.results:
                result.update({f"head{k}": v for k, v in sid.polarity_scores(result['title']).items()})
                session.add(article := Article(**result, agency_id=self.agency_id))
                session.commit()
                logger.info(f"Adding to database: %r", article)
                self.added += 1
        self.results = []

    def add_stub(self, href: str, title: str):
        with Session() as session, self.sql_lock:
            session.add(Article(title=title, url=href, agency_id=self.agency_id, failure=True))
            session.commit()

    def get_page(self, url: str):
        response: rq.Response = rq.get(url, headers=self.headers)
        if not response.ok:
            raise ValueError("Bad response")
        else:
            logger.info(f"Downloaded {url}")
        return Soup(response.content, self.parser)

    def filter_seen(self):
        self.downstream = list(filter(lambda x: x[1], set(self.downstream)))  # no empties and no dupes
        with Session() as s, self.sql_lock:
            titles = [x[1] for x in self.downstream]
            articles = s.query(Article).filter(Article.title.in_(titles))
            for article in articles:
                article.update_last_accessed()
                logger.info("Article already exists, updating last_accessed: %r", article)
            s.commit()
            self.downstream = list(set(self.downstream) - set((article.url, article.title) for article in articles))

    def run(self):
        self.run_setup()
        self.run_processing()
        self.dayreport.added(self.added)
        logger.info("Done with %s, added %d articles", self.agency, self.added)
        self.done = True

    def run_processing(self):
        while self.downstream:
            href, title = self.downstream.pop()
            try:
                self.results.append({'title': title, 'url': href})
                self.process()
            except Exception as e:  # noqa
                Session.rollback()
                msg = f"Failed to get page: {(href, title)}: {e}"
                self.dayreport.add_exception(msg, tb.format_exc())
                logger.exception(msg)
                self.add_stub(href, title)

    def run_setup(self):
        try:
            self.setup(self.get_page(self.url))
            self.filter_seen()
        except Exception as e:  # noqa
            Session.rollback()
            msg = f"Failed to setup: {e}"
            logger.exception(msg)
            self.dayreport.add_exception(msg, tb.format_exc())
            raise
