"""Saga pages: one page per running story (a saga, app/analysis/sagas.py), following it across its parts the way a
story page follows one story: when each part broke and how long it stayed on the front pages, coverage over time by
part, its minutes on TV and its radio newscasts across every part, what people retold, and a link to each part's own
page. The saga tracker and the front page's saga cards link here."""
import bisect
import os
from collections import Counter

from app.analysis import sagas
from app.models import Session, StorySnapshot
from app.site import page_story, page_tv, story_charts
from app.site.boards import genre_key
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


DRIFT_DAYS, DRIFT_MOTIFS = 14, 5  # the latest days shown, and the most-told motifs each day
RIVER_STEPS = 60  # time steps across a saga's river on its share card


def river_layers(parts: list[dict], steps: int = RIVER_STEPS) -> list[list[float]]:
    """How many outlets carried each part across the saga's time, at `steps` even steps: a list per part, in the parts'
    order (its share card's river). Between hourly snapshots the latest one holds; a part shows from a step before
    its first sighting to a step after its last, so a short part isn't lost between two steps"""
    t0, t1 = min(p['first'] for p in parts), max(p['last'] for p in parts)
    if t1 <= t0:
        return []
    step = (t1 - t0) / (steps - 1)
    out = []
    for p in parts:
        snaps = p.get('snapshots') or []
        times = [x['at'] for x in snaps]
        row = []
        for k in range(steps):
            t = t0 + step * k
            i = max(0, bisect.bisect_right(times, t) - 1)
            row.append(float(snaps[i]['outlets']) if snaps and p['first'] - step <= t <= p['last'] + step else 0.0)
        out.append(row)
    return out


def share(saga: dict, parts: list[dict], rows: list[dict], color: str) -> dict:
    """What a shared link to a saga page shows: its name, its parts in a line, and its own card (Oct 27: a saga link
    showed the site's card, "generic and lame")"""
    from app.site import share_images
    stories = {p['story'] for p in parts}
    told = Counter(r['name'] for r in rows if r['story'] in stories).most_common(1)
    leans = {k: saga[k] for k in ('left', 'center', 'right')}
    try:
        image = share_images.saga_card(saga['name'], color, saga['first'], saga['last'], len(parts), saga['outlets'],
                                       leans, river_layers(parts), told[0][0] if told and told[0][1] >= 2 else None)
    except Exception as e:  # noqa: BLE001 - the page stands without its card; the site's is shown instead
        logger.warning("Saga %s: share card: %s", saga['id'], e)
        image = None
    ordered = sorted(parts, key=lambda p: p['first'])
    days = max(1, (share_images.eastern(saga['last']).date() - share_images.eastern(saga['first']).date()).days + 1)
    return {'og_title': f"{saga['name']} · a saga on bignews.day",
            'og_description': f"{len(parts)} parts over {days} day{'s' if days != 1 else ''}, from "
                              f"“{ordered[0]['label']}” to “{ordered[-1]['label']}”. {saga['outlets']} outlets: "
                              f"{leans['left']} left, {leans['center']} center, {leans['right']} right.",
            'og_image': image,
            'og_image_alt': f"{saga['name']}: {len(parts)} parts over {days} days, carried by {saga['outlets']} outlets"}


def drift(rows: list[dict], stories: set[int]) -> list[dict]:
    """How a saga has been told, day by day: for each day with tellings about one of its parts, its most-told motifs
    (each with how many tellers), newest day first. A motif new to the saga that day is marked, so the turns show"""
    from collections import Counter, defaultdict
    from datetime import date
    from app.site import boards
    days = defaultdict(Counter)
    names, genres = {}, {}
    for r in rows:
        if r['story'] in stories and r['date']:
            days[r['date']][r['motif']] += 1
            names[r['motif']], genres[r['motif']] = r['name'], r.get('genre')
    seen, out = set(), []
    for day in sorted(days):
        top = days[day].most_common(DRIFT_MOTIFS)
        try:  # "Tue Oct 21", not 2026-10-21 (Oct 28: ISO dates on a page that reads Oct 21 everywhere else)
            label = date.fromisoformat(day).strftime('%a %b %-d')
        except ValueError:
            label = day
        out.append({'day': day, 'label': label, 'total': sum(n for _, n in top),
                    'motifs': [{'id': m, 'name': names[m], 'n': n, 'new': m not in seen, 'genre': genres[m],
                                'ink': boards.GENRE_INK.get(genres[m], boards.UNCOLORED)} for m, n in top]})
        seen |= set(days[day])
    return list(reversed(out))[:DRIFT_DAYS]


