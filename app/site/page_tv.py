"""On TV: what the cable and news channels kept on screen (their chyrons, from the Internet Archive's Third Eye), and
for how long, beside what the front pages led with (app/chyrons.py)."""
import glob
import os
from collections import defaultdict
from datetime import datetime, timedelta as td

import pytz

from app import chyrons
from app.site.common import TemplateHandler
from app.site.page_sagas import EASTERN
from app.utils import get_logger
from app.utils.store import read_json

logger = get_logger(__name__)
HOURS = 12  # the latest hours shown hour by hour
TOP = 4  # captions shown per channel per hour
STORIES = 12  # stories in the day's table
CHANNEL_ORDER = ['CNNW', 'FOXNEWSW', 'MSNOW', 'BBCNEWS']
CHANNEL_INK = {'CNNW': '#cc0000', 'FOXNEWSW': '#003366', 'MSNOW': '#6a3fd1', 'BBCNEWS': '#b80000'}


def matched(days: int = 2) -> list[dict]:
    """The matched captions of the latest `days` UTC days, oldest first"""
    out = []
    for path in sorted(glob.glob(os.path.join(chyrons.FOLDER, 'matched-*.json')))[-days:]:
        for c in read_json(path, []):
            out.append(dict(c, at=datetime.fromisoformat(c['at'])))
    return out


def minutes(seconds: int) -> str:
    return f'{seconds / 60:.0f} min' if seconds >= 90 else f'{seconds} s'


def story_table(caps: list[dict], since: datetime) -> list[dict]:
    """Stories by their time on screen since `since`, each with its minutes per channel and its best front-page rank"""
    rows = {}
    for c in caps:
        if c['at'] < since or not c.get('story'):
            continue
        r = rows.setdefault(c['story'], {'story': c['story'], 'label': c['label'], 'rank': c['rank'],
                                         'by': defaultdict(int), 'total': 0})
        r['by'][c['channel']] += c['seconds']
        r['total'] += c['seconds']
        r['rank'] = min(r['rank'], c['rank'])
    out = sorted(rows.values(), key=lambda r: -r['total'])[:STORIES]
    peak = max((r['by'][ch] for r in out for ch in CHANNEL_ORDER), default=1) or 1
    for r in out:
        r['cells'] = [{'channel': ch, 'seconds': r['by'][ch], 'text': minutes(r['by'][ch]) if r['by'][ch] else '',
                       'share': round(100 * r['by'][ch] / peak)} for ch in CHANNEL_ORDER]
    return out


def hours(caps: list[dict]) -> list[dict]:
    """The latest HOURS hours (Eastern), newest first: each channel's longest-running captions in that hour"""
    by_hour = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'seconds': 0})))
    for c in caps:
        local = pytz.UTC.localize(c['at']).astimezone(EASTERN).replace(minute=0, second=0, microsecond=0)
        g = by_hour[local][c['channel']][c['text']]
        g['seconds'] += c['seconds']
        g.update({k: c[k] for k in ('story', 'label', 'rank') if k in c})
    out = []
    for hour in sorted(by_hour, reverse=True)[:HOURS]:
        channels = []
        for ch in CHANNEL_ORDER:
            caps_ = sorted(({'text': t, **g} for t, g in by_hour[hour][ch].items()), key=lambda g: -g['seconds'])[:TOP]
            if caps_:
                channels.append({'channel': ch, 'name': chyrons.CHANNELS[ch], 'ink': CHANNEL_INK[ch],
                                 'captions': [dict(g, time=minutes(g['seconds'])) for g in caps_]})
        out.append({'label': hour.strftime('%a %b %-d, %-I %p'), 'channels': channels})
    return out


class TvPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('tv.html')

    def generate(self):
        logger.info("Generating TV page...")
        caps = matched()
        latest = max((c['at'] for c in caps), default=datetime.utcnow())
        self.template.write({'title': 'On TV', 'stories': story_table(caps, latest - td(hours=24)),
                             'hours': hours(caps), 'channels': [chyrons.CHANNELS[ch] for ch in CHANNEL_ORDER],
                             'inks': [CHANNEL_INK[ch] for ch in CHANNEL_ORDER]})
        logger.info("...%d captions", len(caps))
