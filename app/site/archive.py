"""Daily archive pages (#125): each production run saves the front page as that day's edition (data/archive, overwritten
through the day, so the day's last run is the one that stays) and every build publishes the editions at /YYYY/MM/DD/,
plus archive.html listing them. Links in an edition are made absolute so styles and icons still load from its folder.
Debug builds never save, so a preview's stale data can't become an edition."""
import os
import re
import shutil
from datetime import datetime as dt, timedelta as td

import pytz

from app.site.common import TemplateHandler
from app.utils import Config, Constants, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'archive')
DAYS = os.path.join(FOLDER, 'days.json')
RELATIVE = re.compile(r'''(\b(?:href|src)=["'])(?!https?:|#|/|mailto:|data:)([^"']+)''')
FOOTER = re.compile(r'<div class="site-footer">.*?</div>', re.S)


def _today() -> str:
    return dt.now(pytz.UTC).astimezone(Constants.TimeConstants.timezone).strftime('%Y-%m-%d')


def _days() -> dict:
    return read_json(DAYS, {})


def refooter(page: str) -> str:
    """A kept page with today's footer in place of its own. What a page reported stays as it was, but its footer's
    license notice must be the one in force: the blanket CC BY 4.0 of Oct 8-9 was narrowed on Oct 10. Episode guids
    kept as links are swapped for the episode's audio (they 404'd)."""
    from app.sidefeeds import fix_episode_links
    footer = TemplateHandler('footer.html').render({}).strip()
    return fix_episode_links(FOOTER.sub(lambda m: footer, page, count=1))


def edition(page: str, day: str) -> str:
    """The front page as a dated edition: absolute links, the icons' paths too, and a ribbon saying what it is."""
    page = RELATIVE.sub(lambda m: m.group(1) + '/' + m.group(2).removeprefix('./'), refooter(page))
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


WEEK = 7  # days the newsiness chart shows

# The calendar (Oct 28, the person: the list of days was "about 26 identical white boxes nearly all saying 📰 Just
# another news day"): a tile a day, shaded by how newsy the day was, one hue light to dark. The day's number is its
# average news-day score over its hourly runs (app/analysis/newsiness.py), so one spike doesn't make a day; its emoji
# is the front page's tiers (page_headlines.NEWS_DAY_TIERS) on that number, so the shade and the emoji agree. What the
# front page itself said at the end of the day stays in the tile's card.
SHADES = [(0.45, 5), (0.35, 4), (0.30, 3), (0.25, 2), (0.0, 1)]  # score from -> shade step, darkest first
SHADE_INK = '#ff6b1a'  # the peaks orange (docs/style-book.md), the banner's color
# The five steps, light to dark in one orange hue (the dataviz validator, ordinal: monotone, each step at least 0.06
# apart in lightness; the palest is close to white, so every tile has an ink outline and prints its number). The
# darkest takes white text
SHADE_HEX = {1: '#ffd8bd', 2: '#ffb07a', 3: '#ff8638', 4: '#d95a0b', 5: '#a33f00'}
TIER_EMOJI = {'big': '🚨', 'normal': '📰', 'slow': '🌴'}
BOARD_DAYS = 6  # days on each of Biggest days and Slowest days
WEEKDAY_INK, WEEKEND_INK = '#00c2a8', '#ffc400'  # the boards' colored axis: a weekday or a weekend day


def shade(score: float | None) -> int:
    """A day's shade step, 1 (palest) to 5, or 0 when no score was kept that day"""
    if score is None:
        return 0
    return next(step for start, step in SHADES if score >= start)


def tier(score: float) -> str:
    from app.site.page_headlines import NEWS_DAY_TIERS
    return next(k for k, threshold in NEWS_DAY_TIERS if score >= threshold)


