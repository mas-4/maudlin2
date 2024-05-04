import os
import time
from abc import ABC, abstractmethod
from collections import namedtuple
from datetime import datetime as dt
from threading import Thread, Lock

import pandas as pd
import pytz
import requests as rq
import validators
from bs4 import BeautifulSoup as Soup, Tag, NavigableString  # noqa not declared in __all__
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

from app.analysis import metrics
from app.analysis.preprocessing import preprocess
from app.models import Session, Article, Agency, Headline, SqlLock
from app.utils import Config, Credibility, Bias, Country, Constants, get_logger

logger = get_logger(__name__)

ArticleTuple = namedtuple('ArticlePair', ['href', 'raw', 'title', 'processed', 'pos'])


def extract_text(html_content):
    soup = Soup(html_content, 'html.parser')

    stack = [soup]

    def generate_text_elements(_stack):
        while _stack:
            current_element = _stack.pop()
            if isinstance(current_element, NavigableString):
                yield current_element.strip()
            else:
                _stack.extend(reversed(list(current_element.children)))

    return list(generate_text_elements(stack))


class Scraper(ABC, Thread):
    agency: str = ''
    url: str = ''
    bias: Bias = None
    credibility: Credibility = None
    headers: dict[str, str] = {}
    parser: str = 'lxml'
    country = Country.us
    sql_lock = SqlLock

    def __init__(self):
        super().__init__()
        self.success = False
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
        self.prefiltered = []
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

    @abstractmethod
    def setup(self, soup: Soup):
        pass

    def get_page(self, url: str):
        if not self.headers:
            self.headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

        try:
            response: rq.Response = self.rq.get(url, headers=self.headers, timeout=Config.timeout, verify=False)
        except Exception as e:  # noqa
            logger.error("Failed to get page: %s %s", url, e)
            return
        if not response.ok:
            logger.error("Bad response for %s: %s", url, response.status_code)
            return
        else:
            logger.info(f"Downloaded {url}")
        soup = Soup(response.content, self.parser)
        self.success = True
        return soup

    def run(self):
        self.run_setup()
        self.done = True

    def post_run(self):
        t = time.time()
        self.run_processing()
        runtime = time.time() - t
        meantime = 0
        if self.found:
            meantime = runtime / self.found
        # If we didn't got headlines but nothing processed we want to warn
        bugle = logger.info if not self.found or self.articles + self.headlines + self.updated else logger.warning
        bugle("%s: %d found, added %d articles, %d headlines, updated %d in %f seconds with a mean time of %f",
              self.agency, self.found, self.articles, self.headlines, self.updated, runtime, meantime)

    def prefilter(self, downstream):
        df = pd.DataFrame(downstream, columns=['href', 'raw'])
        df['raw'] = df['raw'].apply(str)

        df['row'] = df.index
        df['row'] = df['row'].astype(int)

        t = time.time()
        df['href'] = df['href'].apply(self.clean_href)
        df['validate'] = df['href'].apply(lambda x: bool(validators.url(x)))
        # Headlines with invalid urls are not headlines
        df.drop(df[df['validate'] == False].index, inplace=True)  # noqa
        logger.debug("Dropping headlines with invalid urls in %f seconds", time.time() - t)

        t = time.time()
        df['title'] = df['raw'].apply(lambda x: ' '.join(extract_text(str(x))))
        logger.debug("Extracted text in %f seconds", time.time() - t)

        t = time.time()
        df['word_count'] = df['title'].apply(lambda x: x.count(' '))
        # Headlines without spaces are not headlines
        df.drop(df[df['word_count'] == 0].index, inplace=True)
        logger.debug("Dropping headlines without spaces in %f seconds", time.time() - t)

        t = time.time()
        df['processed'] = df['title'].apply(preprocess)
        # Headlines without processed text are not headlines
        df.drop(df[df['processed'].isnull()].index, inplace=True)
        logger.debug("Dropping headlines without processed text in %f seconds", time.time() - t)

        with Session() as s:
            seen = s.query(Headline.processed, Headline.id, Article.id).join(Headline.article).filter(
                Headline.processed.in_(df['processed'].tolist())
            ).all()
            df['seen'] = df['processed'].isin([x[0] for x in seen])
            df.drop(df[df['seen'] == True].index, inplace=True)  # noqa
            dropped = len(seen)
            self.updated += dropped
            s.query(Headline).filter(Headline.id.in_([x[1] for x in seen])).update({'last_accessed': dt.now(pytz.UTC)})
            s.query(Article).filter(Article.id.in_([x[2] for x in seen])).update({'last_accessed': dt.now(pytz.UTC)})
            s.commit()

        df['artpair'] = df.apply(lambda x: ArticleTuple(x['href'], x['raw'], x['title'], x['processed'], x['row']),
                                 axis=1)
        return dropped, df['artpair'].tolist()

    def run_processing(self):
        self.found = len(self.downstream)
        logger.info("Processing %s, %i upstream headlines", self.agency, self.found)
        t = time.time()
        dropped, prefiltered = self.prefilter(self.downstream)
        logger.info("Prefiltered %i headlines in %f seconds", dropped, time.time() - t)
        with Session() as s:
            [self.process(s, art_pair) for art_pair in prefiltered]
            s.commit()

    def process(self, s, art: ArticleTuple):
        if (headline := s.query(Headline).filter(Headline.processed == art.processed).first()) is not None:
            # we're going to double-check this headline hasn't been seen before
            headline.update_last_accessed()
            headline.article.update_last_accessed()
            self.updated += 1
            return

        if (article := s.query(Article).filter_by(url=art.href).first()) is None:
            article = Article(url=art.href, agency_id=self.agency_id)
            s.add(article)
            self.articles += 1

        article.update_last_accessed()  # if its new this does nothing, if it's not we need to do it!
        headline = Headline(
            title=art.title,
            raw=art.raw,
            processed=art.processed,
            position=art.pos,
            article=article
        )
        s.add(headline)
        metrics.apply(headline, s)
        self.headlines += 1

    def clean_href(self, href):
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = self.url.strip('/') + href
        elif not href.startswith('http'):
            href = self.url.strip('/') + '/' + href
        return href.strip()

    def run_setup(self):
        page = self.get_page(self.url)
        if not page:
            return
        self.setup(page)


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
        self.success = False

    def get_page(self, url: str):
        try:
            t = time.time()
            soup = Soup(self.srs.get_html(url), self.parser)
            logger.info("Downloaded %s in %i seconds", url, time.time() - t)
            self.success = True
        except Exception as e:  # noqa
            logger.error("Failed to get page: %s %s", url, e)
            return
        return soup

    @abstractmethod
    def setup(self, soup: Soup):
        pass
