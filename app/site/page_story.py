"""Story pages: one page per saved story seen in the last week, with everything the trackers know about it in one
place: every outlet's headline, how coverage grew and faded, the saga it belongs to, the names it mentions, its minutes
on TV, the radio newscasts that carried it, and the folklore told around it. The front page's cards link here."""
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta as td

import pytz

from app import chyrons
from app.analysis import entities, running_order
from app.site import page_tv, story_charts
from app.site.common import TemplateHandler, chip_style, outlet_icon, short_name
from app.site.page_sagas import EASTERN, eastern
from app.utils import Config, get_logger

logger = get_logger(__name__)
DAYS = 7  # stories seen this recently get a page
LEAN_WORD = {-2: 'left', -1: 'leans left', 0: 'center', 1: 'leans right', 2: 'right'}


def page_name(story_id: int) -> str:
    return f'story-{story_id}.html'


def recent_stories(days: int = DAYS) -> list[dict]:
    """Saved stories seen in the last `days`, with their headlines, outlets and snapshots"""
    from app.models import Session, Story, StoryHeadline, StorySnapshot, Headline, Article, Agency, Saga
    since = datetime.utcnow() - td(days=days)
    with Session() as s:
        stories = {i: {'id': i, 'label': label or '', 'first': first, 'last': last, 'saga': saga, 'headlines': [],
                       'snapshots': []}
                   for i, label, first, last, saga in s.query(Story.id, Story.label, Story.first_seen, Story.last_seen,
                                                               Story.saga_id).filter(Story.last_seen >= since)}
        if not stories:
            return []
        for sid, title, url, agency, bias, rated, first, last in s.query(
                StoryHeadline.story_id, Headline.title, Article.url, Agency.name, Agency._bias, Agency.lean_rated,
                Headline.first_accessed, StoryHeadline.last_seen).join(Headline, Headline.id == StoryHeadline.headline_id) \
                .join(Article, Article.id == Headline.article_id).join(Agency, Agency.id == Article.agency_id) \
                .filter(StoryHeadline.story_id.in_(list(stories))):
            stories[sid]['headlines'].append({'title': (title or '').strip(), 'url': url, 'outlet': agency,
                                              'bias': bias if rated else None, 'first': first, 'last': last})
        for sid, at, outlets, lean, mood in s.query(StorySnapshot.story_id, StorySnapshot.at, StorySnapshot.outlets,
                                                    StorySnapshot.lean, StorySnapshot.mood) \
                .filter(StorySnapshot.story_id.in_(list(stories))).order_by(StorySnapshot.at):
            stories[sid]['snapshots'].append({'at': at, 'outlets': outlets, 'lean': lean, 'mood': mood})
        sagas = {}
        saga_ids = {st['saga'] for st in stories.values() if st['saga']}
        if saga_ids:
            names = dict(s.query(Saga.id, Saga.name).filter(Saga.id.in_(list(saga_ids))))
            for i, label, first, saga in s.query(Story.id, Story.label, Story.first_seen, Story.saga_id) \
                    .filter(Story.saga_id.in_(list(saga_ids))).order_by(Story.first_seen):
                sagas.setdefault(saga, {'id': saga, 'name': names.get(saga) or '', 'parts': []})['parts'].append(
                    {'id': i, 'label': label or '', 'when': eastern(first)})
    for st in stories.values():
        st['saga'] = sagas.get(st['saga'])
    return [st for st in stories.values() if st['headlines']]


def sparkline(snapshots: list[dict], width: int = 320, height: int = 48) -> dict | None:
    """Outlets covering the story at each run, as an SVG polyline's points, with the peak"""
    if len(snapshots) < 2:
        return None
    t0, t1 = snapshots[0]['at'], snapshots[-1]['at']
    span = max((t1 - t0).total_seconds(), 1)
    peak = max(s['outlets'] for s in snapshots) or 1
    points = ' '.join(f"{4 + (width - 8) * (s['at'] - t0).total_seconds() / span:.1f},"
                      f"{height - 4 - (height - 8) * s['outlets'] / peak:.1f}" for s in snapshots)
    return {'points': points, 'width': width, 'height': height, 'peak': peak, 'from': eastern(t0), 'to': eastern(t1)}


