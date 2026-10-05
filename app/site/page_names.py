"""Who's in the news (#165 follow-up): each person, country, place, organization or group the local model names in the
stories (app/analysis/entities.py), over time: the stories naming them, day by day, and the outlets on them by lean."""
from datetime import timedelta as td

import pytz

from app.analysis import entities
from app.site.common import TemplateHandler
from app.site.page_sagas import eastern
from app.utils import get_logger

logger = get_logger(__name__)
EASTERN = pytz.timezone('America/New_York')
NOW_SLACK = td(minutes=30)


def days_on(stories: list[dict], days: list) -> list[int]:
    """How many of the stories were on the front pages each day (Eastern)"""
    counts = []
    for day in days:
        n = 0
        for st in stories:
            first = pytz.UTC.localize(st['first']).astimezone(EASTERN).date()
            last = pytz.UTC.localize(st['last']).astimezone(EASTERN).date()
            n += first <= day <= last
        counts.append(n)
    return counts


class NamesPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('names.html')

    def generate(self):
        logger.info("Generating names page...")
        found = entities.history()
        latest = max((st['last'] for e in found for st in e['stories']), default=None)
        if found:
            start = min(pytz.UTC.localize(e['first']).astimezone(EASTERN).date() for e in found)
            end = pytz.UTC.localize(latest).astimezone(EASTERN).date()
            days = [start + td(days=i) for i in range((end - start).days + 1)]
        else:
            days = []
        for e in found:
            e['per_day'] = days_on(e['stories'], days)
            e['peak'] = max(e['per_day'] or [1])
            e['now'] = any(st['last'] >= latest - NOW_SLACK for st in e['stories'])
            e['since'] = eastern(e['first'])
            for st in e['stories']:
                st['now'] = st['last'] >= latest - NOW_SLACK
                st['when'] = eastern(st['first'])
                st['until'] = 'now' if st['now'] else eastern(st['last'])
            rated = e['left'] + e['center'] + e['right']
            e['shares'] = {s: round(100 * e[s] / rated, 1) if rated else 0 for s in ('left', 'center', 'right')}
            e['text'] = ' '.join([e['name']] + [st['label'] or '' for st in e['stories']]).lower()
        self.template.write({'title': "Who's in the news", 'names': found,
                             'days': [d.strftime('%b %-d') for d in days]})
        logger.info("...%d names", len(found))
