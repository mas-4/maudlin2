"""Saga pages: one page per running story (a saga, app/analysis/sagas.py), following it across its parts the way a
story page follows one story: when each part broke and how long it stayed on the front pages, coverage over time by
part, its minutes on TV and its radio newscasts across every part, what people retold, and a link to each part's own
page. The saga tracker and the front page's saga cards link here."""
import os

from app.analysis import sagas
from app.models import Session, StorySnapshot
from app.site import page_story, page_tv, story_charts
from app.site.common import TemplateHandler
from app.site.page_headlines import SAGA_COLORS
from app.site.page_sagas import eastern, lasted
from app.utils import Config, get_logger

logger = get_logger(__name__)


def page_name(saga_id: int) -> str:
    return f'saga-{saga_id}.html'


def snapshots(story_ids: list[int]) -> dict[int, list[dict]]:
    """story id -> its hourly snapshots (when, how many outlets had it), oldest first"""
    out = {}
    if not story_ids:
        return out
    with Session() as s:
        for sid, at, outlets in s.query(StorySnapshot.story_id, StorySnapshot.at, StorySnapshot.outlets) \
                .filter(StorySnapshot.story_id.in_(story_ids)).order_by(StorySnapshot.at):
            out.setdefault(sid, []).append({'at': at, 'outlets': outlets})
    return out


class SagaPages:
    def __init__(self, dh=None):
        self.template = TemplateHandler('saga.html')

    def generate(self):
        logger.info("Generating saga pages...")
        found = sagas.history()
        ids = [p['story'] for g in found for p in g['parts']]
        snaps = snapshots(ids)
        recent = page_story.recent_stories()
        tv, radio, folk = page_story.tv_by_story(), page_story.radio_by_story(), page_story.folklore_by_story(recent)
        with_page = {st['id'] for st in recent}  # parts that have a story page of their own
        for saga in found:
            parts = saga['parts']
            for i, p in enumerate(parts):
                p['snapshots'] = snaps.get(p['story'], [])
                p['color'] = story_charts.PART_COLORS[i % len(story_charts.PART_COLORS)]
                p['page'] = page_story.page_name(p['story']) if p['story'] in with_page else None
                p['when'] = eastern(p['first'])
                p['lasted'] = lasted(p['first'], p['last'])
                p['tv'] = tv.get(p['story'])
                p['radio'] = radio.get(p['story'], [])
                p['folklore'] = folk.get(p['story'], [])
            spots = [{**s, 'story': p['story']} for p in parts if p['tv'] for s in p['tv']['spots']]
            newscasts = [{**r, 'story': p['story']} for p in parts for r in p['radio']]
            retold = [(f['day'], p['story']) for p in parts for f in p['folklore']]
            seconds = sum(s['seconds'] for s in spots)
            people = sum(f['people'] for p in parts for f in p['folklore'])
            stickers = [{'emoji': '🧩', 'big': len(parts), 'small': 'parts so far', 'color': '#00c2a8'},
                        {'emoji': '📰', 'big': saga['outlets'], 'small': 'outlets carried a part', 'color': '#3a86ff'},
                        {'emoji': '⚖️', 'big': f"🫏{saga['left']} · {saga['center']} · {saga['right']}🐘",
                         'small': 'left · center · right', 'color': '#a9a9b8'},
                        {'emoji': '⏱️', 'big': lasted(saga['first'], saga['last']), 'small': 'running so far', 'color': '#ffc400'}]
            if seconds:
                stickers.append({'emoji': '📺', 'big': page_tv.minutes(seconds), 'small': 'of TV captions', 'color': '#cc0000'})
            if newscasts:
                stickers.append({'emoji': '📻', 'big': len(newscasts), 'small': 'radio newscast' + ('' if len(newscasts) == 1 else 's'),
                                 'color': '#e8463c'})
            if people:
                stickers.append({'emoji': '🧶', 'big': people, 'small': 'people retold it online', 'color': '#8a5cff'})
            self.template.write({
                'title': saga['name'], 'saga': saga, 'parts': parts, 'stickers': stickers,
                'color': SAGA_COLORS[saga['id'] % len(SAGA_COLORS)],
                'since': eastern(saga['first']), 'until': eastern(saga['last']),
                'lanes': story_charts.saga_lanes(parts, spots, newscasts, retold, page_tv.CHANNEL_INK),
                'coverage': story_charts.saga_coverage(parts),
                'channels': sorted({s['name'] for s in spots}),
                'retellings': [{**f, 'part': p['label'], 'color': p['color']} for p in parts for f in p['folklore']],
            }, os.path.join(Config.build, page_name(saga['id'])))
        logger.info("...%d saga pages", len(found))
