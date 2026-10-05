"""Daily archive pages (#125): each production run saves the front page as that day's edition (data/archive, overwritten
through the day, so the day's last run is the one that stays) and every build publishes the editions at /YYYY/MM/DD/,
plus archive.html listing them. Links in an edition are made absolute so styles and icons still load from its folder.
Debug builds never save, so a preview's stale data can't become an edition."""
import os
import re
import shutil
from datetime import datetime as dt

import pytz

from app.site.common import TemplateHandler
from app.utils import Config, Constants, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'archive')
DAYS = os.path.join(FOLDER, 'days.json')
RELATIVE = re.compile(r'''(\b(?:href|src)=["'])(?!https?:|#|/|mailto:|data:)([^"']+)''')


def _today() -> str:
    return dt.now(pytz.UTC).astimezone(Constants.TimeConstants.timezone).strftime('%Y-%m-%d')


def _days() -> dict:
    return read_json(DAYS, {})


def edition(page: str, day: str) -> str:
    """The front page as a dated edition: absolute links, the icons' paths too, and a ribbon saying what it is."""
    page = RELATIVE.sub(lambda m: m.group(1) + '/' + m.group(2).removeprefix('./'), page)
    page = page.replace('"icons/', '"/icons/')
    when = dt.strptime(day, '%Y-%m-%d').strftime('%A, %B %-d, %Y')
    ribbon = (f'<div class="archive-ribbon">📅 The front page as of the end of {when}. '
              '<a href="/">Today’s front page</a> · <a href="/archive.html">all days</a></div>')
    return re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + ribbon, page, count=1)


def save(newsday: dict | None):
    """Keep today's front page as today's edition (production runs only)."""
    if Config.debug:
        return
    os.makedirs(FOLDER, exist_ok=True)
    day = _today()
    shutil.copyfile(os.path.join(Config.build, 'index.html'), os.path.join(FOLDER, f'{day}.html'))
    days = _days()
    days[day] = {'label': (newsday or {}).get('label'), 'emoji': (newsday or {}).get('emoji'),
                 'story': (newsday or {}).get('story'), 'stories': (newsday or {}).get('stories')}
    write_json(DAYS, days, indent=1)


def publish():
    """Write every saved edition into the build at /YYYY/MM/DD/ and the list of days at archive.html."""
    days = _days()
    published = []
    for day in sorted(days, reverse=True):
        source = os.path.join(FOLDER, f'{day}.html')
        if day == _today() or not os.path.exists(source):
            continue  # today's edition isn't finished; the front page is today's
        folder = os.path.join(Config.build, *day.split('-'))
        os.makedirs(folder, exist_ok=True)
        with open(source) as f, open(os.path.join(folder, 'index.html'), 'w') as out:
            out.write(edition(f.read(), day))
        published.append({'day': day, 'path': '/' + day.replace('-', '/') + '/',
                          'when': dt.strptime(day, '%Y-%m-%d').strftime('%a %b %-d, %Y'), **days[day]})
    TemplateHandler('archive.html').write({'title': 'Archive', 'days': published})
    logger.info("Archive: %d past days published", len(published))
