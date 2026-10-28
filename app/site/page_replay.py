"""The Replay (replayed.html): the passages heard word for word on many shows this week (app/analysis/replay.py),
the clips first, each with when and where it aired by the shows' lean, then the sponsor reads and promos, grouped by
which sides' shows carried them."""
import re
from datetime import datetime, timedelta as td
from html import escape

from app.analysis import replay
from app.site.common import TemplateHandler
from app.site.story_charts import Axis, _local, ticks
from app.utils import get_logger

logger = get_logger(__name__)

WEEK = td(days=7)  # passages heard in the last week of the window are shown
CARDS = 25  # clips shown as cards...
MORE = 60  # ...and listed after them
EXCERPT = 40  # words of a clip shown
AD_EXCERPT = 25
# The shows' lean groups (sidefeeds.SOURCES), in the order the lanes run, with the show chips' colors
LANES = [('left', '🫏', 'left'), ('center', '⚖️', 'center'), ('crossover', '🔀', 'crossover'), ('right', '🐘', 'right')]
INK = {'left': '#3a86ff', 'center': '#8a8f98', 'crossover': '#8a5cff', 'right': '#ff4f6d'}
WIDTH, LABEL_W, LANE_H = 480, 76, 18
PRONOUNS = {'i': 'I', "i'm": "I'm", "i've": "I've", "i'd": "I'd", "i'll": "I'll"}


def quote(text: str, most: int) -> str:
    """A passage as a quote: its first `most` words, with an ellipsis where it was cut, and one in front when it
    starts mid-sentence (lowercase); "i" as "I" where the transcript's words came back lowercase"""
    w = text.split()
    out = ' '.join(PRONOUNS.get(x, x) for x in w[:most]).rstrip(',;:')
    return ('…' if out[:1].islower() else '') + out + ('…' if len(w) > most else '')


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def when(iso: str) -> str:
    return _local(_utc(iso)).strftime('%b %-d, %-I:%M %p')


def clock(seconds: float | None) -> str | None:
    """Seconds into an episode as 1:02:03 or 12:34"""
    if seconds is None:
        return None
    s = int(seconds)
    return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60}:{s % 60:02d}'


def strip(airings: list[dict]) -> str:
    """Each airing as a dot at the feed's publish time, in a lane for its show's lean"""
    times = [_utc(a['published']) for a in airings]
    t0, t1 = min(times), max(times)
    span = max(t1 - t0, td(hours=6))
    pad = span / 20
    t0, t1 = t0 - pad, t0 + span + pad
    axis = Axis(t0, t1, LABEL_W, WIDTH - 12)
    top, bottom = 4, 4 + LANE_H * len(LANES)
    parts = []
    for t, label in ticks(t0, t1, most=5):
        x = axis.x(t)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" class="sc-grid"/>'
                     f'<text x="{x:.1f}" y="{bottom + 14}" class="sc-tick" text-anchor="middle">{escape(label)}</text>')
    for j, (group, emoji, name) in enumerate(LANES):
        y = top + j * LANE_H + LANE_H / 2
        # "crossover" explained in the label's hover card (index.js hoverCard reads an SVG <title>)
        tip = f'<title>{escape(CROSSOVER)}</title>' if group == 'crossover' else ''
        tab = ' tabindex="0"' if tip else ''
        parts.append(f'<text x="{LABEL_W - 8}" y="{y + 4}" class="sc-label" text-anchor="end"{tab}>{tip}{emoji} {name}</text>'
                     f'<line x1="{LABEL_W}" y1="{y}" x2="{WIDTH - 12}" y2="{y}" class="sc-lane"/>')
        for a, t in zip(airings, times):
            if a['group'] != group:
                continue
            at = f' (at {clock(a["at"])} in)' if a['at'] is not None else ''
            # A card beside the dot on hover, kept open by a click (index.js hoverCard), with a link to the episode
            link = (f' data-tip-href="{escape(a["url"])}" data-tip-link="the episode →"'
                    if (a.get('url') or '').startswith('http') else '')
            parts.append(f'<circle cx="{axis.x(t):.1f}" cy="{y}" r="5" fill="{INK[group]}" fill-opacity="0.85" '
                         f'stroke="#1f1f2e" stroke-width="1" tabindex="0" data-tip-head="{escape(a["show"])}"'
                         f'{link}><title>{when(a["published"])} ET{at}\n{escape(a["title"])}</title></circle>')
    height = bottom + 20
    return (f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" '
            f'class="story-chart replay-strip" aria-label="When each airing was published, by the lean of the show">'
            f'{"".join(parts)}</svg>')


