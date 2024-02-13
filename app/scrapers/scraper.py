import traceback as tb
from abc import ABC, abstractmethod
from collections import namedtuple
from threading import Thread, Lock

import requests as rq
from bs4 import BeautifulSoup as Soup
from nltk.sentiment import SentimentIntensityAnalyzer

from app.constants import Credibility, Bias, Country
from app.dayreport import DayReport
from app.logger import get_logger
from app.models import Session, Article, Agency, Headline

logger = get_logger(__name__)


ArticlePair = namedtuple('ArticlePair', ['href', 'title'])
STRIPS = ['\xad', '\xa0', '\n', '\t', '\r']


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
        self.articles = 0
        self.headlines = 0
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

    def process(self, art_pair: ArticlePair):
        sid: SentimentIntensityAnalyzer = SentimentIntensityAnalyzer()
        with Session() as session, self.sql_lock:
            results = {f"head{k}": v for k, v in sid.polarity_scores(art_pair.title).items()}
            results['title'] = art_pair.title

            if (article := session.query(Article).filter_by(url=art_pair.href).first()) is None:
                article = Article(url=art_pair.href, agency_id=self.agency_id)
                session.add(article)
                session.commit()
                logger.info(f"Added to database: %r", article)
                self.articles += 1

            session.add(headline := Headline(**results, article_id=article.id))
            session.commit()
            logger.info(f"Added to database: %r", headline)
            self.headlines += 1

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
            headlines = s.query(Headline).filter(Headline.title.in_(titles))
            for headline in headlines:
                headline.update_last_accessed()
                headline.article.update_last_accessed()
                logger.info("Headline already exists, updating last_accessed: %r", headline)
            s.commit()
            self.downstream = list(set(self.downstream) - set((headline.article.url, headline.title) for headline in headlines))

    def run(self):
        self.run_setup()
        self.run_processing()
        self.dayreport.headlines(self.headlines)
        self.dayreport.articles(self.articles)
        logger.info("Done with %s, added %d articles and %d headlines", self.agency, self.articles, self.headlines)
        self.done = True

    @staticmethod
    def strip(text: str):
        for strip in STRIPS:
            text = text.replace(strip, '')
        return text

    def run_processing(self):
        while self.downstream:
            href, title = self.downstream.pop()
            title = self.strip(title)
            art_pair = ArticlePair(href, title)
            try:
                self.process(art_pair)
            except Exception as e:  # noqa
                Session.rollback()
                msg = f"Failed to process link: {art_pair}: {e}"
                self.dayreport.add_exception(msg, tb.format_exc())
                logger.exception(msg)

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
