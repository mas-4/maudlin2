"""On TV: what the cable and news channels kept on screen (their chyrons, from the Internet Archive's Third Eye), and
for how long, beside what the front pages led with (app/chyrons.py).

Oct 28 (the site redo): the page was a table that squeezed into tall narrow cells on a phone and an endless grid of
hour cards. Now: the hours as a swimlane, a lane per channel, each hour's captions in its hover card; the day's stories
by minutes on screen as a ranked strip with a bar in the channels' inks; and a pair that answers itself, what was on
air but not on the front pages beside what the front pages led with and the air skipped."""
import glob
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta as td

import pytz

from app import chyrons
from app.site import boards
from app.site.common import TemplateHandler
from app.site.page_sagas import EASTERN
from app.utils import get_logger
from app.utils.store import read_json

logger = get_logger(__name__)
HOURS = 12  # the latest hours shown hour by hour, in the swimlane
TOP = 4  # captions in each channel-hour's card
STORIES = 12  # stories by time on screen
OFF_AIR = 10  # rows in each of the pair
TOP_FRONT = 10  # a story "led" the front pages in an hour it was among their top this many...
LED_HOURS = 3  # ...for at least this many of the day's hours...
SKIPPED_SECONDS = 5 * 60  # ...and the air "skipped" it at under this much time on screen, the four channels together
COMMON_FROM = 20  # titles grouped (group_titles) before any word counts as too common to join on
CHANNEL_ORDER = ['CNNW', 'FOXNEWSW', 'MSNOW', 'BBCNEWS']
CHANNEL_INK = {'CNNW': '#cc0000', 'FOXNEWSW': '#003366', 'MSNOW': '#6a3fd1', 'BBCNEWS': '#b80000'}
CHANNEL_MARK = {'CNNW': 'CNN', 'FOXNEWSW': 'FOX', 'MSNOW': 'MS', 'BBCNEWS': 'BBC'}  # the disc's label: never color alone
NOBODY = {'ink': boards.UNCOLORED, 'mark': '📵', 'label': 'no channel'}


def matched(days: int = 2) -> list[dict]:
    """The matched captions of the latest `days` UTC days, oldest first"""
    out = []
    for path in sorted(glob.glob(os.path.join(chyrons.FOLDER, 'matched-*.json')))[-days:]:
        for c in read_json(path, []):
            out.append(dict(c, at=datetime.fromisoformat(c['at'])))
    return out


def minutes(seconds: int) -> str:
    return f'{seconds / 60:.0f} min' if seconds >= 90 else f'{seconds} s'


def eastern(at: datetime) -> datetime:
    return pytz.UTC.localize(at).astimezone(EASTERN)


def hour_label(hour: datetime, first: bool = False) -> str:
    """An hour on the swimlane's axis: "3 PM", with the day at midnight and on the first"""
    return hour.strftime('%a %-I %p') if first or hour.hour == 0 else hour.strftime('%-I %p')


STOP = {'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'at', 'by', 'with', 'as', 'is', 'are', 'was',
        'be', 'from', 'its', 'it', 'this', 'that', 'after', 'over', 'into', 'than', 'new', 'says', 'say', 'said', 'amid',
        'near', 'ahead', 'about', 'up', 'out', 'not', 'will', 'has', 'have', 'had', 'his', 'her', 'their', 'more', 'two',
        'one'}


def words(text: str) -> set[str]:
    """A title's content words, lowercase, a plural's s dropped, for grouping wordings of one story"""
    return {w[:-1] if len(w) > 4 and w.endswith('s') else w for w in re.findall(r"[a-z0-9'-]{3,}", text.lower())
            if w not in STOP}


