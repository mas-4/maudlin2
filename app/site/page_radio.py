"""On the radio (#159): the hourly newscasts of NPR and ABC News, each story in the order it aired, beside what the
front pages led with at that hour (app/analysis/running_order.py).

Oct 28 (the site redo): the page was a sentence of numbers over an endless grid of hour cards. Now: NPR and ABC as
stickers with bars (how often each led with the front pages' top story), the last hours as a swimlane, each newscast's
running order in its hover card, and a pair that answers itself, what the newscasts carried that the front pages didn't
beside what the front pages led with that the newscasts skipped. Every newscast is still there, in a collapsed log."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta as td

import pytz

from app.analysis import running_order
from app.site import boards
from app.site.common import TemplateHandler
from app.site.page_sagas import EASTERN
from app.site.page_tv import group_titles, hour_label
from app.utils import get_logger

logger = get_logger(__name__)
NOW_SLACK = td(minutes=30)
HOURS = 12  # the latest hours in the swimlane
WINDOW = td(hours=24)  # the pair's window, up to the latest newscast
PAIR = 10  # rows in each of the pair
TOP_FRONT = 3  # a story "led" the front pages in an hour it was among their top this many...
LED_HOURS = 3  # ...for at least this many hours of the window...
SKIP_SHARE = 0.25  # ...and the newscasts "skipped" it when they mentioned it in fewer newscasts than this share of them
# The shows' inks: not the lean blue and red; their short names ride on the discs, so the color is never alone
INK = {'nprnewsnow': '#ff6b1a', 'abcupdate': '#1fb5a8'}
MARK = {'nprnewsnow': 'NPR', 'abcupdate': 'ABC'}
FRONT = {'ink': '#ffc400', 'mark': '📰', 'name': 'The front pages'}
NOBODY = {'ink': boards.UNCOLORED, 'mark': '📵', 'label': 'neither newscast'}


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


def stickers(store: dict) -> list[dict]:
    """A sticker per show: its newscasts, and bars for how often it led with the front pages' top story, one of their
    top three, and how many of its stories were on the front pages at all"""
    out = []
    for src, name in running_order.SOURCES.items():
        casts = [c for c in store.values() if c['source'] == src]
        s = show_stats(casts)
        if not s['casts']:
            continue
        since = min(c['published'] for c in casts)
        pct = lambda n, of: round(100 * n / (of or 1))  # noqa: E731
        out.append({'source': src, 'show': name, 'ink': INK.get(src, '#b8b8c8'), 'mark': MARK.get(src, '📻'),
                    'casts': s['casts'], 'since': datetime.fromisoformat(since).strftime('%b %-d'), 'bars': [
                        {'label': "led with the front pages' top story", 'n': s['lead_top'], 'of': s['casts'],
                         'pct': pct(s['lead_top'], s['casts']), 'unit': 'newscasts'},
                        {'label': 'led with one of their top three', 'n': s['lead_top3'], 'of': s['casts'],
                         'pct': pct(s['lead_top3'], s['casts']), 'unit': 'newscasts'},
                        {'label': 'of its stories were on the front pages that hour', 'n': s['on_front'],
                         'of': s['items'], 'pct': pct(s['on_front'], s['items']), 'unit': 'stories'}]})
    return out


def local(cast: dict) -> datetime:
    return pytz.UTC.localize(datetime.fromisoformat(cast['published'])).astimezone(EASTERN)


def hours(store: dict) -> list[dict]:
    """The newscasts by hour (Eastern), newest first, each hour with its shows side by side"""
    by_hour = {}
    for cast in store.values():
        at = local(cast)
        hour = at.replace(minute=0, second=0, microsecond=0)
        cast = dict(cast, when=at.strftime('%-I:%M %p'))
        by_hour.setdefault(hour, {})[cast['source']] = cast
    out = []
    for hour in sorted(by_hour, reverse=True):
        shows = [by_hour[hour][src] for src in running_order.SOURCES if src in by_hour[hour]]
        front = max((c['front_top'] for c in shows), key=len, default=[])
        out.append({'hour': hour, 'label': hour.strftime('%a %b %-d, %-I %p'), 'shows': shows, 'front': front})
    return out


def item_line(n: int, x: dict) -> str:
    where = (f"#{x['front_rank']} on the front pages, as “{x['story_label']}”" if x.get('story')
             else 'not on the front pages')
    return f"{n}. {x['title']} · {where}"


def swimlane(hrs: list[dict]) -> dict:
    """The latest HOURS hours as a swimlane, oldest on the left: a lane per show and one for the front pages, a cell
    per newscast with its lead story and that story's place on the front pages, the running order in its hover card"""
    cols = sorted(hrs[:HOURS], key=lambda h: h['hour'])
    srcs = [s for s in running_order.SOURCES if any(c['source'] == s for h in cols for c in h['shows'])]
    lanes = [{'name': running_order.SOURCES[s], 'ink': INK.get(s, '#b8b8c8'), 'mark': MARK.get(s, '📻')} for s in srcs]
    lanes.append(FRONT)
    front_row = len(lanes) + 1
    cells = []
    for j, h in enumerate(cols, 2):
        flip = len(cols) + 3 - j
        for c in h['shows']:
            if not c['items']:
                continue
            lead = c['items'][0]
            cells.append({'row': srcs.index(c['source']) + 2, 'col': j, 'flip': flip, 'ink': INK.get(c['source']),
                          'lead': lead['title'], 'rank': lead.get('front_rank') if lead.get('story') else None,
                          'head': f"📻 {c['show']}, aired {c['when']} ET · {len(c['items'])} stories",
                          'tip': '\n'.join(item_line(n, x) for n, x in enumerate(c['items'], 1))})
        if h['front']:
            cells.append({'row': front_row, 'col': j, 'flip': flip, 'ink': FRONT['ink'], 'lead': h['front'][0]['label'],
                          'rank': 1, 'head': f"📰 The front pages' biggest stories, {h['label']} ET",
                          'tip': '\n'.join(f"#{n} {f['label']} · on {f['outlets']} outlets"
                                           for n, f in enumerate(h['front'], 1))})
    return {'lanes': lanes, 'cells': cells, 'cols': len(cols),
            'hours': [{'label': hour_label(h['hour'], first=j == 2), 'col': j, 'flip': len(cols) + 3 - j}
                      for j, h in enumerate(cols, 2)]}


