import os

import pandas as pd

from app.analysis.edits import find_edits, edit_rates, WINDOW_DAYS
from app.site.common import TemplateHandler
from app.site.data import DataHandler
from app.site.graphing import bias_colors, bias_ink
from app.utils.constants import Bias
from app.utils.logger import get_logger

logger = get_logger(__name__)

# e.g. "Oct 3, 9:41 AM"; Windows' strftime doesn't support the no-padding dash
TIME = '%b %#d, %#I:%M %p' if os.name == 'nt' else '%b %-d, %-I:%M %p'


def eastern(timestamp) -> str:
    return pd.Timestamp(timestamp).tz_localize('UTC').tz_convert('US/Eastern').strftime(TIME)


def shifts(edit) -> list[str]:
    """Plain-words notes on how the rewrite moved the llm's scores, when both versions were scored."""
    notes = []
    if pd.notna(edit['loaded_before']) and pd.notna(edit['loaded_after']):
        if edit['loaded_after'] > edit['loaded_before']:
            notes.append('more loaded wording')
        elif edit['loaded_after'] < edit['loaded_before']:
            notes.append('plainer wording')
    if pd.notna(edit['event_before']) and pd.notna(edit['event_after']):
        if edit['event_after'] > edit['event_before']:
            notes.append('reads as better news')
        elif edit['event_after'] < edit['event_before']:
            notes.append('reads as worse news')
    return notes


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
        rows = []
        for _, edit in edits.iterrows():
            rows.append({
                'agency': edit['agency'], 'url': edit['url'], 'color': bias_colors[int(edit['bias']) + 3],
                'ink': bias_ink[int(edit['bias']) + 3],
                'bias': str(Bias(int(edit['bias']))),
                'before_html': edit['before_html'], 'after_html': edit['after_html'],
                'between': f"{eastern(edit['last_seen_before'])} and {eastern(edit['first_seen_after'])} ET",
                'shifts': shifts(edit),
                'source': kinds.get(edit['agency'], 'front page'),
            })
        rates = edit_rates(edits)
        self.context.update({
            'edits': rows,
            'minor_count': len(minor),
            'rates': [] if rates.empty else [
                {'agency': r.agency, 'color': bias_colors[int(r.bias) + 3], 'ink': bias_ink[int(r.bias) + 3],
                 'edits': int(r.edits),
                 'headlines': int(r.headlines), 'per_100': round(r.per_100, 1)}
                for r in rates.head(15).itertuples()],
        })
        self.template.write(self.context)
        logger.info("...%d edits, %d minor", len(rows), len(minor))