def group_titles(items: list[dict], text=lambda i: i['text'], least: int = 2, common: float = 0.15) -> list[list]:
    """Wordings of one story together: two titles join when they share `least` content words, not counting the words
    in more than `common` of all the titles (election, midterm: they'd join everything). Joined titles join groups."""
    ws = [words(text(i)) for i in items]
    df = Counter(w for s in ws for w in s)
    cut = common * len(items) if len(items) >= COMMON_FROM else len(items)  # a few titles: no word too common
    ws = [{w for w in s if df[w] <= cut} for s in ws]
    parent = list(range(len(items)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    by_word = defaultdict(list)
    for i, s in enumerate(ws):
        for w in s:
            by_word[w].append(i)
    for i, s in enumerate(ws):
        near = Counter(j for w in s for j in by_word[w] if j > i)
        for j, n in near.items():
            if n >= least or ws[i] == ws[j]:
                parent[root(j)] = root(i)
    groups = defaultdict(list)
    for i in range(len(items)):
        groups[root(i)].append(items[i])
    return list(groups.values())


def channel_mark(ch: str | None) -> dict:
    """A row's disc: the channel's ink and its short name, or no channel"""
    if not ch:
        return NOBODY
    return {'ink': CHANNEL_INK[ch], 'mark': CHANNEL_MARK[ch], 'label': chyrons.CHANNELS[ch]}


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


def most_on_screen(table: list[dict]) -> list[dict]:
    """The story table as a ranked strip: a bar in parts, one per channel in its ink, on the scale of the biggest
    total; the disc is the channel that gave it the most time"""
    top = max((r['total'] for r in table), default=1) or 1
    out = []
    for r in table:
        lead = max(CHANNEL_ORDER, key=lambda ch: r['by'][ch])
        tip = '\n'.join([f"#{r['rank']} on the front pages at best"]
                        + [f"{chyrons.CHANNELS[ch]}: {minutes(r['by'][ch])}" for ch in CHANNEL_ORDER if r['by'][ch]])
        out.append({'name': r['label'], 'href': None, 'figure': minutes(r['total']), 'tip': tip,
                    'parts': [{'ink': CHANNEL_INK[ch], 'mark': CHANNEL_MARK[ch], 'share': 100 * r['by'][ch] / top}
                              for ch in CHANNEL_ORDER if r['by'][ch]],
                    'rank': r['rank'], **{f'mark_{k}': v for k, v in channel_mark(lead).items()}})
    return out


def hours(caps: list[dict]) -> list[dict]:
    """The latest HOURS hours (Eastern), newest first: each channel's longest-running captions in that hour"""
    by_hour = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'seconds': 0})))
    programs = defaultdict(Counter)
    for c in caps:
        local = eastern(c['at']).replace(minute=0, second=0, microsecond=0)
        g = by_hour[local][c['channel']][c['text']]
        g['seconds'] += c['seconds']
        g.update({k: c[k] for k in ('story', 'label', 'rank') if k in c})
        if c.get('program'):
            programs[(local, c['channel'])][c['program']] += c['seconds']
    out = []
    for hour in sorted(by_hour, reverse=True)[:HOURS]:
        channels = []
        for ch in CHANNEL_ORDER:
            caps_ = sorted(({'text': t, **g} for t, g in by_hour[hour][ch].items()), key=lambda g: -g['seconds'])
            if caps_:
                prog = programs[(hour, ch)].most_common(1)
                channels.append({'channel': ch, 'name': chyrons.CHANNELS[ch], 'ink': CHANNEL_INK[ch],
                                 'program': prog[0][0] if prog else '',
                                 'seconds': sum(g['seconds'] for g in caps_),
                                 'on_front': sum(g['seconds'] for g in caps_ if g.get('story')),
                                 'captions': [dict(g, time=minutes(g['seconds'])) for g in caps_[:TOP]],
                                 'more': max(len(caps_) - TOP, 0)})
        out.append({'hour': hour, 'label': hour.strftime('%a %b %-d, %-I %p'), 'channels': channels})
    return out


def caption_line(g: dict) -> str:
    where = (f"#{g['rank']} on the front pages, as “{g['label']}”" if g.get('story')
             else 'not on the front pages')
    return f"“{g['text']}” · {g['time']} · {where}"


