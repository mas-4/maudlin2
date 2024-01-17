import time
from threading import Thread

import requests as rq
from bs4 import BeautifulSoup as Soup

from scraper.config import Config
from scraper.logger import get_logger
from scraper.models import Session, Article, Agency
from nltk.sentiment.vader import SentimentIntensityAnalyzer

logger = get_logger(__name__)


class CNNScraper(Thread):
    def __init__(self):
        super().__init__()
        self.url = 'https://lite.cnn.com/'
        self.downstream = []
        self.done = False
        self.results = []
        self.agency = "CNN"
        with Session() as session:
            agency = session.query(Agency).filter_by(name=self.agency).first()
            if not agency:
                agency = Agency(name=self.agency, url=self.url)
                session.add(agency)
                session.commit()
            self.agency_id = agency.id

    def setup(self):
        response = rq.get(self.url)
        soup = Soup(response.content, 'lxml')
        for li in soup.find_all('li', class_='card--lite'):
            a = li.find('a')
            href = self.url + a.get('href')[1:]
            title = a.text.strip()
            self.downstream.append((href, title))

    def consume(self) -> bool:
        if not self.downstream:
            self.done = True
            return False

        href, title = self.downstream.pop()
        with Session() as session:
            article = session.query(Article).filter_by(url=href).first()
            if article:
                return True

        response = rq.get(href)
        if not response.ok:
            logger.error("Status Code: ", response.status_code)
            logger.info("Removing URL from downstream")
            self.downstream.remove((href, title))
            return True
        soup = Soup(response.content, 'lxml')
        story = []
        for p in soup.find('article').find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': ' '.join(story),
            'title': title,
            'url': href
        })
        logger.info(f"Title: {title}")
        logger.info(f"URL: {href}")
        logger.info(f"Story: {' '.join(story)}")

    def process(self):
        if not self.results:
            return
        sid = SentimentIntensityAnalyzer()
        for result in self.results:
            artss = sid.polarity_scores(result['body'])
            artss = {f"art{k}": v for k, v in artss.items()}
            headss = sid.polarity_scores(result['title'])
            headss = {f"head{k}": v for k, v in headss.items()}
            result.update(artss)
            result.update(headss)
            logger.info(f"Summary: {result}")
            with Session() as session:
                article = Article(**result, agency_id=self.agency_id)
                session.add(article)
                session.commit()

    def run(self):
        self.setup()
        while not self.done:
            consumed = self.consume()
            self.process()
            if not consumed:
                time.sleep(Config.time_between_requests())
