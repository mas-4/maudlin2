import re
import traceback as tb
from abc import ABC, abstractmethod
from collections import namedtuple
from threading import Thread, Lock

import requests as rq
import validators
from bs4 import BeautifulSoup as Soup
from nltk.sentiment import SentimentIntensityAnalyzer
from selenium.webdriver.firefox.options import Options
from selenium import webdriver

from app.constants import Credibility, Bias, Country
from app.dayreport import DayReport
from app.logger import get_logger
from app.models import Session, Article, Agency, Headline

logger = get_logger(__name__)


ArticlePair = namedtuple('ArticlePair', ['href', 'title'])
STRIPS = {'\xad': ' ', '\xa0': ' ', '\n': ' ', '\t': ' ', '\r': ' ', '  +': ' '}


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
        self.rq = rq.Session()
        self.articles = 0
        self.headlines = 0
        self.updated = 0
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
            agency = session.query(Agency).filter_by(url=self.url).first()
            if not agency:
                agency = Agency(url=self.url)
            agency.name = self.agency
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
        with Session() as s, self.sql_lock:
            if (headline := s.query(Headline).filter(Headline.title == art_pair.title).first()) is not None:
                # we're going to double-check this headline hasn't been seen before
                headline.update_last_accessed()
                headline.article.update_last_accessed()
                self.updated += 1
                s.commit()
                return

            results = {k: v for k, v in sid.polarity_scores(art_pair.title).items()}
            results['comp'] = results['compound']
            del results['compound']
            results['title'] = art_pair.title

            if (article := s.query(Article).filter_by(url=art_pair.href).first()) is None:
                article = Article(url=art_pair.href, agency_id=self.agency_id)
                s.add(article)
                s.commit()
                logger.debug(f"Added to database: %r", article)
                self.articles += 1

            article.update_last_accessed()  # if its new this does nothing, if it's not we need to do it!
            s.add(headline := Headline(**results, article_id=article.id))
            s.commit()
            logger.debug(f"Added to database: %r", headline)
            self.headlines += 1

    def get_page(self, url: str):
        try:
            response: rq.Response = self.rq.get(url, headers=self.headers)
        except Exception as e:  # noqa
            raise ValueError(f"Failed to get page: {url} {e}")
        if not response.ok:
            raise ValueError("Bad response for %s: %s" % (url, response.status_code))
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
                self.updated += 1
                logger.debug("Headline already exists, updating last_accessed: %r", headline)
            s.commit()
            self.downstream = list(set(self.downstream) - set((headline.article.url, headline.title) for headline in headlines))

    def run(self):
        self.run_setup()
        self.run_processing()
        self.dayreport.headlines(self.headlines)
        self.dayreport.articles(self.articles)
        logger.info("Done with %s, added %d articles and %d headlines, updated %d headlines",
                    self.agency, self.articles, self.headlines, self.updated)
        self.done = True

    @staticmethod
    def strip(text: str):
        for pattern, replacement in STRIPS.items():
            text = re.sub(pattern, replacement, text)
        return text

    def run_processing(self):
        while self.downstream:
            href, title = self.downstream.pop()
            if title.strip().count(' ') == 0:
                continue  # obviously a headline without spaces isn't a headline
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = self.url.strip('/') + href
            elif not href.startswith('http'):
                href = self.url.strip('/') + '/' + href
            href = href.strip()
            title = self.strip(title)
            art_pair = ArticlePair(href, title)
            try:
                if not (err := validators.url(art_pair.href)):
                    raise err
                self.process(art_pair)
            except Exception as e:  # noqa
                Session.rollback()
                msg = f"Failed to process link: {self.agency}: {art_pair} {e}"
                self.dayreport.add_exception(msg, tb.format_exc())
                logger.exception(msg)

    def run_setup(self):
        try:
            self.setup(self.get_page(self.url))
            self.filter_seen()
        except Exception as e:  # noqa
            Session.rollback()
            msg = f"Failed to setup: {e} for {self.url}"
            logger.exception(msg)
            self.dayreport.add_exception(msg, tb.format_exc())
            raise


class SeleniumResourceManager:
    _instance = None
    lock = Lock()
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            options = Options()
            options.add_argument("--headless")
            cls._instance._driver = webdriver.Firefox(options=options)
        return cls._instance

    def __del__(self):
        self.quit()

    def quit(self):
        self._driver.quit()

    def get_html(self, url):
        with self.lock:
            self._driver.get(url)
            return self._driver.page_source


class SeleniumScraper(Scraper):
    def __init__(self):
        super().__init__()
        self.srs = SeleniumResourceManager()
    def get_page(self, url: str):
        try:
            soup = Soup(self.srs.get_html(url), self.parser)
        except Exception as e:  # noqa
            raise ValueError(f"Failed to get page: {e}")
        return soup

    @abstractmethod
    def setup(self, soup: Soup):
        pass
