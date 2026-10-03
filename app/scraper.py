import html
import os
import time
import warnings
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

from app.analysis import metrics, newsfilter
from app.analysis.preprocessing import preprocess, extract_text
from app.models import Session, Article, Agency, Headline, SqlLock
from app.utils import Config, Credibility, Bias, Country, Constants, get_logger

logger = get_logger(__name__)

ArticleTuple = namedtuple('ArticlePair', ['href', 'raw', 'title', 'processed', 'pos', 'news_score', 'event_score',
                                           'loaded_score', 'emotion', 'emotion_ranks', 'scored_by', 'scored_at',
                                           'affected'])


class Scraper(ABC, Thread):
    agency: str = ''
    url: str = ''
    headers: dict[str, str] = {}
    parser: str = 'lxml'
    country = Country.us
    sql_lock = SqlLock

    def __repr__(self):
        return f'(Scraper: {self.agency})'

    def __str__(self):
        return self.__repr__()

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
        self.downstream: list[tuple[str, Tag]] = []
        self.prefiltered = []
        self.done: bool = False
        self.results: list[dict[str, str]] = []
        with Session() as session, self.sql_lock:
            agency = session.query(Agency).filter_by(url=self.url).first()
            if not agency:
                agency = Agency(url=self.url)
            agency.name = self.agency
            agency.country = self.country
            if not agency.id:
                # Ratings come from ratings.csv (app/ratings.py); a new outlet starts unrated until it's added there
                agency._bias, agency._credibility, agency.lean_rated = 0, 0, False  # noqa prot attr
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
            with warnings.catch_warnings(action="ignore"):
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
        # Finding nothing means the scraper is broken (blocked, or the page changed); finding headlines but keeping
        # none of them usually means the parser is grabbing the wrong elements. Both need a look.
        bugle = logger.warning if not self.found or not self.articles + self.headlines + self.updated else logger.info
        bugle("%s: %d found, added %d articles, %d headlines, updated %d in %f seconds with a mean time of %f",
              self.agency, self.found, self.articles, self.headlines, self.updated, runtime, meantime)

    def process_dataframe(self, downstream):
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
        df['title'] = df['raw'].apply(extract_text)
        logger.debug("Extracted text in %f seconds", time.time() - t)

        t = time.time()
        df['word_count'] = df['title'].str.split().str.len()
        # Short strings are navigation ("Read More", "OPINION"), not headlines
        df.drop(df[df['word_count'] < Constants.Thresholds.min_headline_words].index, inplace=True)
        # ...and long strings are a summary that came along with the headline, a scraper bug to fix, not a headline
        too_long = df['word_count'] > Constants.Thresholds.max_headline_words
        if too_long.any():
            logger.warning("%s: dropped %d headlines over %d words, its parser may be grabbing summaries",
                           self.agency, too_long.sum(), Constants.Thresholds.max_headline_words)
        df.drop(df[too_long].index, inplace=True)
        # Text repeated all over one page is chrome ("Leave a Comment", section names), not a headline
        repeats = df.groupby('title')['title'].transform('size')
        df.drop(df[repeats >= Constants.Thresholds.page_repeat_limit].index, inplace=True)
        logger.debug("Dropping short and repeated headlines in %f seconds", time.time() - t)

        t = time.time()
        df['processed'] = df['title'].apply(preprocess)
        # Headlines without processed text are not headlines
        df.drop(df[df['processed'].isnull()].index, inplace=True)
        logger.debug("Dropping headlines without processed text in %f seconds", time.time() - t)
        return df

    def prefilter(self, downstream):
        df = self.process_dataframe(downstream)
        # A page often links the same story more than once; keep its first (highest) appearance. The session doesn't
        # autoflush, so process() can't see rows added earlier in the same batch and would save each copy.
        df = df.drop_duplicates('processed')
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

        # Only headlines we haven't seen before need judging
        judged = pd.DataFrame(newsfilter.assess(df['title'].tolist(), self.agency), index=df.index,
                              columns=['news_score', 'event_score', 'loaded_score', 'emotion', 'emotion_ranks',
                                       'scored_by', 'scored_at', 'affected'])
        df = df.join(judged)
        df['artpair'] = df.apply(lambda x: ArticleTuple(x['href'], x['raw'], x['title'], x['processed'], x['row'],
                                                        x['news_score'], x['event_score'], x['loaded_score'],
                                                        x['emotion'], x['emotion_ranks'], x['scored_by'],
                                                        x['scored_at'], x['affected']), axis=1)
        return dropped, df['artpair'].tolist()

    def run_processing(self):
        self.found = len(self.downstream)
        logger.info("Processing %s, %i upstream headlines", self.agency, self.found)
        t = time.time()
        dropped, prefiltered = self.prefilter(self.downstream)
        logger.info("Prefiltered %i headlines in %f seconds", dropped, time.time() - t)
        self.batch_articles = {}  # url -> Article added in this batch, which queries can't see until a flush
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

        article = self.batch_articles.get(art.href) or s.query(Article).filter_by(url=art.href).first()
        if article is None:
            article = Article(url=art.href, agency_id=self.agency_id)
            s.add(article)
            self.articles += 1
        self.batch_articles[art.href] = article

        article.update_last_accessed()  # if its new this does nothing, if it's not we need to do it!
        headline = Headline(
            title=art.title,
            raw=art.raw,
            processed=art.processed,
            position=art.pos,
            news_score=art.news_score,
            event_score=art.event_score,
            loaded_score=art.loaded_score,
            emotion=art.emotion if isinstance(art.emotion, str) else None,
            emotion_ranks=art.emotion_ranks if isinstance(art.emotion_ranks, str) else None,
            scored_by=art.scored_by if isinstance(art.scored_by, str) else None,
            scored_at=art.scored_at if isinstance(art.scored_at, dt) else None,
            affected=art.affected if isinstance(art.affected, str) else None,
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


class FeedScraper(Scraper):
    """Pulls headlines from an RSS or Atom feed. Subclasses only need to set `feed` alongside the usual metadata.
    `url` stays the homepage so the agency record and relative links don't change."""
    feed: str = ''
    parser: str = 'xml'

    def run_setup(self):
        if not self.feed:
            raise ValueError("Feed must be set")
        page = self.get_page(self.feed)
        if not page:
            return
        self.setup(page)

    def setup(self, soup: Soup):
        for item in soup.find_all(['item', 'entry']):
            title = item.find('title')
            link = item.find('link')
            if title is None or link is None:
                continue
            href = link.get('href') or link.get_text(strip=True)  # atom puts the url in href, rss in the text
            # An html-typed title arrives with its entities still encoded (Vox's "Here&#8217;s")
            text = html.unescape(title.get_text(strip=True))
            if href and text:
                self.downstream.append((href, text))


class GoogleNewsScraper(FeedScraper):
    """For outlets that block scrapers outright: their last day of stories through a Google News search feed.
    The links are Google redirects rather than the outlet's own urls, and the order is Google's, not the outlet's
    front page. Subclasses set `site` (e.g. 'apnews.com') and the `suffix` Google appends to titles."""
    site: str = ''
    suffix: str = ''

    @property
    def feed(self) -> str:
        return f'https://news.google.com/rss/search?q=site:{self.site}+when:1d&hl=en-US&gl=US&ceid=US:en'

    def setup(self, soup: Soup):
        super().setup(soup)
        self.downstream = [(href, title.removesuffix(self.suffix)) for href, title in self.downstream]


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

    def __repr__(self):
        return f'(SeleniumScraper: {self.agency})'

    def __str__(self):
        return self.__repr__()

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
