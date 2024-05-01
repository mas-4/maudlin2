import os
import traceback as tb
from abc import ABC, abstractmethod
from collections import namedtuple
from threading import Thread, Lock

import requests as rq
import validators
from bs4 import BeautifulSoup as Soup, Tag, NavigableString  # noqa not declared in __all__
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

from app.analysis import metrics
from app.analysis.preprocessing import preprocess
from app.models import Session, Article, Agency, Headline, SqlLock
from app.utils import Config, Credibility, Bias, Country, Constants
from app.utils.logger import get_logger
from utils.dayreport import DayReport

logger = get_logger(__name__)

ArticleTuple = namedtuple('ArticlePair', ['href', 'raw', 'title', 'processed', 'pos'])


def extract_text(html_content):
    # Parse the HTML content using BeautifulSoup
    soup = Soup(html_content, 'lxml').find()

    # Initialize the stack with the root of the document
    stack = [soup]

    # List to hold all extracted texts
    extracted_texts = []

    # Process each element in the stack
    while stack:
        # Pop the top element from the stack
        current_element = stack.pop()

        # Check if current element has text and add it to the list
        if isinstance(current_element, NavigableString):
            extracted_texts.append(current_element.string.strip())
            continue

        # Add children of the current element to the stack
        for child in current_element.children:
            stack.append(child)

    return extracted_texts


class Scraper(ABC, Thread):
    agency: str = ''
    url: str = ''
    bias: Bias = None
    credibility: Credibility = None
    headers: dict[str, str] = {}
    parser: str = 'lxml'
    country = Country.us
    day_lock = Lock()
    sql_lock = SqlLock

    def __init__(self):
        super().__init__()
        self.rq = rq.Session()
        self.articles = 0
        self.headlines = 0
        self.updated = 0
        self.found = 0
        if not self.agency:
            raise ValueError("Agency name must be set")
        if not self.url:
            raise ValueError("URL must be set")
        if self.bias is None or self.credibility is None:
            raise ValueError("Bias and credibility must be set")
        self.downstream: list[tuple[str, Tag]] = []
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

    def process(self, art: ArticleTuple):
        with Session() as s, self.sql_lock:
            if (headline := s.query(Headline).filter(Headline.processed == art.processed).first()) is not None:
                # we're going to double-check this headline hasn't been seen before
                headline.update_last_accessed()
                headline.article.update_last_accessed()
                self.updated += 1
                s.commit()
                return

            if (article := s.query(Article).filter_by(url=art.href).first()) is None:
                article = Article(url=art.href, agency_id=self.agency_id)
                s.add(article)
                s.commit()
                logger.debug(f"Added to database: %r", article)
                self.articles += 1

            article.update_last_accessed()  # if its new this does nothing, if it's not we need to do it!
            headline = Headline(
                title=art.title,
                raw=art.raw,
                processed=art.processed,
                position=art.pos,
                article_id=article.id
            )
            s.add(headline)
            s.commit()
            logger.debug(f"Added to database: %r", headline)
            s.expunge(headline)
        metrics.apply(headline)
        self.headlines += 1

    def get_page(self, url: str):
        if not self.headers:
            self.headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

        try:
            response: rq.Response = self.rq.get(url, headers=self.headers, timeout=Config.timeout)
        except Exception as e:  # noqa
            raise ValueError(f"Failed to get page: {url} {e}")
        if not response.ok:
            raise ValueError("Bad response for %s: %s" % (url, response.status_code))
        else:
            logger.info(f"Downloaded {url}")
        return Soup(response.content, self.parser)

    def run(self):
        self.run_setup()
        self.run_processing()
        self.dayreport.headlines(self.headlines)
        self.dayreport.articles(self.articles)
        self.dayreport.updated(self.updated)
        # If we didn't get anything we want to warn!
        bugle = logger.info if self.articles + self.headlines + self.updated else logger.warning
        bugle("Done with %s, from %d found, added %d articles and %d headlines, updated %d headlines",
              self.agency, self.found, self.articles, self.headlines, self.updated)
        self.done = True

    def run_processing(self):
        self.found = len(self.downstream)
        logger.info("Processing %s, %i upstream headlines", self.agency, self.found)
        pos = 0
        while self.downstream:
            href, raw = self.downstream.pop()
            raw = str(raw)
            title = ' '.join(extract_text(raw))
            if title.strip().count(' ') == 0:
                continue  # obviously a headline without spaces isn't a headline
            art = ArticleTuple(self.clean_href(href).strip(), str(raw), title, preprocess(title), pos)
            if not art.processed:
                continue
            pos += 1
            try:
                if not (err := validators.url(art.href)):
                    raise err
                self.process(art)
            except Exception as e:  # noqa
                Session.rollback()
                msg = f"Failed to process link: {self.agency}: {art} {e}"
                self.dayreport.add_exception(msg, tb.format_exc())
                logger.exception(msg)

    def clean_href(self, href):
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = self.url.strip('/') + href
        elif not href.startswith('http'):
            href = self.url.strip('/') + '/' + href
        return href

    def run_setup(self):
        try:
            self.setup(self.get_page(self.url))
            # self.filter_seen()
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
            cls._instance._driver.set_page_load_timeout(Config.timeout)
        return cls._instance

    def __del__(self):
        self.quit()

    def quit(self):
        self._driver.quit()
        # force kill the driver
        os.system(f"kill -9 {self._driver.service.process.pid}")

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
            logger.info("Downloading %s...", url)
            soup = Soup(self.srs.get_html(url), self.parser)
            logger.info("Downloaded %s", url)
        except Exception as e:  # noqa
            raise ValueError(f"Failed to get page: {e}")
        return soup

    @abstractmethod
    def setup(self, soup: Soup):
        pass
