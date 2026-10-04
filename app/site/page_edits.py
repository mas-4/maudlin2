import os

import pandas as pd

from app.analysis import abtests
from app.analysis.edits import judge_edits, find_edits, edit_rates, WINDOW_DAYS
from app.site.common import TemplateHandler, chip_style, j2env
from app.site.data import DataHandler
from app.utils.constants import Bias
from app.utils.logger import get_logger

logger = get_logger(__name__)

# e.g. "Oct 3, 9:41 AM"; Windows' strftime doesn't support the no-padding dash
TIME = '%b %#d, %#I:%M %p' if os.name == 'nt' else '%b %-d, %-I:%M %p'


def eastern(timestamp) -> str:
    return pd.Timestamp(timestamp).tz_localize('UTC').tz_convert('US/Eastern').strftime(TIME)


NOTES = {('wording', 'more_loaded'): 'more loaded wording', ('wording', 'plainer'): 'plainer wording',
         ('news', 'better'): 'reads as better news', ('news', 'worse'): 'reads as worse news'}


def shifts(judgment, edit) -> list[str]:
    """Notes on how a rewrite moved the wording or the news, shown only when two independent readings agree on the
    direction: the language model's side-by-side judgment of both versions, and the change between each version's own
    scores. Either alone is noisy (one called an added apostrophe "more loaded"); both agreeing is worth showing."""
    if not judgment:
        return []
    notes = []

    def moved(field):
        before, after = edit[f'{field}_before'], edit[f'{field}_after']
        if pd.isna(before) or pd.isna(after) or before == after:
            return None
        return 'up' if after > before else 'down'
    agree = {('wording', 'more_loaded'): moved('loaded') == 'up', ('wording', 'plainer'): moved('loaded') == 'down',
             ('news', 'better'): moved('event') == 'up', ('news', 'worse'): moved('event') == 'down'}
    for (field, value), note in NOTES.items():
        if judgment.get(field) == value and agree[(field, value)]:
            notes.append(note)
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
        judged = judge_edits([(e['before'], e['after']) for _, e in edits.iterrows()]) if not edits.empty else {}
        rows = []
        for _, edit in edits.iterrows():
            judgment = judged.get((edit['before'], edit['after']))
            rows.append({
                'agency': edit['agency'], 'url': edit['url'], 'style': chip_style(edit['agency'], edit['bias']),
                'bias': 'not rated' if edit['agency'] in j2env.globals['unrated'] else str(Bias(int(edit['bias']))),
                'before_html': edit['before_html'], 'after_html': edit['after_html'],
                'between': f"{eastern(edit['last_seen_before'])} and {eastern(edit['first_seen_after'])} ET",
                'when': int(pd.Timestamp(edit['first_seen_after']).timestamp()),
                'shifts': shifts(judgment, edit),
                'change': judgment.get('change') if judgment else None,
                'source': kinds.get(edit['agency'], 'front page'),
            })
        rates = edit_rates(edits)
        ab = [{**t, 'style': chip_style(t['agency'], t['bias']), 'started': eastern(t['started']),
               'latest': eastern(t['latest'])} for t in abtests.tests()]
        self.context.update({
            'shift_notes': [n for n in NOTES.values() if any(n in r['shifts'] for r in rows)],
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
