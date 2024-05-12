import argparse
import time

from app.analysis import reapply_sent, reprocess_headlines, analyze_all_topics, reapply_entities
from app.builder import build
from app.queue import scrape
from app.registry import Scrapers
from app.utils import Config, get_logger

logger = get_logger(__name__)


def main(args: argparse.Namespace):
    t = time.time()
    if args.analyze_topics:
        analyze_all_topics(True)
        return
    if args.analyze_sentiment is not None:
        reapply_sent('all' in args.analyze_sentiment)
        return
    if args.reprocess is not None:
        reprocess_headlines('all' in args.reprocess)
        return
    if args.process_entities is not None:
        reapply_entities('all' in args.process_entities)
        return

    if not args.skip_scrape:
        scrapers = [s for s in Scrapers if s.agency == args.scraper] if args.scraper else Scrapers
        scrape(args, scrapers)
    build()
    logger.info("Finished in %f minutes", round((time.time() - t) / 60, 2))


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-scrape', action='store_true')
    parser.add_argument('--scraper', type=str, default=None)
    parser.add_argument('--run-selenium', action='store_true')
    parser.add_argument('--debug', action='store_true')

    parser.add_argument('--analyze-topics', action='store_true')
    parser.add_argument('--analyze-sentiment', action='store', type=str)
    parser.add_argument('--reprocess', action='store', type=str)
    parser.add_argument('--process-entities', action='store', type=str)

    args = parser.parse_args()
    if args.debug:
        Config.set_debug()
    return args


if __name__ == '__main__':
    main(get_args())