def swimlane(hrs: list[dict]) -> dict:
    """The hours as a swimlane, oldest on the left: a lane per channel, a cell per channel-hour with its lead caption
    and its place on the front pages, every caption of the hour in the cell's hover card"""
    cols = sorted(hrs, key=lambda h: h['hour'])
    lanes = [{'channel': ch, 'name': chyrons.CHANNELS[ch], 'ink': CHANNEL_INK[ch], 'mark': CHANNEL_MARK[ch]}
             for ch in CHANNEL_ORDER if any(c['channel'] == ch for h in cols for c in h['channels'])]
    row_of = {lane['channel']: i for i, lane in enumerate(lanes, 2)}
    cells = []
    for j, h in enumerate(cols, 2):
        for c in h['channels']:
            lead = c['captions'][0]
            share = round(100 * c['on_front'] / (c['seconds'] or 1))
            lines = [caption_line(g) for g in c['captions']]
            if c['more']:
                lines.append(f"…and {c['more']} shorter caption{'s' if c['more'] > 1 else ''}")
            lines.append(f"{share}% of its captions' time on front-page stories")
            cells.append({'row': row_of[c['channel']], 'col': j, 'flip': len(cols) + 3 - j, 'ink': c['ink'],
                          'lead': lead['text'], 'rank': lead.get('rank') if lead.get('story') else None,
                          'share': share, 'head': f"📺 {c['name']}, {h['label']} ET"
                                                  + (f" · {c['program']}" if c['program'] else ''),
                          'tip': '\n'.join(lines)})
    return {'lanes': lanes, 'cells': cells,
            'hours': [{'label': hour_label(h['hour'], first=j == 2), 'col': j, 'flip': len(cols) + 3 - j}
                      for j, h in enumerate(cols, 2)], 'cols': len(cols)}


def front_hours(since: datetime, until: datetime) -> dict[int, dict]:
    """The stories among the front pages' TOP_FRONT in each hour from `since` to `until` (UTC): id -> {label, hours,
    best}"""
    out = {}
    hour = since.replace(minute=0, second=0, microsecond=0)
    while hour < until:  # 24 hours, not 25
        try:
            front = chyrons.front_at(hour + td(minutes=30))
        except Exception as e:  # noqa: BLE001 - a database without snapshots: no front pages to compare
            logger.warning("TV: front pages at %s: %s", hour, e)
            front = []
        for st in front[:TOP_FRONT]:
            r = out.setdefault(st['id'], {'id': st['id'], 'label': st['label'], 'hours': 0, 'best': st['rank']})
            r['hours'] += 1
            r['best'] = min(r['best'], st['rank'])
        hour += td(hours=1)
    return out


def off_front(caps: list[dict], since: datetime) -> list[dict]:
    """On air, not on the front pages: the captions matched to no front-page story since `since`, their wordings of
    one story together, by minutes on screen; each row in the ink of the channel that ran it longest"""
    by_text = {}
    for c in caps:
        if c['at'] < since or c.get('story'):
            continue
        g = by_text.setdefault((c['channel'], c['text']), {'text': c['text'], 'channel': c['channel'], 'seconds': 0,
                                                           'first': c['at'], 'last': c['at']})
        g['seconds'] += c['seconds']
        g['first'], g['last'] = min(g['first'], c['at']), max(g['last'], c['at'])
    groups = []
    for items in group_titles(list(by_text.values())):
        by = Counter()
        for i in items:
            by[i['channel']] += i['seconds']
        items.sort(key=lambda i: -i['seconds'])
        groups.append({'items': items, 'by': by, 'seconds': sum(by.values()),
                       'first': min(i['first'] for i in items), 'last': max(i['last'] for i in items)})
    groups = sorted(groups, key=lambda g: -g['seconds'])[:OFF_AIR]
    top = max((g['seconds'] for g in groups), default=1)
    rows = []
    for g in groups:
        lead = g['by'].most_common(1)[0][0]
        m = channel_mark(lead)
        others = [i['text'] for i in g['items'][1:4]]
        tip = '\n'.join([' · '.join(f"{chyrons.CHANNELS[ch]} {minutes(n)}" for ch, n in g['by'].most_common()),
                         f"On screen {eastern(g['first']):%-I:%M %p} to {eastern(g['last']):%-I:%M %p} ET"]
                        + ([f"Also worded: “{t}”" for t in others]))
        rows.append(boards.row(g['items'][0]['text'], None, g['seconds'], top, minutes(g['seconds']), tip=tip,
                               ink=m['ink'], mark=m['mark'], mark_label=m['label']))
    return rows


