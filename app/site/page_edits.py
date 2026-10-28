"""The edits page: headlines outlets changed after publishing, which outlets rewrite most, and Slate's headline tests.

Oct 28 (the site redo): "Which outlets rewrite most" (a plain table) became Rewrite most | Never rewrite boards,
colored by lean, the table folded under them; the headline tests became little races, a bar per wording for the
hours it was up, the top few shown and the rest folded."""
import os

import pandas as pd

from app.analysis import abtests
from app.analysis.edits import find_edits, edit_rates, WINDOW_DAYS
from app.site import boards as strips
from app.site.common import TemplateHandler, chip_style, j2env
from app.site.data import DataHandler
from app.site.favicons import slug
from app.site.page_emotions import lean_key, outlet_lean
from app.utils.constants import Bias
from app.utils.logger import get_logger

logger = get_logger(__name__)

# e.g. "Oct 3, 9:41 AM"; Windows' strftime doesn't support the no-padding dash
TIME = '%b %#d, %#I:%M %p' if os.name == 'nt' else '%b %-d, %-I:%M %p'
PER_BOARD = 12
RACES_SHOWN = 3  # headline tests shown as races; the rest folded


def eastern(timestamp) -> str:
    return pd.Timestamp(timestamp).tz_localize('UTC').tz_convert('US/Eastern').strftime(TIME)


def source_kinds() -> dict[str, str]:
    """Where we read each outlet's headlines. Feed titles are normally the article's own headline, so a change
    there is close to a real rewrite; a front-page change can also mean the story moved to a slot with a different,
    shorter headline while the article itself kept its original one."""
    from app.registry import Scrapers
    from app.scraper import FeedScraper
    return {s.agency: 'feed' if issubclass(s, FeedScraper) else 'front page' for s in Scrapers}


def hours(h: float) -> str:
    return 'under an hour' if h < 1 else f'{round(h)}h'


def rate_boards(rates: list[dict], kinds: dict[str, str]) -> list[dict]:
    """Rewrite most | Never rewrite: the outlets that changed the most headlines per 100 they put up, and those that
    changed none, the most headlines read first (the longer the record, the surer the zero); rows colored by lean"""
    def tip(r):
        where = 'its RSS feed' if kinds.get(r['agency']) == 'feed' else 'its front page'
        return '\n'.join([f"{r['lean_words'].capitalize()}",
                          f"{r['edits']} changes in {r['headlines']:,} headlines over {WINDOW_DAYS} days",
                          f"read from {where}"])

    def row(r, value, top, figure):
        x = strips.row(r['agency'], r['href'], value, top, figure, tip=tip(r), ink=strips.LEAN_INK[r['lean']],
                       mark=strips.LEAN_EMOJI[r['lean']], mark_label=r['lean_words'])
        x['lean'] = r['lean']
        return x
    most = sorted((r for r in rates if r['edits']), key=lambda r: (-r['per_100'], -r['edits']))[:PER_BOARD]
    never = sorted((r for r in rates if not r['edits']), key=lambda r: (-r['headlines'], r['agency']))[:PER_BOARD]
    top_most = most[0]['per_100'] if most else 1
    top_never = never[0]['headlines'] if never else 1
    return [
        strips.board('rewrite-most', '✏️', 'Rewrite most', '#ff6b1a',
                     'the bar is changes per 100 headlines it put up', [
                         row(r, r['per_100'], top_most, f"{r['per_100']:g} per 100") for r in most],
                     empty='🦗 No outlet changed a headline this week.'),
        strips.board('rewrite-never', '🪨', 'Never rewrite', '#a9a9b8',
                     "no change seen this week; the bar is how many headlines we read from it, so the longer the bar, "
                     "the surer the zero", [row(r, r['headlines'], top_never, f"0 of {r['headlines']:,}") for r in never],
                     empty='🤷 Every outlet changed at least one headline this week.'),
    ]


def race(t: dict) -> dict:
    """A headline test as a little race: a lane per wording, its bar the hours it was up (of the longest), the
    winner first with its 🏆"""
    top = max((v['hours'] for v in t['variants']), default=0) or 1
    lanes = []
    for v in t['variants']:
        bits = [f"up {hours(v['hours'])}"]
        if v['won']:
            bits.append('🏆 the one Slate kept')
        elif t['state'] == 'running' and v['live']:
            bits.append('🟢 still being tried')
        elif t['state'] == 'won':
            bits.append('dropped')
        if v['default']:
            bits.append('⭐ a starting wording: the one in the page itself')
        lanes.append({**v, 'bar': strips.bar(v['hours'], top, least=3), 'up': hours(v['hours']), 'tip': '\n'.join(bits)})
    return {**t, 'lanes': lanes}


class EditsPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('edits.html')
        self.context = {'title': 'Headline changes', 'window_days': WINDOW_DAYS, 'races_shown': RACES_SHOWN}

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
        ab = [race({**t, 'style': chip_style(t['agency'], t['bias']), 'started': eastern(t['started']),
                    'latest': eastern(t['latest'])}) for t in abtests.tests()]
        rate_rows = [] if rates.empty else [
            {'agency': r.agency, 'style': chip_style(r.agency, r.bias), 'edits': int(r.edits),
             'headlines': int(r.headlines), 'per_100': round(r.per_100, 1), 'href': f'outlet-{slug(r.agency)}.html',
             **dict(zip(('lean', 'lean_words'), outlet_lean(r.agency, int(r.bias))))}
            for r in rates.itertuples()]
        boards = rate_boards(rate_rows, kinds)
        self.context.update({
            'tests': ab,
            'edits': rows,
            'minor_count': len(minor),
            'rates': rate_rows,
            'rate_boards': boards,
            'lean_key': lean_key([r for b in boards for r in b['rows']]),
        })
        self.template.write(self.context)
        logger.info("...%d edits, %d minor", len(rows), len(minor))