def shows_of(airings: list[dict], detail: bool = True) -> list[dict]:
    """One chip per show, in lane order then by when it first aired it, linking to that first episode (its title in
    the chip's hover text with `detail`)"""
    first = {}
    for a in airings:
        first.setdefault(a['source'], a)
    order = [g for g, _, _ in LANES]
    return [{'name': a['show'], 'url': a['url'], 'ink': INK.get(a['group'], '#8a8f98'), 'lean': a['group'],
             'title': f'{a["group"]}, {when(a["published"])} ET' + (f': {a["title"]}' if detail else '')}
            for a in sorted(first.values(), key=lambda a: (order.index(a['group']) if a['group'] in order else 9,
                                                           a['published']))]


# "Crossover", said where its lane and its count appear (Oct 28: the label went unexplained): sidefeeds' loose group
CROSSOVER = ('Crossover: shows with listeners on both sides, like Rogan, Theo Von and Tim Dillon; a loose label by '
             'reputation, as left and right are')
# Who is speaking, where the words say so: a speaker naming themselves, an ad's sponsor
INTRO = re.compile(r"\b[Mm]y name(?: is|'s) (?P<name>[A-Z][\w'’-]+(?: [A-Z][\w'’-]+){0,3})"
                   r"(?:,? and (?P<what>I(?:'m| am) [^.!?,]{3,60}))?"
                   r"|(?:^|(?<=[.!?] ))(?P<here>[A-Z][a-z'’]+(?: [A-Z][a-z'’]+){0,2}) here\.")
APPROVE = re.compile(r"\bI(?:'m| am) ([A-Z][\w'’.-]+(?: [A-Z][\w'’.-]+){0,3}),? and I approve this message")
PAID = re.compile(r"\b[Pp]aid for by ((?:[A-Z0-9][\w'’&-]*|for|of|the|and)(?: (?:[A-Z0-9][\w'’&-]*|for|of|the|and)){0,7})")
NAME = re.compile(r"\b[A-Z][a-z'’]+(?:[- ][A-Z][a-z'’]+){0,2}\b")
NOT_NAMES = {'This', 'That', 'There', 'They', 'Well', 'Right', 'Quote', 'Okay', 'Today', 'Sir', 'God', 'America',
             'American', 'Americans', 'President', 'Senate', 'Congress', 'Republican', 'Republicans', 'Democrat',
             'Democrats', 'Democratic', 'Party', 'State', 'States', 'United', 'House', 'White', 'Election'}
NAMED_IN = 2  # a name in the clip counts when at least this many of its episodes' titles have it too
NAMES = 3  # names given


def name_like(text: str) -> list[str]:
    """The clip's words that look like names: capitalized runs, a possessive's 's dropped; a single word only when
    it's 4 letters or more, not a common capitalized word, and, at the start of a sentence, never seen lowercase"""
    lower = set(re.findall(r"\b[a-z][a-z'’]+\b", text))
    out = []
    for m in NAME.finditer(text):
        n = re.sub(r"['’]s\b", '', m.group(0))
        if ' ' not in n and '-' not in n:
            starts = m.start() == 0 or text[:m.start()].rstrip()[-1:] in '.!?"“'
            if n in NOT_NAMES or len(n) < 4 or (starts and n.lower() in lower):
                continue
        out.append(n)
        if ' ' in n and len(last := n.split()[-1]) >= 4 and last not in NOT_NAMES:  # a surname, as titles have it
            out.append(last)
    return out


def about(p: dict) -> str | None:
    """A line on who is speaking or what the clip is, where the words or the episodes say so: a speaker naming
    themselves, an ad's "I approve this message" or "paid for by", else the names in the clip that the episodes that
    played it also have in their titles"""
    text = ' '.join(p['text'].split())
    if m := APPROVE.search(text):
        return f'🗳️ The candidate speaking: {m.group(1)}, who “approves this message”'
    if p['kind'] == 'campaign' and (m := PAID.search(text)):
        return f'🗳️ Paid for by {m.group(1).rstrip(".")}, it says'
    if m := INTRO.search(text):
        if m['here']:
            return f'🗣️ Speaking, in their own words: {m["here"]} (“{m["here"]} here”)'
        return f'🗣️ Speaking, in their own words: {m["name"]}' + (f', “{m["what"]}”' if m['what'] else '')
    titles = [a['title'] or '' for a in {a['source'] + (a['title'] or ''): a for a in p['airings']}.values()]
    names = []
    for n in dict.fromkeys(name_like(text)):
        k = sum(bool(re.search(rf'\b{re.escape(n)}\b', t, re.I)) for t in titles)
        if k >= NAMED_IN:
            names.append((n, k))
    # a longer name wins over its parts ("Amy Acton" over "Acton")
    names = [(n, k) for n, k in names if not any(n != o and n in o.split() for o, _ in names)]
    names.sort(key=lambda x: -x[1])
    if not names:
        return None
    return ('📝 Named in the clip and in the titles of the episodes that played it: '
            + ', '.join(f'{n} ({k} of {len(titles)})' for n, k in names[:NAMES]))