def part_board(parts: list[dict]) -> dict:
    """The saga's parts, listed once in full (Oct 28: they were listed three times, as a journey, a chart's labels
    and a wall of cards): a row each in the order of their latest news, in its color on the charts, the bar the
    outlets that carried it, the disc whether it's on the front pages now (🔴), has a page of its own (📄) or is
    older than a week (🗄️); when it broke, how long it lasted, its first headline and its TV, radio and retellings in
    its hover card"""
    from app.site import boards
    top = max((p['outlets'] for p in parts), default=1)
    rows = []
    for p in parts:
        lines = [f"{p['label']}: {p['when']} ET · on the front pages {p['lasted']}"
                 + (' · 🔴 on them now' if p.get('now') else '')]
        if p.get('first_title'):
            lines.append(f"“{p['first_title']}”" + (f" first on {', '.join(p['first_outlets'])}"
                                                     if p.get('first_outlets') else ''))
        if p.get('tv'):
            lines.append('📺 ' + ', '.join(f"{t['name']} {t['time']}" for t in p['tv']['channels']))
        if p.get('radio'):
            lines.append(f"📻 {len(p['radio'])} radio newscast{'' if len(p['radio']) == 1 else 's'}")
        if p.get('folklore'):
            lines.append(f"🧶 retold by {sum(f['people'] for f in p['folklore'])} people online")
        if not p.get('page'):
            lines.append('older than a week: no page of its own')
        mark, label = ('🔴', 'on the front pages now') if p.get('now') else ('📄', 'has its own page') if p.get('page') \
            else ('🗄️', 'older than a week')
        rows.append(boards.row(p['label'], p.get('page'), p['outlets'], top,
                               f"{p['outlets']} outlet{'' if p['outlets'] == 1 else 's'}", tip='\n'.join(lines),
                               ink=p['color'], mark=mark, mark_label=label))
    return boards.board('parts', '🧩', 'The parts', '#ff4fa3', 'in the order of their latest news, each in its color '
                        'on the charts; the bar is the outlets that carried it. 🔴 on the front pages now, 📄 a page of '
                        'its own, 🗄️ older than a week', rows)


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
        with_page = {st['id'] for st in recent} | page_story.archived_ids()  # parts with a story page of their own
        try:  # how the saga's been told, day by day, from the motif index (motif_web)
            from app.site.page_motif import shared
            rows = shared()['web']['rows']
        except Exception as e:  # noqa: BLE001 - extra
            logger.warning("Saga pages: motifs: %s", e)
            rows = []
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
            color = SAGA_COLORS[saga['id'] % len(SAGA_COLORS)]
            self.template.write({
                'drift': (told := drift(rows, {p['story'] for p in parts})),
                'drift_key': genre_key([{'genre': m['genre']} for d in told for m in d['motifs']]),
                'title': saga['name'], 'saga': saga, 'parts': parts, 'stickers': stickers, 'color': color,
                **share(saga, parts, rows, color),
                'since': eastern(saga['first']), 'until': eastern(saga['last']),
                'lanes': story_charts.saga_lanes(parts, spots, newscasts, retold, page_tv.CHANNEL_INK),
                'coverage': story_charts.saga_coverage(parts),
                'part_board': part_board(parts),
                'channels': sorted({s['name'] for s in spots}),
                'retellings': [{**f, 'part': p['label'], 'color': p['color']} for p in parts for f in p['folklore']],
            }, os.path.join(Config.build, page_name(saga['id'])))
        # A saga that ended (absorbed into another, or left with one part) points on to where it went, so a shared
        # link keeps working; one whose end wasn't recorded (before Oct 7) to the saga tracker
        made = {saga['id'] for saga in found}
        for sid, to in sagas.ended().items():
            if sid in made:
                continue
            target = page_name(to['saga']) if to.get('saga') else page_story.page_name(to['story']) if to.get('story') else 'sagas.html'
            with open(os.path.join(Config.build, page_name(sid)), 'w', encoding='utf-8') as f:
                f.write(page_story.REDIRECT.format(to=target).replace(
                    f'This story is now part of <a href="{target}">this one</a>',
                    f'This saga has ended; it continues <a href="{target}">here</a>'))
        logger.info("...%d saga pages", len(found))