def skipped(caps: list[dict], led: dict[int, dict], since: datetime) -> list[dict]:
    """Front pages led, air skipped: the stories among the front pages' top for LED_HOURS hours or more that got under
    SKIPPED_SECONDS on screen; the bar is the hours they led, the row in the ink of the channel that gave it the most
    of what little time it got (or none)"""
    on = defaultdict(Counter)
    for c in caps:
        if c['at'] >= since and c.get('story'):
            on[c['story']][c['channel']] += c['seconds']
    items = sorted((r for r in led.values() if r['hours'] >= LED_HOURS and sum(on[r['id']].values()) < SKIPPED_SECONDS),
                   key=lambda r: (-r['hours'], r['best'], r['label']))[:OFF_AIR]
    top = max((r['hours'] for r in items), default=1)
    rows = []
    for r in items:
        by = on[r['id']]
        m = channel_mark(by.most_common(1)[0][0] if by else None)
        air = ' · '.join(f"{chyrons.CHANNELS[ch]} {minutes(n)}" for ch, n in by.most_common()) or 'Not on any channel'
        tip = (f"Among the front pages' top {TOP_FRONT} for {r['hours']} of the last 24 hours, #{r['best']} at best\n"
               f"On screen: {air}")
        rows.append(boards.row(r['label'], None, r['hours'], top,
                               f"{r['hours']} h · {minutes(sum(by.values())) if by else 'none'}", tip=tip,
                               ink=m['ink'], mark=m['mark'], mark_label=m['label']))
    return rows


def channel_key(with_nobody: bool = False) -> list[dict]:
    key = [{'name': chyrons.CHANNELS[ch], 'mark': CHANNEL_MARK[ch], 'ink': CHANNEL_INK[ch]} for ch in CHANNEL_ORDER]
    return key + ([{'name': 'no channel', 'mark': NOBODY['mark'], 'ink': NOBODY['ink']}] if with_nobody else [])


class TvPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('tv.html')

    def generate(self):
        logger.info("Generating TV page...")
        caps = matched()
        latest = max((c['at'] for c in caps), default=datetime.utcnow())
        since = latest - td(hours=24)
        table = story_table(caps, since)
        pair = [boards.board('on-air', '📡', 'On air, not on the front pages', '#ff6b1a',
                             'captions matched to none of the front pages\' stories, wordings of one story together; '
                             'the bar is minutes on screen, the four channels together', off_front(caps, since),
                             empty='🦗 Everything on screen was on the front pages too.'),
                boards.board('skipped', '🙈', 'Front pages led, air skipped', '#ffc400',
                             f"stories in the front pages' top {TOP_FRONT} for {LED_HOURS} hours or more with under "
                             f"{SKIPPED_SECONDS // 60} minutes on screen; the bar is hours on top, the figure "
                             "beside it minutes on air", skipped(caps, front_hours(since, latest) if caps else {}, since),
                             empty='🦗 The channels gave every big front-page story some time.')]
        self.template.write({'title': 'On TV', 'stories': most_on_screen(table), 'lane': swimlane(hours(caps)),
                             'pair': pair, 'key': channel_key(), 'pair_key': channel_key(with_nobody=True)})
        logger.info("...%d captions", len(caps))