def card(p: dict) -> dict:
    airings = [dict(a, when=when(a['published']), clock=clock(a['at'])) for a in p['airings']]
    chips = shows_of(p['airings'])
    return {'id': p['id'], 'kind': p['kind'], 'why': p['why'], 'quote': quote(p['text'], EXCERPT), 'about': about(p),
            'shows': p['shows'], 'airings': airings, 'chips': chips, 'strip': strip(p['airings']),
            'first': airings[0], 'span': f'{when(p["first"])} to {when(p["last"])}',
            'sides': [(name, emoji, n) for g, emoji, name in LANES
                      if (n := sum(c['lean'] == g for c in chips))]}


# The sponsor reads' groups, by whether left- and right-leaning shows carried them
SIDES = [('both', '🫏🐘', 'On left- and right-leaning shows alike'),
         ('left', '🫏', 'On left-leaning shows, none leaning right'),
         ('right', '🐘', 'On right-leaning shows, none leaning left'),
         ('neither', '⚖️', 'On center and crossover shows only')]


def side_of(groups: set) -> str:
    return ('both' if {'left', 'right'} <= groups else 'left' if 'left' in groups else 'right' if 'right' in groups
            else 'neither')


def sponsor_groups(ads: list[dict]) -> list[dict]:
    """The sponsor reads by whether left- and right-leaning shows carried them, each heard on the most shows first"""
    by = {}
    for p in ads:
        by.setdefault(side_of({a['group'] for a in p['airings']}), []).append(
            {'quote': quote(p['text'], AD_EXCERPT), 'shows': p['shows'], 'airings': len(p['airings']),
             'span': f'{when(p["first"])} to {when(p["last"])}', 'chips': shows_of(p['airings'], detail=False),
             'why': p['why']})
    return [{'key': key, 'emoji': emoji, 'label': label, 'reads': by[key]} for key, emoji, label in SIDES if key in by]


def week(result: dict) -> list[dict]:
    """The passages heard at least once in the last week of the window"""
    if not result.get('until'):
        return []
    since = _utc(result['until']) - WEEK
    return [p for p in result['passages'] if _utc(p['last']) >= since]


class ReplayPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('replayed.html')

    def generate(self):
        logger.info("Generating the Replay page...")
        try:
            result = replay.load()
        except Exception as e:  # noqa: BLE001 - e.g. a database without transcripts yet
            logger.warning("Replay: %s", e)
            result = {'passages': [], 'transcripts': 0}
        shown = week(result)
        clips = [p for p in shown if p['kind'] in ('clip', 'campaign')]
        ads = [p for p in shown if p['kind'] == 'ad']
        cards = [card(p) for p in clips[:CARDS]]
        more = [{'quote': quote(p['text'], 18), 'shows': p['shows'], 'airings': len(p['airings']),
                 'span': f'{when(p["first"])} to {when(p["last"])}', 'chips': shows_of(p['airings'], detail=False)}
                for p in clips[CARDS:CARDS + MORE]]
        sources = {a['source'] for p in shown for a in p['airings']}
        self.template.write({
            'title': 'The Replay', 'cards': cards, 'more': more, 'sponsors': sponsor_groups(ads),
            'ads': len(ads), 'clips': len(clips), 'unlisted': max(len(clips) - CARDS - MORE, 0), 'glitches': sum(p['kind'] == 'glitch' for p in shown),
            'transcripts': result.get('transcripts', 0), 'shows_heard': len(sources),
            'until': when(result['until']) if result.get('until') else None,
            'since': when((_utc(result['until']) - WEEK).isoformat()) if result.get('until') else None,
            'top': cards[0]['shows'] if cards else 0, 'min_shows': replay.MIN_SHOWS, 'k': replay.K,
            'crossover': CROSSOVER,
            'og_description': 'Clips, campaign ads and statements heard word for word on many shows this week, '
                              'left and right, and when each show played them.',
        })
        logger.info("...%d clips, %d sponsor reads", len(clips), len(ads))
