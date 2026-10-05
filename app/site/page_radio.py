"""On the radio (#159): the hourly newscasts of NPR and ABC News, each story in the order it aired, beside what the
front pages led with at that hour (app/analysis/running_order.py)."""
from datetime import datetime, timedelta as td

import pytz

from app.analysis import running_order
from app.site.common import TemplateHandler
from app.site.page_sagas import EASTERN
from app.utils import get_logger

logger = get_logger(__name__)
NOW_SLACK = td(minutes=30)


def current_story_ids() -> set:
    """Stories on the front pages at the latest run, to link to their cards"""
    from sqlalchemy import func
    from app.models import Session, Story
    with Session() as s:
        latest = s.query(func.max(Story.last_seen)).scalar()
        if latest is None:
            return set()
        return {i for (i,) in s.query(Story.id).filter(Story.last_seen >= latest - NOW_SLACK)}


def show_stats(casts: list[dict]) -> dict:
    """How a show's running order compares with the front pages': how often its lead was their biggest story or one of
    their three biggest, and how many of its stories were on them at all"""
    led = [c for c in casts if c['items']]
    items = [x for c in casts for x in c['items']]
    return {'casts': len(led),
            'lead_top': sum(c['items'][0].get('front_rank') == 1 for c in led),
            'lead_top3': sum((c['items'][0].get('front_rank') or 99) <= 3 for c in led),
            'items': len(items), 'on_front': sum('story' in x for x in items)}


def hours(store: dict) -> list[dict]:
    """The newscasts by hour (Eastern), newest first, each hour with its shows side by side"""
    by_hour = {}
    for cast in store.values():
        local = pytz.UTC.localize(datetime.fromisoformat(cast['published'])).astimezone(EASTERN)
        hour = local.replace(minute=0, second=0, microsecond=0)
        cast = dict(cast, when=local.strftime('%-I:%M %p'))
        by_hour.setdefault(hour, {})[cast['source']] = cast
    out = []
    for hour in sorted(by_hour, reverse=True):
        shows = [by_hour[hour][src] for src in running_order.SOURCES if src in by_hour[hour]]
        front = max((c['front_top'] for c in shows), key=len, default=[])
        out.append({'label': hour.strftime('%a %b %-d, %-I %p'), 'shows': shows, 'front': front})
    return out


class RadioPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('radio.html')

    def generate(self):
        logger.info("Generating radio page...")
        store = running_order.load()
        now = current_story_ids()
        for cast in store.values():
            for x in cast['items']:
                x['now'] = x.get('story') in now
            for f in cast['front_top']:
                f['now'] = f['id'] in now
        stats = [dict(show_stats([c for c in store.values() if c['source'] == src]), show=name)
                 for src, name in running_order.SOURCES.items()]
        self.template.write({'title': 'On the radio', 'hours': hours(store), 'stats': stats})
        logger.info("...%d newscasts", len(store))