def day_scores(points: list[dict]) -> dict[str, dict]:
    """Each Eastern day's news-day scores: {day: {score (the average over its hourly runs), hours, peak (the run where
    it was highest)}}"""
    from app.site import story_charts
    by = {}
    for p in points:
        by.setdefault(story_charts._local(dt.fromisoformat(p['at'])).strftime('%Y-%m-%d'), []).append(p)
    return {day: {'score': round(sum(p['score'] for p in ps) / len(ps), 3), 'hours': len(ps),
                  'peak': max(ps, key=lambda p: p['score'])} for day, ps in by.items()}


def _hour(at: str) -> str:
    from app.site import story_charts
    return story_charts._local(dt.fromisoformat(at)).strftime('%-I %p')


def day_tip(scored: dict | None, kept: dict | None, today: bool = False) -> str:
    """A tile's card: the day's number in words, its busiest hour, and what its front page closed the day saying"""
    lines = []
    if scored:
        s, peak = scored['score'], scored['peak']
        lines.append(f"{s:.2f}: in an average hour{' so far' if today else ''}, the biggest story was on about "
                     f"{round(10 * s)} in 10 front pages")
        lines.append(f"Busiest at {_hour(peak['at'])} ET: {peak['outlets']} of {peak['active']} outlets on "
                     f"“{peak['label']}”")
    else:
        lines.append('No score kept for this day')
    if kept and kept.get('label'):
        lines.append(' '.join(x for x in ('The front page closed the day:', kept.get('emoji'), kept['label']) if x))
    if kept and kept.get('story'):
        lines.append(f"Top story: {kept['story']}")
    if kept and kept.get('stories'):
        lines.append(f"{kept['stories']} stories on the front page")
    return '\n'.join(lines)


def calendar(published: list[dict], scores: dict[str, dict], today: str) -> list[dict]:
    """The calendar, newest month first: each month's weeks (Sunday first), each a list of 7 tiles or None. A tile is
    a day with a kept edition, or today (its live front page); days before the first edition are left out"""
    import calendar as cal
    from datetime import date
    editions = {d['day']: d for d in published}
    first = date.fromisoformat(min(set(editions) | {today}))
    last = date.fromisoformat(today)
    months, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        weeks = []
        for week in cal.Calendar(firstweekday=6).monthdatescalendar(y, m):
            row = []
            for d in week:
                iso = d.isoformat()
                if d.month != m or d < first or d > last:
                    row.append(None)
                    continue
                kept, scored, is_today = editions.get(iso), scores.get(iso), iso == today
                head = f"{d:%A, %B} {d.day}{' (today, so far)' if is_today else ''}"
                if not (kept or is_today):
                    row.append({'day': d.day, 'iso': iso, 'href': None, 'shade': 0, 'emoji': '🕳️', 'missing': True,
                                'head': head, 'tip': 'No front page kept that day', 'today': False})
                    continue
                score = scored['score'] if scored else None
                row.append({'day': d.day, 'iso': iso, 'missing': False, 'today': is_today,
                            'href': 'index.html' if is_today else kept['path'], 'shade': shade(score),
                            'hex': SHADE_HEX.get(shade(score), '#ffffff'),
                            'score': score, 'emoji': TIER_EMOJI[tier(score)] if score is not None else '❔',
                            'head': head, 'tip': day_tip(scored, kept, is_today)})
            if any(row):
                weeks.append(row)
        months.append({'name': date(y, m, 1).strftime('%B %Y'), 'weeks': weeks})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months[::-1]


def shade_key() -> list[dict]:
    """The calendar's key: each shade step, palest first, with its emoji and the scores it holds"""
    starts = sorted(start for start, _ in SHADES)
    out = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else None
        step = shade(start)
        words = f'under {end:.2f}' if not start else f'{start:.2f} and up' if end is None else \
            f'{start:.2f}–{end - 0.01:.2f}'
        out.append({'step': step, 'hex': SHADE_HEX[step], 'emoji': TIER_EMOJI[tier(start)], 'words': words})
    return out


