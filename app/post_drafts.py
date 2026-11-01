"""Bluesky post drafts: a dry run before the account goes live (Nov 1, the person: "write up some of our bluesky
proposals so we are generating them and can monitor them before we go live", without the posting itself).

Each hourly run, after the build, drafts the posts the account would make from what the run already has, in a few of
the formats from the Oct 30 plan (maudlin-notes/bluesky-post-ideas-2026-10-30.md). Nothing here talks to Bluesky.
The drafts are kept in data/post_drafts.json for the checker's 📣 drafts page, where the person marks each one 👍 or
👎; after the dry run, the formats that earn their keep are the ones that go live.

The guardrails from the plan hold for drafts too, so what's judged here is what would go out:
- the public layer only: verified motifs (the motif pages' catalog), headlines and captions as published;
- no true or false verdicts, no forecasts, no replies or quotes aimed at people;
- a motif's shows "came up on", never "told by" (tellings carry no stance yet);
- both sides or neither: a post comparing leans or channels shows them all;
- 300 characters at most (Bluesky's limit, counted here as characters), the link apart (it becomes the post's card).

A draft is keyed by its format and subject, so the same headline test or motif seen again next hour updates its draft
instead of adding another; the person's mark stays with it. Drafts are kept for KEEP_DAYS."""
import os
import re
from collections import defaultdict
from datetime import datetime as dt, timedelta as td

import pytz

from app.utils import Config, get_logger
from app.utils.store import locked, read_json, write_json

logger = get_logger(__name__)

FILE = os.path.join(Config.data, 'post_drafts.json')
SITE = 'https://bignews.day'
LIMIT = 300  # Bluesky's post length
KEEP_DAYS = 14
EASTERN = pytz.timezone('US/Eastern')

# The formats, in the order the drafts page shows them: emoji, name, what it is (from the Oct 30 plan)
FORMATS = {
    'headline_test': ('🧪', 'Headline test caught', 'an outlet trying several headlines on one story, in the order seen'),
    'rewrite': ('✏️', 'Rewrite caught', 'a headline changed after publishing, before and after'),
    'minutes': ('⏱️', 'Minutes on screen', "the day's top stories by minutes on each channel"),
    'chyrons': ('📺', 'Three chyrons, one moment', 'what CNN, Fox News and MSNOW had on screen at one moment, near 8 pm ET'),
    'shape': ('🧶', 'Shape of the day', 'the story shape that came up most lately, with the shows it came up on'),
    'theme': ('🔁', 'Front-page theme', 'several of the top stories at once about one kind of thing, like shootings'),
    'both_sides': ('🤝', 'Both sides', 'a story shape that came up on left- and right-leaning shows alike'),
}

TV = {'CNNW': 'CNN', 'FOXNEWSW': 'Fox News', 'MSNOW': 'MSNOW'}  # the three US channels (BBC News is left out)
WORD = re.compile(r'[A-Za-z]{3,}')  # a caption with fewer than three words is a poll's margins or a clock
NEAR = 3  # minutes apart, at most, for three captions to count as one moment


def eastern(t: dt) -> dt:
    """A naive UTC time in Eastern time"""
    return pytz.UTC.localize(t).astimezone(EASTERN)


def clock(t: dt) -> str:
    e = eastern(t)
    return e.strftime('%-I:%M %p').lower().replace(':00 ', ' ') + ' ET'


def fits(head: str, lines: list[str], tail: str = '', more: str = '+{n} more') -> str:
    """The head, as many whole lines as fit under LIMIT, then "+N more" for the rest (never a line cut mid-way: a
    headline cut short reads as a different headline), and the tail"""
    text = head
    for i, line in enumerate(lines):
        left = len(lines) - i - 1
        note = '\n' + more.format(n=left) if left else ''
        if len(text) + 1 + len(line) + len(tail) + len(note) > LIMIT:
            text += '\n' + more.format(n=len(lines) - i)
            break
        text += '\n' + line
    return (text + tail)[:LIMIT]