def recent(store: dict) -> list[dict]:
    """The newscasts of the WINDOW up to the latest"""
    if not store:
        return []
    hour = lambda c: datetime.fromisoformat(c['published']).replace(minute=0, second=0, microsecond=0)  # noqa: E731
    last = max(hour(c) for c in store.values())
    return [c for c in store.values() if hour(c) > last - WINDOW]  # the latest 24 clock hours, not 25


def show_mark(src: str | None) -> dict:
    if not src:
        return NOBODY
    return {'ink': INK.get(src, '#b8b8c8'), 'mark': MARK.get(src, '📻'), 'label': running_order.SOURCES.get(src, src)}


def off_front(casts: list[dict]) -> list[dict]:
    """On air, not on the front pages: the newscasts' stories that were none of the front pages' that hour, their
    wordings of one story together, by how many newscasts mentioned them; each row in the ink of the show that did
    more"""
    items = [dict(x, source=c['source'], at=local(c)) for c in casts for x in c['items'] if not x.get('story')]
    groups = sorted(group_titles(items, text=lambda i: i['title']), key=lambda g: (-len(g), g[0]['title']))[:PAIR]
    top = max((len(g) for g in groups), default=1)
    rows = []
    for g in groups:
        g.sort(key=lambda i: i['at'], reverse=True)
        by = Counter(i['source'] for i in g)
        m = show_mark(by.most_common(1)[0][0])
        said = list(dict.fromkeys(i['title'] for i in g))
        tip = '\n'.join([' · '.join(f"{running_order.SOURCES.get(s, s)} {n}" for s, n in by.most_common()),
                         f"Aired {min(i['at'] for i in g):%-I:%M %p} to {max(i['at'] for i in g):%-I:%M %p} ET"]
                        + [f"Also worded: “{t}”" for t in said[1:4]])
        rows.append(boards.row(said[0], None, len(g), top, f"{len(g)} newscast{'s' if len(g) > 1 else ''}", tip=tip,
                               ink=m['ink'], mark=m['mark'], mark_label=m['label']))
    return rows


