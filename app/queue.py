import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from app.analysis import ner
from app.scraper import SeleniumResourceManager, Scraper, SeleniumScraper
from app.models import Session, Headline
from app.utils import Config, get_logger

logger = get_logger(__name__)


class SeleniumThread(threading.Thread):
    def __init__(self, seleniums):
        self.seleniums = seleniums
        threading.Thread.__init__(self)
        self.scrapers = []

    def run(self):
        t = time.time()
        for sel in self.seleniums:
            scraper = sel()
            try:
                scraper.run()
            except Exception as e:
                logger.error(f"Failed to run {scraper}: {e}")
                continue
            else:
                self.scrapers.append(scraper)
        SeleniumResourceManager().quit()
        logger.info(f"Finished seleniums in {time.time() - t} seconds")

    def post_run(self):
        num = len(self.scrapers)
        for i, sel in enumerate(self.scrapers):
            sel.post_run()
            logger.info(f"Finished {sel} ({i + 1} of {num})")


class Queue:
    def __init__(self, args):
        self.threads = []
        self.selenium_classes = []
        self.scrapers = []
        self.args = args

    def run(self):
        seleniumthread = SeleniumThread(self.selenium_classes)
        if Config.run_selenium and self.args.run_selenium:
            logger.info("Running seleniums")
            seleniumthread.start()

        num = len(self.threads)
        with ThreadPoolExecutor(max_workers=Config.max_threads) as executor:
            futures = {executor.submit(scraper.run): scraper for scraper in self.threads}
            for i, future in enumerate(as_completed(futures)):
                scraper: Scraper = futures[future]
                if scraper.success:
                    scraper.post_run()
                    logger.info(f"Finished {scraper} ({i + 1} of {num})")

        if Config.run_selenium and self.args.run_selenium:
            logger.info("Waiting for seleniums")
            seleniumthread.join()
            seleniumthread.post_run()
        self.scrapers = self.threads + seleniumthread.scrapers

        self.run_ner()

    def run_ner(self):
        """
        Concatenate the dataframes from the scrapers and run

        The dfs have the following columns (but are not limited to):
        - processed: the processed headline
        - seen: boolean if the headline has been seen before this run (and therefore shouldn't be reprocessed)
        """
        dfs = [scraper.df for scraper in self.scrapers]
        if not len(dfs):
            raise ValueError("No dataframes to concatenate")
        df = pd.concat(dfs)
        df = df[~df['seen']]
        if not len(df):
            logger.info("No new headlines to process")
            return
        with Session() as s:
            df['headline_id'] = s.query(Headline.id).filter(Headline.processed.in_(df['processed'])).all()
        df = df[['headline_id', 'processed']]
        df.rename(columns={'processed': 'title'}, inplace=True)
        ner.setup(df, ner.EntityAnalyzer())
        ner.apply_entities(df)

    def add(self, scraper):
        if issubclass(scraper, SeleniumScraper):
            self.selenium_classes.append(scraper)
        else:
            self.threads.append(scraper())


def scrape(args, scrapers):
    if not len(scrapers):
        raise ValueError("No scrapers provided")
    queue = Queue(args)
    logger.info("Initializing queue")
    # Log the scrapers in a pretty print of multiple columns
    logger.info("Scrapers: %s", '\n'.join([str(scraper) for scraper in scrapers]))
    for scraper in scrapers:
        queue.add(scraper)

    queue.run()
