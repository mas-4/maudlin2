"""Who's in the news (#165 follow-up): each person, country, place, organization or group the local model names in
today's stories (app/analysis/entities.py), with those stories and the outlets on them by lean."""
from datetime import timedelta as td

import pytz

from app.analysis import entities
from app.site.common import TemplateHandler
from app.site.page_sagas import eastern
from app.utils import get_logger

logger = get_logger(__name__)
EASTERN = pytz.timezone('America/New_York')
NOW_SLACK = td(minutes=30)


SHOWN = 3  # a name's stories shown; the rest folded
MOTIFS = 6  # the stories told about a name shown on its card, the most told first
WIDE = 15  # outlets: a name in one story today is listed if that story reached this many


def today_start():
    """The start of today in Eastern time, as naive UTC"""
    from datetime import datetime
    midnight = EASTERN.localize(datetime.now(EASTERN).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0))
    return midnight.astimezone(pytz.UTC).replace(tzinfo=None)


class NamesPage:
    """Who's in the news today (Oct 12, the person: "make it a bit more coherent now that we have a week of data ... it's
    too much under each name ... probably just who's in the news today"): each name in a story on the front pages
    today, one story enough, by how many outlets carry its stories; a few stories each, the rest folded"""
    def __init__(self, dh=None):
        self.template = TemplateHandler('names.html')

    def generate(self):
        logger.info("Generating names page...")
        from app.site import page_story
        since = today_start()
        # in two stories today, or in one that reached at least WIDE outlets (the long tail stays out: Oct 12, 259 names)
        found = [e for e in entities.history(least=1, since=since) if len(e['stories']) >= 2 or e['outlets'] >= WIDE]
        latest = max((st['last'] for e in found for st in e['stories']), default=None)
        with_page = {st['id'] for st in page_story.recent_stories()} | page_story.archived_ids()
        for e in found:
            for st in e['stories']:
                st['now'] = st['last'] >= latest - NOW_SLACK
                st['when'] = eastern(st['first'])
                st['page'] = page_story.page_name(st['id']) if st['id'] in with_page else None
            e['stories'].sort(key=lambda st: (not st['now'], -st['outlets']))  # on the front pages now, the widest first
            e['now'] = any(st['now'] for st in e['stories'])
            rated = e['left'] + e['center'] + e['right']
            e['shares'] = {s: round(100 * e[s] / rated, 1) if rated else 0 for s in ('left', 'center', 'right')}
            e['text'] = ' '.join([e['name']] + [st['label'] or '' for st in e['stories']]).lower()
        try:  # the stories told about each name, from the motif index (motif_web.people)
            from app.analysis import motif_web
            from app.site.page_motif import shared
            told = motif_web.people(shared()['web']['rows'], [e['name'] for e in found], entities.load_aliases()['aliases'])
        except Exception as err:  # noqa: BLE001 - extra
            logger.warning("Names page: motifs: %s", err)
            told = {}
        for e in found:
            e['motifs'] = told.get(e['name'], [])[:MOTIFS]
        found.sort(key=lambda e: (-e['outlets'], -len(e['stories']), e['name']))
        self.template.write({'title': "Who's in the news", 'names': found, 'shown': SHOWN,
                             'today': datetime_eastern_today()})
        logger.info("...%d names today", len(found))


def datetime_eastern_today() -> str:
    from datetime import datetime
    return datetime.now(EASTERN).strftime('%A, %B %-d')
