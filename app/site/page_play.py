"""The Play page (Oct 28, before the site goes on Bluesky and Mastodon): three small games from the day's headlines.
Real or satire?, Guess the lean, and Same story, two papers. The puzzles are picked at build time
(app/analysis/play.py); the page's own script runs the games, with nothing sent anywhere.

Scored on both kinds of right answer (news-literacy games that reward calling things "fake" only teach people to
call more things fake), and never a verdict on a headline's truth: the lean is the outlet's rating, from AllSides."""
from datetime import datetime

from app.site.common import TemplateHandler, chip_style, outlet_icon, short_name
from app.utils import get_logger

logger = get_logger(__name__)

RATING = {-2: 'Left', -1: 'Lean Left', 0: 'Center', 1: 'Lean Right', 2: 'Right'}  # AllSides' own words
SIDE_EMOJI = {'left': '🫏', 'center': '⚖️', 'right': '🐘'}
GROUP_WORD = {'left': 'a left-leaning satire site', 'right': 'a right-leaning satire site', 'center': 'a satire site'}
EMPTY = {'day': None, 'satire': [], 'lean': [], 'pair': None}


def chip(outlet: str, bias) -> dict:
    """An outlet chip's look: its lean color and icon (unrated outlets get the dashed white chip)"""
    try:
        return {'style': chip_style(outlet, bias or 0), 'icon': outlet_icon(outlet), 'short': short_name(outlet)}
    except (KeyError, TypeError):  # the build's outlet globals aren't set (a page rendered on its own)
        return {'style': '', 'icon': '', 'short': outlet}


def percent(p: float) -> int:
    return round(100 * p)


def satire_model_line(q: dict) -> str:
    p = q['p']
    said = 'satire' if p >= 0.5 else 'real news'
    sure = percent(p if p >= 0.5 else 1 - p)
    right = (p >= 0.5) == (q['kind'] == 'satire')
    return f"Our word model called it {said}, {sure}% sure: {'right' if right else 'fooled'}."


def lean_model_line(q: dict) -> str:
    return f"Our word model was {percent(q['conf'])}% sure this came from a {q['side']}-rated outlet."


def context(games: dict, when: datetime | None = None) -> dict:
    """The page's context from play.build()'s puzzles: each puzzle with its chips and its lines, the answer key the
    script needs, and the share card"""
    day = games.get('day')
    day_text = datetime.strptime(day, '%Y-%m-%d').strftime('%A, %b %-d') if day else ''
    short_day = datetime.strptime(day, '%Y-%m-%d').strftime('%b %-d') if day else ''
    satire = []
    for q in games.get('satire') or []:
        satire.append({**q, 'chip': chip(q['outlet'], q.get('bias')) if q['kind'] == 'real' else None,
                       'group_word': GROUP_WORD.get(q.get('group') or 'center', 'a satire site'),
                       'model': satire_model_line(q), 'external': not q['link'].startswith('story-')})
    lean = []
    for q in games.get('lean') or []:
        lean.append({**q, 'chip': chip(q['outlet'], q['bias']), 'rating': RATING.get(q['bias'], ''),
                     'emoji': SIDE_EMOJI[q['side']], 'model': lean_model_line(q),
                     'external': not q['link'].startswith('story-'),
                     'other': [{**o, 'chip': chip(o['outlet'], o['bias']), 'rating': RATING.get(o['bias'], ''),
                                'emoji': SIDE_EMOJI[o['side']]} for o in q.get('other') or []]})
    pair = games.get('pair')
    image = None
    if pair:
        pair = {**pair}
        for k in ('left', 'right'):
            pair[k] = {**pair[k], 'chip': chip(pair[k]['outlet'], pair[k]['bias']),
                       'rating': RATING.get(pair[k]['bias'], '')}
        try:
            from app.site import share_images
            image = share_images.two_papers_card(pair['label'], pair['left'], pair['right'], short_day)
        except Exception as e:  # noqa: BLE001 - the page stands without its card; the site's is shown instead
            logger.warning("Play: share card: %s", e)
    key = {'day': day or '', 'label': short_day, 'satire': [q['kind'] for q in satire],
           'lean': [q['side'] for q in lean]}
    return {'title': 'Play', 'day': day, 'day_text': day_text, 'satire': satire, 'lean': lean, 'pair': pair,
            'key': key, 'og_image': image, 'og_title': '🎲 Real or satire? Headline games · bignews.day',
            'og_description': "Five headlines: real news or a joke? Then guess which side's outlet ran it, and see one "
                              "story as a left paper and a right paper told it. New every day.",
            'og_image_alt': (f"Same story, two papers: {pair['left']['outlet']} and {pair['right']['outlet']} on "
                             f"{pair['label']}") if pair else None}


class PlayPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('play.html')

    def generate(self):
        logger.info("Generating play page...")
        from app.analysis import play
        try:
            games = play.build()
        except Exception as e:  # noqa: BLE001 - the page says the games are resting rather than failing the build
            logger.exception("Play: no puzzles: %s", e)
            games = EMPTY
        self.template.write(context(games))
