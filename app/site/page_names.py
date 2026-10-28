"""Who's in the news (#165 follow-up): each person, country, place, organization or group the local model names in
today's stories (app/analysis/entities.py), with those stories and the outlets on them by lean.

Oct 28 (the site redo): the masonry of identical purple cards became a ranked strip of names (the bar: outlets that
named it in a headline) and a pair, Named more by the left | by the right, against the day's mix; each name's stories
and the motifs told about it in its hover card. The strip was to be colored by kind (person, place, organization),
but the names come without one (the model is asked only for names), so it's colored by how new the name is to the
news: first named in the last two days, this week, or before."""
from datetime import timedelta as td

import pytz

from app.analysis import entities
from app.site import boards as strips
from app.site.common import TemplateHandler, motif_href
from app.site.page_sagas import eastern
from app.utils import get_logger

logger = get_logger(__name__)
EASTERN = pytz.timezone('America/New_York')
NOW_SLACK = td(minutes=30)


SHOWN = 20  # names in the strip before "show all"
STORIES = 6  # a name's stories in its hover card, the rest counted
MOTIFS = 6  # the stories told about a name shown in its card, the most told first
WIDE = 15  # outlets: a name in one story today is listed if that story reached this many
SIDE_LEAST = 6  # left and right outlets naming it, at least, for the Named more by... pair
SIDE_EXCESS = 2  # outlets more than the day's mix would give a side, at least
SIDE_GAP = 0.1  # and a share of left (or right) at least this far past the day's mix
PER_SIDE = 10
# How new each name is to the news: first named (in any saved story) within these days. Fixed colors, not lean's
FRESH = [('new', 2, '🆕', 'New', '#ffc400', 'first named in the last two days'),
         ('week', 7, '📅', 'This week', '#00c2a8', 'first named earlier this week'),
         ('running', None, '🔁', 'Before this week', '#ff4fa3', 'named before this week too')]


def today_start():
    """The start of today in Eastern time, as naive UTC"""
    from datetime import datetime
    midnight = EASTERN.localize(datetime.now(EASTERN).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0))
    return midnight.astimezone(pytz.UTC).replace(tzinfo=None)


def freshness(first, now) -> dict:
    """Which of FRESH a name first named at `first` (naive UTC) is"""
    for key, days, mark, name, ink, about in FRESH:
        if days is None or first >= now - td(days=days):
            return {'key': key, 'mark': mark, 'name': name, 'ink': ink, 'about': about}


def fresh_key() -> list[dict]:
    return [{'name': name, 'mark': mark, 'ink': ink, 'about': about} for _, _, mark, name, ink, about in FRESH]


def tip(e: dict) -> str:
    """A name's plain card (the page's script draws a richer one from the same facts)"""
    lines = [f"Named in a headline by {e['outlets']} outlets: 🫏 {e['left']} left · ⚖️ {e['center']} center · "
             f"🐘 {e['right']} right" + (f" · ⚪ {e['unrated']} unrated" if e['unrated'] else ''),
             f"{e['fresh']['mark']} {e['fresh']['about']} ({e['since']})"]
    lines += [f"🗞️ {st['label']} ({st['outlets']} outlets)" for st in e['stories'][:STORIES]]
    return '\n'.join(lines)


def name_row(e: dict, value, top, figure: str, split: float | None = None) -> dict:
    return strips.row(e['name'], None, value, top, figure, tip=tip(e), ink=e['fresh']['ink'], mark=e['fresh']['mark'],
                      mark_label=e['fresh']['about'], split=split)