def same_words(text: str) -> str:
    """A wording with curly quotes, dashes, case and spacing set aside: two wordings alike but for these are one"""
    text = text.translate(str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-'}))
    return ' '.join(re.sub(r'[^\w\s]', '', text.lower()).split())


def short(text: str, most: int) -> str:
    return text if len(text) <= most else text[:most - 1].rsplit(' ', 1)[0] + '…'


def draft(fmt: str, subject: str, text: str, link: str, about: str = '', when: dt | None = None) -> dict:
    return {'key': f'{fmt}:{subject}', 'format': fmt, 'text': text, 'link': link, 'about': about,
            'chars': len(text), 'event': (when or dt.now(pytz.UTC).replace(tzinfo=None)).isoformat(timespec='minutes')}


# --- the formats ---

def headline_tests(now: dt) -> list[dict]:
    """🧪 Tests with three or more wordings seen in the last day: the wordings in the order first seen"""
    from app.analysis import abtests
    out = []
    found = []
    for t in abtests.tests(days=1, now=now):
        wordings, seen = [], set()
        for v in t['variants']:  # the kept one first, then the longest up
            if same_words(v['text']) not in seen:
                seen.add(same_words(v['text']))
                wordings.append(v)
        if len(wordings) >= 3:
            found.append((t, wordings))
    found.sort(key=lambda x: -len(x[1]))
    out = []
    for t, wordings in found[:3]:
        head = f"🧪 Headline test caught: {t['agency']} tried {len(wordings)} headlines on one story."
        lines = [('🏆 ' if v['won'] else '• ') + v['text'] for v in wordings]
        tail = '\n(🏆 the one they kept)' if t['state'] == 'won' else ''
        out.append(draft('headline_test', t['url'], fits(head, lines, tail), f'{SITE}/edits.html',
                         about=t['url'], when=t['latest']))
    return out


def rewrites(now: dt) -> list[dict]:
    """✏️ The day's rewrites that changed the most words (typo fixes and live blogs are already left out)"""
    from app.analysis.edits import find_edits, overlap
    edits, _ = find_edits(days=1)
    if edits.empty:
        return []
    rows = edits.to_dict('records')
    rows.sort(key=lambda r: overlap(r['before'], r['after']))  # the least alike first
    out = []
    for r in rows[:2]:
        when = r.get('first_seen_after')
        when = when.to_pydatetime() if hasattr(when, 'to_pydatetime') else when
        head = f"✏️ Rewrite caught. {r['agency']} changed a headline after publishing:"
        text = fits(head, [f"Before: {r['before']}", f"After: {r['after']}"])
        out.append(draft('rewrite', r['url'] + '|' + r['after'], text, f'{SITE}/edits.html', about=r['url'], when=when))
    return out


def minutes_on_screen(now: dt) -> list[dict]:
    """⏱️ Yesterday (Eastern) on the three US channels: the stories with the most minutes, each channel's minutes"""
    from app.site import page_tv
    day = eastern(now).date() - td(days=1)
    start = EASTERN.localize(dt(day.year, day.month, day.day)).astimezone(pytz.UTC).replace(tzinfo=None)
    end = start + td(days=1)
    rows = {}
    for c in page_tv.matched(days=3):
        if not (start <= c['at'] < end) or not c.get('story') or c['channel'] not in TV:
            continue
        r = rows.setdefault(c['story'], {'label': c['label'], 'by': defaultdict(int), 'total': 0})
        r['by'][c['channel']] += c['seconds']
        r['total'] += c['seconds']
    top = sorted(rows.values(), key=lambda r: -r['total'])[:3]
    if not top:
        return []
    mins = lambda s: f'{round(s / 60)} min'  # noqa: E731
    lines = []
    for r in top:
        lines.append(f"• {short(r['label'], 60)}\n  " + ' · '.join(f"{name} {mins(r['by'][ch])}" for ch, name in TV.items()))
    head = f"⏱️ Minutes on screen, {day.strftime('%A')}:"
    return [draft('minutes', day.isoformat(), fits(head, lines, more='+{n} more on the On TV page'),
                  f'{SITE}/tv.html', when=end)]


def three_chyrons(now: dt) -> list[dict]:
    """📺 The latest evening that has passed: the moment closest to 8 pm Eastern (between 6 and 11) when each US
    channel had a cleaned headline caption up within NEAR minutes of the others. The Archive reads some channels
    sparsely (MSNOW, weekends), so an exact shared minute is rare; no such moment, no draft"""
    from app import chyrons
    local = eastern(now)
    day = local.date() if local.hour >= 23 else local.date() - td(days=1)  # an hour's slack for the Archive
    eight = EASTERN.localize(dt(day.year, day.month, day.day, 20)).astimezone(pytz.UTC).replace(tzinfo=None)
    start, end = eight - td(hours=2), eight + td(hours=3)
    clean = read_json(chyrons.CLEAN, {})
    up = defaultdict(dict)  # channel -> minute -> headline
    for utc_day in sorted({start.date().isoformat(), end.date().isoformat()}):
        for r in chyrons.rows(utc_day):
            if r['channel'] not in TV or not (start <= r['at'] < end):
                continue
            for line in chyrons.caption_lines(r['text']):
                found = clean.get(chyrons.line_key(r['channel'], line))
                if found and found.get('kind') == 'headline' and len(WORD.findall(found.get('text', ''))) >= 3:
                    up[r['channel']].setdefault(r['at'].replace(second=0), found['text'])
    minutes = sorted({m for ch in up.values() for m in ch}, key=lambda m: abs((m - eight).total_seconds()))
    for m in minutes:
        seen = {}
        for ch in TV:
            near = [x for x in up[ch] if abs((x - m).total_seconds()) <= NEAR * 60]
            if near:
                seen[ch] = up[ch][min(near, key=lambda x: abs((x - m).total_seconds()))]
        if len(seen) == len(TV):
            head = f"📺 {clock(m)}, {day.strftime('%A')}. Three channels, one moment:"
            lines = [f"{name}: {seen[ch]}" for ch, name in TV.items()]
            return [draft('chyrons', day.isoformat(), fits(head, lines), f'{SITE}/tv.html', when=m)]
    return []


# Kinds of story that pile up on a front page (Nov 1, the person: four of the top stories were shootings, "can we
# capture such a thing"): a pattern on the stories' titles, and how a post says it. Counted on the build's top
# stories (data/top_stories.json); each story once, under every kind it matches
THEMES = {
    'shootings': (r'\b(shoot\w*|shot|gunm[ae]n|gunfire|opened fire|gun violence)\b', '🚨', 'about shootings'),
    'storms': (r'\b(hurricane|tornado\w*|storms?|blizzard|flood\w*|typhoon|cyclone)\b', '🌪️', 'about storms and floods'),
    'fires': (r'\b(wildfires?|blazes?|fire)\b', '🔥', 'about fires'),  # not "fires": a boss fires someone
    'crashes': (r'\b(crash\w*|derail\w*|collision|plane goes down)\b', '💥', 'about crashes'),
    'courts': (r'\b(judges?|courts?|rul(es|ing)|lawsuits?|sues?|sued|jury|verdict|indict\w*|charged|convicted|sentenced)\b',
               '⚖️', 'in the courts'),
    'protests': (r'\b(protest\w*|demonstrat\w*|riots?)\b', '📣', 'about protests'),
    'deaths': (r'\b(dies|died|death of|obituary|dead at \d+)\b', '🕯️', 'about someone dying'),
    'hospital': (r'\b(hospitali[sz]ed)\b', '🏥', 'about someone in the hospital'),
    'hacks': (r'\b(hack\w*|breach\w*|ransomware|cyberattack\w*)\b', '💻', 'about hacks'),
}
THEME_LEAST = 3  # of the top stories, for a theme


def front_page_themes(now: dt) -> list[dict]:
    """🔁 Three or more of the front page's top stories about one kind of thing. One draft a theme a day (Eastern),
    kept at the hour it was biggest"""
    top = read_json(os.path.join(Config.data, 'top_stories.json'), {}).get('stories') or []
    if not top:
        return []
    day = eastern(now).date().isoformat()
    out = []
    for theme, (pattern, emoji, about) in THEMES.items():
        hits = [s for s in top if re.search(pattern, s['title'], re.I)]
        if theme == 'fires':  # gunfire and sayings aren't fires
            hits = [s for s in hits if not re.search(r'open(ed|s)? fire|under fire|fire back|line of fire', s['title'], re.I)]
        if len(hits) < THEME_LEAST:
            continue
        head = f"{emoji} {len(hits)} of the top {len(top)} stories right now are {about}:"
        d = draft('theme', f'{day}|{theme}', fits(head, [f"• {h['title']}" for h in hits]), f'{SITE}/', when=now)
        d['peak'] = len(hits)
        out.append(d)
    return out


def motif_lines(e: dict) -> tuple[str, str]:
    leans = e['leans']
    shows = ', '.join(f"{leans[k]} {k}" for k in ('left', 'center', 'right') if leans[k])
    return shows, e['note'].strip()


def motifs(now: dt) -> list[dict]:
    """🧶 the shape that came up most lately, and 🤝 the most even one of those that came up on both sides"""
    from app.site import page_motif
    from app.site.common import motif_href
    try:
        told = page_motif.told_now(20)
    except Exception as e:  # noqa: BLE001 - the motif data may be missing outside a build
        logger.info("No motif drafts: %s", e)
        return []
    out = []
    day = eastern(now).date().isoformat()
    if told:
        e = told[0]
        shows, note = motif_lines(e)
        head = f"🧶 Shape of the day: {e['name']} {e['emoji']}"
        lines = [note] + ([f"Came up lately on {shows}-leaning shows."] if shows else [])
        out.append(draft('shape', f"{day}|{e['id']}", fits(head, lines), f"{SITE}/{motif_href(e['id'])}",
                         about=e['id']))
    both = [e for e in told if e['leans']['left'] and e['leans']['right']]
    if both:
        e = max(both, key=lambda e: (min(e['leans']['left'], e['leans']['right']), -told.index(e)))
        _, note = motif_lines(e)
        head = f"🤝 Both sides: {e['name']} {e['emoji']}"
        lines = [note, f"Came up lately on {e['leans']['left']} left-leaning and {e['leans']['right']} right-leaning "
                       "shows. A story shape isn't a side."]
        out.append(draft('both_sides', f"{day}|{e['id']}", fits(head, lines), f"{SITE}/{motif_href(e['id'])}",
                         about=e['id']))
    return out


MAKERS = [front_page_themes, headline_tests, rewrites, minutes_on_screen, three_chyrons, motifs]


def make(now: dt | None = None, file: str = FILE) -> int:
    """Draft this hour's posts and keep them with the earlier ones; returns how many are new"""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    fresh = []
    for maker in MAKERS:
        try:
            fresh += maker(now)
        except Exception as e:  # noqa: BLE001 - one format failing never stops the others, or the run
            logger.warning("Post drafts: %s failed: %s", maker.__name__, e)
    stamp = now.isoformat(timespec='minutes')
    with locked(file):
        store = read_json(file, {'drafts': []})
        by_key = {d['key']: d for d in store['drafts']}
        new = 0
        for d in fresh:
            old = by_key.get(d['key'])
            if old and d.get('peak', 0) < old.get('peak', 0):  # a theme smaller than it was: its biggest hour stays
                old['seen'] = stamp
            elif old:  # seen again: the newest text, the person's mark and first sighting kept
                old.update(d, seen=stamp)
            else:
                by_key[d['key']] = {**d, 'made': stamp, 'seen': stamp, 'mark': None}
                new += 1
        since = (now - td(days=KEEP_DAYS)).isoformat()
        store['drafts'] = sorted((d for d in by_key.values() if d['seen'] >= since), key=lambda d: d['made'],
                                 reverse=True)
        write_json(file, store)
    logger.info("Post drafts: %d this hour, %d new", len(fresh), new)
    return new


def state(file: str = FILE) -> dict:
    """For the checker's 📣 drafts page: the formats with their tallies, and the drafts, newest first"""
    drafts = read_json(file, {'drafts': []})['drafts']
    tally = {f: {'up': 0, 'down': 0, 'drafts': 0} for f in FORMATS}
    for d in drafts:
        t = tally.setdefault(d['format'], {'up': 0, 'down': 0, 'drafts': 0})
        t['drafts'] += 1
        if d.get('mark') in ('up', 'down'):
            t[d['mark']] += 1
    formats = [{'id': f, 'emoji': e, 'name': n, 'what': w, **tally[f]} for f, (e, n, w) in FORMATS.items()]
    return {'formats': formats, 'drafts': drafts, 'limit': LIMIT}


def mark(key: str, value: str | None, note: str | None = None, file: str = FILE) -> dict:
    """The person's 👍 or 👎 (or neither) on a draft, with an optional note on what's wrong with it"""
    if value not in ('up', 'down', None):
        raise ValueError('mark: up, down or null')
    with locked(file):
        store = read_json(file, {'drafts': []})
        for d in store['drafts']:
            if d['key'] == key:
                d['mark'] = value
                if note is not None:
                    d['note'] = re.sub(r'\s+', ' ', note).strip()[:500]
                break
        else:
            raise ValueError(f'no draft {key}')
        write_json(file, store)
    return state(file)