def tv_by_story() -> dict:
    """story id -> {'channels': [(name, ink, time)], 'captions': [the longest-running captions]}, over every day read"""
    seconds, captions = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    first, spots = {}, defaultdict(list)
    for path in glob.glob(os.path.join(chyrons.FOLDER, 'matched-*.json')):
        try:
            caps = json.load(open(path))
        except (OSError, ValueError):
            continue
        for c in caps:
            if c.get('story'):
                at = datetime.fromisoformat(c['at'])
                if c['story'] not in first or at < first[c['story']][0]:
                    first[c['story']] = (at, chyrons.CHANNELS[c['channel']])
                seconds[c['story']][c['channel']] += c['seconds']
                spots[c['story']].append({'at': at, 'seconds': c['seconds'], 'channel': c['channel'],
                                          'name': chyrons.CHANNELS[c['channel']], 'text': c['text']})
                captions[c['story']][(c['channel'], c['text'])] += c['seconds']
    out = {}
    for sid, by in seconds.items():
        most = max(by.values()) or 1
        out[sid] = {'channels': [{'name': chyrons.CHANNELS[ch], 'ink': page_tv.CHANNEL_INK[ch], 'time': page_tv.minutes(n),
                                  'share': round(100 * n / most)}
                                 for ch, n in sorted(by.items(), key=lambda kv: -kv[1])],
                    'spots': spots[sid],
                    'captions': [{'channel': chyrons.CHANNELS[ch], 'text': t, 'time': page_tv.minutes(n)}
                                 for (ch, t), n in sorted(captions[sid].items(), key=lambda kv: -kv[1])[:8]],
                    'first': first[sid]}
    return out


def radio_by_story() -> dict:
    """story id -> the newscasts that carried it: show, when (ET) and its place in the running order"""
    out = defaultdict(list)
    for cast in running_order.load().values():
        for n, item in enumerate(cast['items'], 1):
            if item.get('story'):
                when = pytz.UTC.localize(datetime.fromisoformat(cast['published'])).astimezone(EASTERN)
                out[item['story']].append({'show': cast['show'], 'when': when.strftime('%b %-d, %-I:%M %p'),
                                           'at': when, 'place': n, 'of': len(cast['items']), 'title': item['title']})
    return {sid: sorted(v, key=lambda x: x['at'], reverse=True) for sid, v in out.items()}


def folklore_by_label() -> dict:
    """story label -> the narratives in the latest report tied to it (people retelling it, in our words), each with
    the motifs it's filed under and the days it was told before (narrative threads)"""
    from app.analysis import motif_index, narrative_threads
    from app.site.page_folklore import latest_report, motif_cards, told_before
    report = latest_report() or {'found': []}
    index, threads = motif_index.load(), narrative_threads.load()
    # The report's time is the machine's local (Eastern) time; everything else here is UTC
    day = EASTERN.localize(datetime.fromisoformat(report['made'])).astimezone(pytz.UTC).replace(tzinfo=None) \
        if report.get('made') else None
    out = defaultdict(list)
    for g in report['found']:
        label, story = g.get('label') or {}, g.get('story') or {}
        if label.get('retold') and story.get('label'):
            claim = label.get('narrative', '')
            out[story['label']].append({'claim': motif_index.corrected(claim, index), 'people': g['authors'],
                                        'relation': story.get('relation', ''), 'day': day,
                                        'motifs': motif_cards(index, motif_index.corrected(claim, index)),
                                        'before': told_before(threads, report.get('file', ''), claim, index)})
    return out


def flow(st: dict, outlets: list[dict], tv: dict | None, radio: list[dict], folklore: list[dict]) -> list[dict]:
    """The story's first moments at each stage downstream, in time order (Eastern): its first front page, its peak,
    its first minute on TV and on the radio, and the day people were found retelling it"""
    events = []
    # A headline first seen before the story began joined it later (an older piece folded in): not its origin
    starts = [h for h in outlets if h['first'] and h['first'] >= st['first'] - td(hours=1)]
    if starts:
        h = min(starts, key=lambda h: h['first'])
        events.append({'at': h['first'], 'stage': 'origin', 'emoji': '📰', 'text': f"first on a front page: {h['outlet']}"})
    if st['snapshots']:
        peak = max(st['snapshots'], key=lambda s: s['outlets'])
        events.append({'at': peak['at'], 'stage': 'spread', 'emoji': '📈', 'text': f"peak: on {peak['outlets']} front pages"})
    if tv:
        events.append({'at': tv['first'][0], 'stage': 'broadcast', 'emoji': '📺', 'text': f"first on TV: {tv['first'][1]}"})
    if radio:
        r = min(radio, key=lambda r: r['at'])
        events.append({'at': r['at'].astimezone(pytz.UTC).replace(tzinfo=None), 'stage': 'broadcast', 'emoji': '📻',
                       'text': f"first on the radio: {r['show']}"})
    if folklore:
        events.append({'at': folklore[0]['day'], 'stage': 'retelling', 'emoji': '🧶',
                       'text': f"retold online by {sum(f['people'] for f in folklore)} people"})
    events = [e for e in events if e['at']]
    for e in sorted(events, key=lambda e: e['at']):
        e['when'] = eastern(e['at'])
    return sorted(events, key=lambda e: e['at'])