def skipped(casts: list[dict], now: set | None = None) -> list[dict]:
    """Front pages led, air skipped: the stories among the front pages' TOP_FRONT for LED_HOURS hours or more that
    the newscasts mentioned in fewer than SKIP_SHARE of those hours' newscasts; the bar is the hours they led, the row
    in the ink of the show that mentioned it more (or neither)"""
    by_hour = defaultdict(list)
    for c in casts:
        by_hour[local(c).replace(minute=0, second=0, microsecond=0)].append(c)
    led = {}
    for cs in by_hour.values():
        front = max((c['front_top'] for c in cs), key=len, default=[])
        for n, f in enumerate(front[:TOP_FRONT], 1):
            r = led.setdefault(f['id'], {'id': f['id'], 'label': f['label'], 'hours': 0, 'casts': 0, 'best': n})
            r['hours'] += 1
            r['casts'] += len([c for c in cs if c['items']])
            r['best'] = min(r['best'], n)
    said = defaultdict(Counter)
    for c in casts:
        for x in c['items']:
            if x.get('story'):
                said[x['story']][c['source']] += 1
    items = sorted((r for r in led.values() if r['hours'] >= LED_HOURS
                    and sum(said[r['id']].values()) < SKIP_SHARE * r['casts']),
                   key=lambda r: (-r['hours'], r['best'], r['label']))[:PAIR]
    top = max((r['hours'] for r in items), default=1)
    rows = []
    for r in items:
        by = said[r['id']]
        m = show_mark(by.most_common(1)[0][0] if by else None)
        n = sum(by.values())
        air = ' · '.join(f"{running_order.SOURCES.get(s, s)} {k}" for s, k in by.most_common()) or 'Neither newscast'
        tip = (f"Among the front pages' top {TOP_FRONT} for {r['hours']} of the last {WINDOW // td(hours=1)} hours, "
               f"#{r['best']} at best\nMentioned in {n} of those {r['casts']} newscasts: {air}")
        href = f"index.html#s-{r['id']}" if now and r['id'] in now else None
        rows.append(boards.row(r['label'], href, r['hours'], top, f"{r['hours']} h · {n} newscast{'' if n == 1 else 's'}",
                               tip=tip, ink=m['ink'], mark=m['mark'], mark_label=m['label']))
    return rows


def show_key(with_nobody: bool = False) -> list[dict]:
    key = [{'name': name, 'mark': MARK[s], 'ink': INK[s]} for s, name in running_order.SOURCES.items() if s in INK]
    return key + ([{'name': NOBODY['label'], 'mark': NOBODY['mark'], 'ink': NOBODY['ink']}] if with_nobody
                  else [{'name': FRONT['name'], 'mark': FRONT['mark'], 'ink': FRONT['ink']}])


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
        hrs = hours(store)
        last = recent(store)
        pair = [boards.board('radio-on-air', '📡', 'On air, not on the front pages', '#ff6b1a',
                             "the newscasts' stories that were none of the front pages' that hour, wordings of one "
                             'story together; the bar is how many newscasts mentioned it', off_front(last),
                             empty='🦗 Every story on the air was on the front pages too.'),
                boards.board('radio-skipped', '🙈', 'Front pages led, air skipped', '#ffc400',
                             f"stories in the front pages' top {TOP_FRONT} for {LED_HOURS} hours or more that fewer than "
                             f"{SKIP_SHARE:.0%} of those hours' newscasts mentioned; the bar is hours on top, the "
                             'figure beside it the newscasts that did', skipped(last, now),
                             empty="🦗 The newscasts got to every one of the front pages' big stories.")]
        self.template.write({'title': 'On the radio', 'hours': hrs, 'stickers': stickers(store), 'lane': swimlane(hrs),
                             'pair': pair, 'key': show_key(), 'pair_key': show_key(with_nobody=True),
                             'casts': sum(bool(c['items']) for c in store.values()), 'inks': INK})
        logger.info("...%d newscasts", len(store))