def boards(found: list[dict]) -> tuple[dict, list[dict], float]:
    """The strip of every name, by outlets that named it; and the pair, the names named more by left-leaning (or
    right-leaning) outlets than the day's mix would give them, by how many more"""
    top = max((e['outlets'] for e in found), default=1)
    everyone = strips.board('names-all', '🗣️', 'Most named today', '#8a5cff',
                            'the bar is how many outlets named it in a headline; point at a name for its stories',
                            [name_row(e, e['outlets'], top, f"{e['outlets']} outlets") for e in found],
                            empty="🦗 No names in today's stories yet.")
    left, right = sum(e['left'] for e in found), sum(e['right'] for e in found)
    base = left / (left + right) if left + right else 0.5
    sided = [e for e in found if e['left'] + e['right'] >= SIDE_LEAST]
    for e in sided:
        e['excess'] = e['left'] - base * (e['left'] + e['right'])  # more left than the day's mix gives it (or fewer)
    pair = []
    for side, emoji, stage, sign in (('left', '🫏', '#3a86ff', 1), ('right', '🐘', '#ff4f6d', -1)):
        rows = sorted((e for e in sided if sign * e['excess'] >= SIDE_EXCESS
                       and sign * (e['left'] / (e['left'] + e['right']) - base) >= SIDE_GAP), key=lambda e: -sign * e['excess'])
        rows = rows[:PER_SIDE]
        most = max((e['left'] + e['right'] for e in rows), default=1)
        pair.append(strips.board(
            f'names-{side}', emoji, f'Named more by the {side}', stage,
            f"named by more {side}-leaning outlets than the day's mix would give it; the bar is the left- and "
            "right-leaning outlets that named it, blue for left",
            [name_row(e, e['left'] + e['right'], most, f"🫏 {e['left']} · {e['right']} 🐘",
                      split=e['left'] / (e['left'] + e['right'])) for e in rows],
            empty=f'🤷 No name leans {side} of the day today.'))
    return everyone, pair, base


class NamesPage:
    """Who's in the news today (Oct 12, the person: "make it a bit more coherent now that we have a week of data ... it's
    too much under each name ... probably just who's in the news today"): each name in a story on the front pages
    today, one story enough, by how many outlets named it in a headline; its stories in its hover card"""
    def __init__(self, dh=None):
        self.template = TemplateHandler('names.html')

    def generate(self):
        logger.info("Generating names page...")
        from app.site import page_story
        since = today_start()
        # in two stories today, or in one that reached at least WIDE outlets (the long tail stays out: Oct 12, 259 names)
        found = [e for e in entities.history(least=1, since=since) if len(e['stories']) >= 2 or e['outlets'] >= WIDE]
        latest = max((st['last'] for e in found for st in e['stories']), default=None)
        # when each was first named, in any saved story (a name in today's stories may go back weeks)
        first = {e['name']: e['first'] for e in entities.history(least=1)} if found else {}
        with_page = {st['id'] for st in page_story.recent_stories()} | page_story.archived_ids()
        for e in found:
            for st in e['stories']:
                st['now'] = st['last'] >= latest - NOW_SLACK
                st['when'] = eastern(st['first'])
                st['page'] = page_story.page_name(st['id']) if st['id'] in with_page else None
            e['stories'].sort(key=lambda st: (not st['now'], -st['outlets']))  # on the front pages now, the widest first
            e['now'] = any(st['now'] for st in e['stories'])
            e['first'] = min(first.get(e['name'], e['first']), e['first'])
            e['fresh'] = freshness(e['first'], latest or since)
            e['since'] = 'since ' + eastern(e['first']).rsplit(',', 1)[0]
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
        everyone, pair, base = boards(found)
        cards = {e['name']: {
            'outlets': e['outlets'], 'left': e['left'], 'center': e['center'], 'right': e['right'],
            'unrated': e['unrated'], 'fresh': e['fresh']['about'], 'mark': e['fresh']['mark'], 'since': e['since'],
            'text': e['text'],
            'stories': [{'label': st['label'] or '', 'outlets': st['outlets'], 'when': st['when'], 'now': st['now'],
                         'href': st['page'] or (f"index.html#s-{st['id']}" if st['now'] else None)}
                        for st in e['stories'][:STORIES]],
            'more': max(0, len(e['stories']) - STORIES),
            'motifs': [{'name': m['name'], 'claims': m['claims'], 'href': motif_href(m['id'])} for m in e['motifs']]}
            for e in found}
        self.template.write({'title': "Who's in the news", 'names': found, 'shown': SHOWN, 'everyone': everyone,
                             'pair': pair, 'base': round(100 * base), 'fresh_key': fresh_key(), 'cards': cards,
                             'today': datetime_eastern_today()})
        logger.info("...%d names today", len(found))


def datetime_eastern_today() -> str:
    from datetime import datetime
    return datetime.now(EASTERN).strftime('%A, %B %-d')