def wire_copied(headlines: list[dict]) -> dict:
    """The outlets that ran an AP or Reuters headline on the story nearly word for word (the wire-share test,
    app/analysis/wire.py): wire -> outlets"""
    import pandas as pd
    from app.analysis import wire
    df = pd.DataFrame([{'title': h['title'], 'agency': h['outlet']} for h in headlines if h['title']])
    if df.empty or not df['agency'].isin(wire.WIRES).any():
        return {}
    try:
        copies = wire.wire_copies(df)
    except Exception as e:  # noqa: extra; the page stands without it
        logger.warning("Story pages: wire copies: %s", e)
        return {}
    wires = ', '.join(sorted(set(df.loc[df['agency'].isin(wire.WIRES), 'agency'])))
    outlets = sorted(set(df.loc[copies, 'agency']))
    return {'wires': wires, 'outlets': outlets} if outlets else {}


def rewordings(headlines: list[dict]) -> list[dict]:
    """Outlets that ran more than one headline on the story (a reworded headline or a follow-up piece): the first and
    the latest"""
    by = defaultdict(list)
    for h in sorted(headlines, key=lambda h: h['first'] or datetime.min):
        if h['title'] and h['title'] not in [x['title'] for x in by[h['outlet']]]:
            by[h['outlet']].append(h)
    return [{'outlet': o, 'first': hs[0]['title'], 'latest': hs[-1]['title'], 'times': len(hs)}
            for o, hs in sorted(by.items()) if len(hs) > 1]


class StoryPages:
    def __init__(self, dh=None):
        self.template = TemplateHandler('story.html')

    def generate(self):
        logger.info("Generating story pages...")
        stories = recent_stories()
        tv, radio, folk = tv_by_story(), radio_by_story(), folklore_by_label()
        try:
            names = json.load(open(entities.CACHE))
        except (OSError, ValueError):
            names = {}
        aliases = entities.load_aliases()['aliases']
        from app.site.page_headlines import STORY_EXTRAS
        from app.utils.store import read_json
        extras = read_json(STORY_EXTRAS, {})
        for st in stories:
            by_outlet = {}
            for h in sorted(st['headlines'], key=lambda h: h['first'] or datetime.min):
                by_outlet.setdefault(h['outlet'], h)  # each outlet's first headline on it
            outlets = sorted(by_outlet.values(), key=lambda h: (h['bias'] is None, h['bias'] or 0, h['outlet']))
            for h in outlets:
                h.update(chip=chip_style(h['outlet'], h['bias'] or 0), icon=outlet_icon(h['outlet']),
                         short=short_name(h['outlet']), lean=LEAN_WORD.get(h['bias'], 'not rated'),
                         when=eastern(h['first']) if h['first'] else '')
            rated = [h['bias'] for h in outlets if h['bias'] is not None]
            self.template.write({
                'title': st['label'] or 'A story', 'story': st, 'outlets': outlets,
                'lean_counts': {'left': sum(b < 0 for b in rated), 'center': sum(b == 0 for b in rated),
                                'right': sum(b > 0 for b in rated), 'unrated': len(outlets) - len(rated)},
                'since': eastern(st['first']), 'until': eastern(st['last']), 'spark': sparkline(st['snapshots']),
                'by_lean': story_charts.by_lean(st, outlets),
                'timeline': story_charts.timeline(st, outlets, (tv.get(st['id']) or {}).get('spots', []),
                                                  radio.get(st['id'], []),
                                                  next((f['day'] for f in folk.get(st['label'], []) if f['day']), None),
                                                  page_tv.CHANNEL_INK),
                'names': list(dict.fromkeys(entities.canonical(n, aliases) for n in names.get(f"s{st['id']}", []))),
                'tv': tv.get(st['id']), 'radio': radio.get(st['id'], [])[:12], 'folklore': folk.get(st['label'], []),
                'extras': extras.get(str(st['id']), {}), 'rewordings': rewordings(st['headlines']),
                'wire': wire_copied(st['headlines']),
                'flow': flow(st, outlets, tv.get(st['id']), radio.get(st['id'], []), folk.get(st['label'], [])),
            }, os.path.join(Config.build, page_name(st['id'])))
        logger.info("...%d story pages", len(stories))
