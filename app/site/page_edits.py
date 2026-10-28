import os

import pandas as pd

from app.analysis import abtests
from app.analysis.edits import find_edits, edit_rates, WINDOW_DAYS
from app.site.common import TemplateHandler, chip_style, j2env
from app.site.data import DataHandler
from app.utils.constants import Bias
from app.utils.logger import get_logger

logger = get_logger(__name__)

# e.g. "Oct 3, 9:41 AM"; Windows' strftime doesn't support the no-padding dash
TIME = '%b %#d, %#I:%M %p' if os.name == 'nt' else '%b %-d, %-I:%M %p'


def eastern(timestamp) -> str:
    return pd.Timestamp(timestamp).tz_localize('UTC').tz_convert('US/Eastern').strftime(TIME)


def source_kinds() -> dict[str, str]:
    """Where we read each outlet's headlines. Feed titles are normally the article's own headline, so a change
    there is close to a real rewrite; a front-page change can also mean the story moved to a slot with a different,
    shorter headline while the article itself kept its original one."""
    from app.registry import Scrapers
    from app.scraper import FeedScraper
    return {s.agency: 'feed' if issubclass(s, FeedScraper) else 'front page' for s in Scrapers}


class EditsPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('edits.html')
        self.context = {'title': 'Headline changes', 'window_days': WINDOW_DAYS}

    def generate(self):
        logger.info("Generating edits page...")
        edits, minor = find_edits()
        kinds = source_kinds()
        # The language model's reading of each rewrite (more loaded or plainer wording, better or worse news, a note
        # on what changed) isn't shown since Oct 28: it called 63% of rewrites "more loaded" for outlets on every
        # side, and 6.8% of its notes only repeated a label. The rewrites and their counts stay
        rows = []
        for _, edit in edits.iterrows():
            rows.append({
                'agency': edit['agency'], 'url': edit['url'], 'style': chip_style(edit['agency'], edit['bias']),
                'bias': 'not rated' if edit['agency'] in j2env.globals['unrated'] else str(Bias(int(edit['bias']))),
                'before_html': edit['before_html'], 'after_html': edit['after_html'],
                'between': f"{eastern(edit['last_seen_before'])} and {eastern(edit['first_seen_after'])} ET",
                'when': int(pd.Timestamp(edit['first_seen_after']).timestamp()),
                'source': kinds.get(edit['agency'], 'front page'),
            })
        rates = edit_rates(edits)
        ab = [{**t, 'style': chip_style(t['agency'], t['bias']), 'started': eastern(t['started']),
               'latest': eastern(t['latest'])} for t in abtests.tests()]
        self.context.update({
            'tests': ab,
            'edits': rows,
            'minor_count': len(minor),
            'rates': [] if rates.empty else [
                {'agency': r.agency, 'style': chip_style(r.agency, r.bias),
                 'edits': int(r.edits),
                 'headlines': int(r.headlines), 'per_100': round(r.per_100, 1)}
                for r in rates.itertuples()],
        })
        self.template.write(self.context)
        logger.info("...%d edits, %d minor", len(rows), len(minor))
