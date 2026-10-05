"""The saga tracker (#163): every running story we've followed, kept after it leaves the front pages, each with its
parts on a timeline (app/analysis/sagas.py keeps the sagas; this page lays out their history)."""
from datetime import timedelta as td

import pytz

from app.analysis import sagas
from app.site.common import TemplateHandler
from app.site.page_headlines import SAGA_COLORS
from app.utils import get_logger

logger = get_logger(__name__)
EASTERN = pytz.timezone('America/New_York')
MIN_SPAN = td(hours=6)  # a timeline is never shorter than this, so a saga a few hours old isn't all bar


def eastern(when) -> str:
    """'Oct 4, 6 PM' in Eastern time, from a naive UTC time."""
    local = pytz.UTC.localize(when).astimezone(EASTERN)
    return local.strftime('%b %-d, %-I %p').replace(':00', '')


def lasted(first, last) -> str:
    hours = (last - first).total_seconds() / 3600
    if hours < 24:
        return f'{max(1, round(hours))} hour{"" if round(hours) <= 1 else "s"}'
    days = round(hours / 24, 1)
    return f'{days:g} day{"" if days == 1 else "s"}'


class SagasPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('sagas.html')

    def generate(self):
        logger.info("Generating saga tracker page...")
        found = sagas.history()
        for saga in found:
            saga['color'] = SAGA_COLORS[saga['id'] % len(SAGA_COLORS)]  # the same color as on the front page
            start = saga['first']
            span = max(saga['last'] - start, MIN_SPAN).total_seconds()
            for part in saga['parts']:
                # Each part's time on the front pages as a bar across the saga's whole span
                part['left'] = round(100 * (part['first'] - start).total_seconds() / span, 2)
                part['width'] = max(2.0, round(100 * (part['last'] - part['first']).total_seconds() / span, 2))
                part['width'] = min(part['width'], 100 - part['left'])
                part['when'] = eastern(part['first'])
                part['until'] = 'now' if part['now'] else eastern(part['last'])
            saga['started'] = eastern(saga['first'])
            saga['ended'] = eastern(saga['last'])
            saga['lasted'] = lasted(saga['first'], saga['last'])
            rated = saga['left'] + saga['center'] + saga['right']
            saga['shares'] = {side: round(100 * saga[side] / rated, 1) if rated else 0 for side in ('left', 'center', 'right')}
            saga['text'] = ' '.join([saga['name']] + [p['label'] for p in saga['parts']]).lower()
        self.template.write({'title': 'Sagas', 'sagas': found, 'active': sum(s['now'] for s in found)})
        logger.info("...%d sagas, %d on front pages now", len(found), sum(s['now'] for s in found))
