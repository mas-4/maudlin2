"""Beyond the front pages: what the news-of-the-day shows, newsletters, streams and investigative outfits are
talking about, by subject (app/analysis/subjects.py), and a directory of every source we follow besides the outlets'
front pages, with what we do with each (shown on the site, or archived and transcribed for research only). The subjects are a
diverging strip, left-leaning shows against right-leaning (Oct 28, the site redo: they were 35 filter buttons)."""
from collections import Counter

import pandas as pd

from app import investigations, sidefeeds
from app.analysis import subjects
from app.site.common import TemplateHandler
from app.utils import get_logger

logger = get_logger(__name__)

KIND = {'podcast': ('🎙️', 'Podcasts'), 'newsletter': ('📨', 'Newsletters'), 'video': ('📺', 'Video channels'),
        'call-in': ('☎️', 'Call-in shows'), 'investigation': ('🕵️', 'Investigations'),
        'fact-check': ('🔎', 'Fact-checkers'), 'satire': ('🃏', 'Satire')}
GROUP_INK = {'left': '#3a86ff', 'right': '#ff4f6d', 'center': '#b8b8c8', 'crossover': '#8a5cff'}
LEAN = {'left': 'left-leaning', 'right': 'right-leaning', 'center': 'center', 'crossover': 'crossover'}
# What we do with each kind of source, in plain words
USE = {'investigation': 'shown on the stories it covers (🕵️)', 'fact-check': 'shown on stories and Rumors (🔎)',
       'satire': 'shown on the stories it jokes about (🃏)'}


SIDES = [('left', '🫏', 'left-leaning shows'), ('elsewhere', '⚖️', 'center and crossover shows, investigations'),
         ('right', '🐘', 'right-leaning shows')]


def subject_strip(items: list[dict]) -> list[dict]:
    """The subjects as a diverging strip (Oct 28, the site redo: they were 35 buttons): per subject the pieces from
    left-leaning shows out to the left, right-leaning out to the right, and the rest (center and crossover shows,
    investigations) across the middle, on one scale; the most pieces first"""
    by = {}
    for i in items:
        side = i.get('group') if i.get('group') in ('left', 'right') else 'elsewhere'
        for s in i['subjects']:
            by.setdefault(s, Counter())[side] += 1
    rows = sorted(by.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    reach = max((max(c['left'], c['right']) + c['elsewhere'] / 2 for _, c in rows), default=1) or 1
    out = []
    for s, c in rows:
        w = {k: 50 * c[k] / reach for k in ('left', 'right')}
        mid = 50 * c['elsewhere'] / reach / 2  # half of the middle on each side of the axis
        tip = '\n'.join(f"{emoji} {c[k]} from {words}" for k, emoji, words in SIDES if c[k])
        out.append({'key': s, 'emoji': subjects.EMOJI.get(s, '🏷️'), 'label': subjects.label(s), 'n': sum(c.values()),
                    'left': c['left'], 'right': c['right'], 'elsewhere': c['elsewhere'], 'tip': tip,
                    'w_left': round(w['left'], 1), 'w_right': round(w['right'], 1), 'w_mid': round(mid, 1)})
    return out


def use(src: dict) -> str:
    if src['kind'] in USE:
        return USE[src['kind']]
    shown = 'shown here and on its stories (🎙️)' if src['publish'] else 'archived for research, not shown'
    audio = src['kind'] in ('podcast', 'call-in')
    return shown + ('; transcribed' if audio else '')


class BeyondPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('beyond.html')

    def generate(self):
        logger.info("Generating beyond-the-front-pages page...")
        try:
            items = [{**i, 'kind_emoji': KIND.get(i['kind'], ('🎙️', ''))[0],
                      'color': GROUP_INK.get(i['group'], '#b8b8c8')}
                     for i in sidefeeds.recent(days=3, limit=300, per_source=6)]
        except Exception as e:  # noqa: BLE001 - e.g. no side_item table on a database that hasn't migrated
            logger.warning("Beyond: shows: %s", e)
            items = []
        items += [{**p, 'kind': 'investigation', 'kind_emoji': '🕵️'}
                  for p in investigations.recent(days=14, limit=60, per_source=8)]
        tags = subjects.tag(items)
        for item in items:
            item['subjects'] = tags.get(item['url'], [])
            item['date'] = pd.Timestamp(item['published']).tz_convert('US/Eastern').strftime('%b %-d')
        items.sort(key=lambda i: i['published'], reverse=True)
        directory = []
        for kind, (emoji, heading) in KIND.items():
            rows = [{'name': s['name'], 'lean': LEAN.get(s['group'], ''), 'color': GROUP_INK.get(s['group']),
                     'use': use(s)} for s in sidefeeds.SOURCES if s['kind'] == kind]
            if kind == 'investigation':
                rows = [{'name': s['name'], 'home': s['home'], 'lean': '', 'color': s['color'], 'use': USE[kind],
                         'about': s['about']} for s in investigations.SOURCES]
            if rows:
                directory.append({'kind': kind, 'emoji': emoji, 'heading': heading,
                                  'rows': sorted(rows, key=lambda r: r['name'].lower())})
        try:  # each show's own page, where the motif index has enough of its claims (page_show)
            from app.analysis import motif_web
            from app.site.page_motif import shared
            show_pages = {s: motif_web.show_slug(s) for s in shared()['web']['shows']}
        except Exception as e:  # noqa: BLE001 - extra
            logger.warning("Beyond: show pages: %s", e)
            show_pages = {}
        self.template.write({
            'show_pages': show_pages,
            'title': 'Beyond the front pages', 'items': items, 'directory': directory, 'kinds': KIND,
            'subject_counts': Counter(s for i in items for s in i['subjects']).most_common(),
            'subject_strip': subject_strip(items), 'sides': SIDES,
            'subject_emoji': subjects.EMOJI, 'subject_label': subjects.label,
            'kind_counts': Counter(i['kind'] for i in items).most_common(),
            'total_sources': sum(len(d['rows']) for d in directory),
        })
        logger.info("...%d recent pieces, %d sources", len(items), sum(len(d['rows']) for d in directory))