def day_boards(published: list[dict], scores: dict[str, dict]) -> list[dict]:
    """Biggest days | Slowest days: the finished days with a score, by their average score, each colored by whether
    it was a weekday or a weekend day"""
    from app.site import boards
    days = [d for d in published if d['day'] in scores]
    top = max((scores[d['day']]['score'] for d in days), default=1)

    def rows(ds):
        out = []
        for d in ds:
            s, when = scores[d['day']], dt.strptime(d['day'], '%Y-%m-%d')
            weekend = when.weekday() >= 5
            out.append(boards.row(f"{when:%a %b} {when.day}: {d.get('story') or s['peak']['label']}", d['path'],
                                  s['score'], top, f"{TIER_EMOJI[tier(s['score'])]} {s['score']:.2f}",
                                  tip=f"{when:%A, %B} {when.day}: " + day_tip(s, d),
                                  ink=WEEKEND_INK if weekend else WEEKDAY_INK, mark='🛋️' if weekend else '💼',
                                  mark_label='a weekend day' if weekend else 'a weekday'))
        return out
    ranked = sorted(days, key=lambda d: (-scores[d['day']]['score'], d['day']))
    big = ranked[:BOARD_DAYS]
    slow = [d for d in ranked[::-1] if d not in big][:BOARD_DAYS]  # a day on one board only, while there are few
    return [boards.board('days-big', '🚨', 'Biggest days', '#ff6b1a', "the bar is the day's number: how much of the "
                         'news its biggest story took, in an average hour', rows(big),
                         empty='🦗 No finished day has a score yet.'),
            boards.board('days-slow', '🌴', 'Slowest days', '#00c2a8', 'the same number, the smallest first',
                         rows(slow), empty='🦗 Not enough days yet to have slow ones.')]


def newsiness_chart(published: set[str], points: list[dict] | None = None) -> dict:
    """The archive's chart of how newsy each hour was (app/analysis/newsiness.py), each spike linked to its story's own
    page, else to the story on that day's front page (today's live one, or the day's saved edition)"""
    try:
        from app.analysis import newsiness
        from app.site import page_story, story_charts
        since = (dt.utcnow() - td(days=WEEK)).isoformat()  # the past week, for now (the person, Oct 12)
        points = [p for p in (newsiness.series() if points is None else points) if p['at'] >= since]
        spikes = newsiness.spikes(points)
        with_page = {st['id'] for st in page_story.recent_stories()} | page_story.archived_ids()

        def link_of(p):
            if p['story'] in with_page:
                return page_story.page_name(p['story'])
            day = story_charts._local(dt.fromisoformat(p['at'])).strftime('%Y-%m-%d')
            if day == _today():
                return f"index.html#s-{p['story']}"
            return f"/{day.replace('-', '/')}/#s-{p['story']}" if day in published else None
        return {'newsiness': story_charts.newsiness(points, spikes, link_of),
                'spikes': [{**p, 'href': link_of(p), 'when': story_charts._local(dt.fromisoformat(p['at'])).strftime('%a %b %-d, %-I %p')}
                           for p in reversed(spikes)],
                'since': story_charts._local(dt.fromisoformat(points[0]['at'])).strftime('%B %-d') if points else ''}
    except Exception as e:  # noqa: BLE001 - the list of days stands without it
        logger.warning("Archive: newsiness chart failed (%s)", e)
        return {}


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
    try:
        from app.analysis import newsiness
        points = newsiness.series()
    except Exception as e:  # noqa: BLE001 - the calendar stands without its shades
        logger.warning("Archive: newsiness scores failed (%s)", e)
        points = []
    scores = day_scores(points)
    TemplateHandler('archive.html').write({
        'title': 'Archive', 'days': published, 'months': calendar(published, scores, _today()),
        'shade_key': shade_key(), 'shade_ink': SHADE_INK, 'day_boards': day_boards(published, scores),
        'day_key': [{'name': 'a weekday', 'mark': '💼', 'ink': WEEKDAY_INK},
                    {'name': 'a weekend day', 'mark': '🛋️', 'ink': WEEKEND_INK}],
        **newsiness_chart({d['day'] for d in published}, points)})
    logger.info("Archive: %d past days published", len(published))
