"""Story pages: one page per saved story seen in the last week, with everything the trackers know about it in one
place: every outlet's headline, how coverage grew and faded, the saga it belongs to, the names it mentions, its minutes
on TV, the radio newscasts that carried it, and the folklore told around it. The front page's cards link here."""
import glob
import json
import os
import re
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
                    'spots': spots[sid], 'total': page_tv.minutes(sum(by.values())),
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


WORDS = re.compile(r"[a-z0-9']+")
SAME_LABEL = 0.5  # a report's story label this alike (shared words) to a saved story's is that story under older words


def reports_by_day(days: int = DAYS) -> list[dict]:
    """The last narrative report of each of the last `days` days, newest first (a day's earlier reports cover the same
    posts)"""
    from app.site.page_folklore import FOLDER
    from app.utils.store import read_json
    last = {}
    for path in sorted(glob.glob(os.path.join(FOLDER, 'report-*.json'))):
        last[os.path.basename(path)[len('report-'):][:10]] = path
    since = (datetime.now() - td(days=days)).strftime('%Y-%m-%d')
    return [dict(read_json(path, {}), file=os.path.basename(path))
            for day, path in sorted(last.items(), reverse=True) if day >= since]


def story_of(link: dict, stories: list[dict], at: datetime | None) -> int | None:
    """The saved story a report's story link means. Links carry the story's id since Oct 6; before, its label then,
    which may have been reworded since: the same label, or else the story around then whose label shares the most
    words with it (at least SAME_LABEL of them)"""
    ids = {st['id'] for st in stories}
    if link.get('id') in ids:
        return link['id']
    label = link.get('label') or ''
    same = [st for st in stories if st['label'] == label]
    if same:
        return max(same, key=lambda st: st['last'])['id']
    words = set(WORDS.findall(label.lower()))
    best, score = None, SAME_LABEL
    for st in stories:
        if at and not (st['first'] - td(days=1) <= at <= st['last'] + td(days=2)):
            continue
        theirs = set(WORDS.findall((st['label'] or '').lower()))
        overlap = len(words & theirs) / max(1, len(words | theirs))
        if overlap >= score:
            best, score = st['id'], overlap
    return best


def folklore_by_story(stories: list[dict]) -> dict:
    """story id -> the narratives people retold about it over the last week, newest day first: each day's report (not
    only the latest), each narrative with the motifs it's filed under, the earlier days it was told (narrative
    threads) and the focus group episodes where voters voiced it. A narrative told on several days shows once, on its
    latest day."""
    from app.analysis import focus_group, motif_index, narrative_threads
    from app.site.page_folklore import motif_cards, told_before
    index, threads = motif_index.load(), narrative_threads.load()
    episodes = focus_group.load()
    out, seen = defaultdict(list), defaultdict(set)
    for report in reports_by_day():
        day = EASTERN.localize(datetime.fromisoformat(report['made'])).astimezone(pytz.UTC).replace(tzinfo=None) \
            if report.get('made') else None
        for g in report.get('found', []):
            label, link = g.get('label') or {}, g.get('story') or {}
            if not (label.get('retold') and link.get('label')):
                continue
            sid = story_of(link, stories, day)
            claim = motif_index.corrected(label.get('narrative', ''), index)
            if sid is None or not claim:
                continue
            before = told_before(threads, report.get('file', ''), claim, index)
            same = {motif_index.key(claim)}
            if same & seen[sid]:
                continue
            seen[sid] |= same | {motif_index.key(b['claim']) for b in before}
            voters = []
            for v in g.get('voters') or []:  # where voters said it: the episode only (we never quote them)
                url = next((u for u, ep in episodes.items() if ep.get('title') == v.get('episode')), None)
                voters.append({'title': v.get('episode', ''), 'url': url, 'date': v.get('date', '')})
            out[sid].append({'claim': claim, 'people': g['authors'], 'relation': link.get('relation', ''), 'day': day,
                             'when': pytz.UTC.localize(day).astimezone(EASTERN).strftime('%b %-d') if day else '',
                             'motifs': motif_cards(index, claim), 'before': before, 'voters': voters})
    return dict(out)


VOTER_CLAIMS = 6


def voters_by_motif(folklore: list[dict], index: dict | None = None) -> list[dict]:
    """What voters in The Focus Group's episodes told that's filed under the same verified motifs as the story's
    retellings (in our words, as on the motifs page): the same shape, told by ordinary voters, often months before"""
    from app.analysis import focus_group, motif_index
    index = index or motif_index.load()
    episodes = focus_group.load()
    out, have = [], set()
    for f in folklore:
        for m in f['motifs']:
            entry = index['entries'].get(m['id'])
            if not entry:
                continue
            for c in motif_index.public_claims(entry):
                if c.get('source') != 'Focus Group' or c['claim'] in have:
                    continue
                have.add(c['claim'])
                ep = episodes.get(c.get('ref', ''), {})
                out.append({'claim': motif_index.corrected(c['claim'], index), 'motif': m, 'url': c.get('ref', ''),
                            'episode': ep.get('title', 'The Focus Group'), 'date': c.get('date', '')})
    return sorted(out, key=lambda v: v['date'], reverse=True)[:VOTER_CLAIMS]


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
        events.append({'at': min((f['day'] for f in folklore if f['day']), default=None), 'stage': 'retelling', 'emoji': '🧶',
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


def stickers(st: dict, outlets: list[dict], lean_counts: dict, tv: dict | None, radio: list[dict],
             folklore: list[dict], factchecks: list, snapshots: list[dict]) -> list[dict]:
    """The story's numbers as stickers across the top of its page, in the order it traveled: a big number or word,
    what it counts, an emoji and a color from the front page's palette. Stages with nothing to count are left off."""
    from app.site.page_sagas import lasted
    out = [{'emoji': '📰', 'big': len(outlets), 'small': 'outlet' + ('' if len(outlets) == 1 else 's') + ' carried it',
            'color': '#00c2a8'}]
    if any(lean_counts[k] for k in ('left', 'center', 'right')):
        out.append({'emoji': '⚖️', 'big': f"🫏{lean_counts['left']} · {lean_counts['center']} · {lean_counts['right']}🐘",
                    'small': 'left · center · right', 'color': '#3a86ff'})
    out.append({'emoji': '⏱️', 'big': lasted(st['first'], st['last']), 'small': 'on the front pages', 'color': '#ffc400'})
    if snapshots:
        peak = max(s['outlets'] for s in snapshots)
        out.append({'emoji': '📈', 'big': peak, 'small': 'front pages at once, at its peak', 'color': '#ff6b1a'})
    if tv and tv.get('total'):
        out.append({'emoji': '📺', 'big': tv['total'], 'small': 'of TV captions', 'color': '#cc0000'})
    if radio:
        out.append({'emoji': '📻', 'big': len(radio), 'small': 'radio newscast' + ('' if len(radio) == 1 else 's'),
                    'color': '#e8463c'})
    people = sum(f['people'] for f in folklore)
    if people:
        out.append({'emoji': '🧶', 'big': people, 'small': 'people retold it online', 'color': '#8a5cff'})
    if factchecks:
        out.append({'emoji': '🔎', 'big': len(factchecks), 'small': 'fact-check' + ('' if len(factchecks) == 1 else 's'),
                    'color': '#f5b700'})
    if st.get('saga'):
        parts = [p['id'] for p in st['saga']['parts']]
        if st['id'] in parts:
            out.append({'emoji': '🧵', 'big': f"{parts.index(st['id']) + 1} of {len(parts)}", 'small': 'parts of a saga',
                        'color': '#ff4fa3'})
    return out


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
        tv, radio, folk = tv_by_story(), radio_by_story(), folklore_by_story(stories)
        try:  # fact-checks that came after a story left the front page, or of one that never made a card
            from app.analysis import factchecks
            checks = factchecks.for_story_pages({st['id']: st['label'] for st in stories if st['label']})
        except Exception as e:  # noqa: extra; the pages stand without them
            logger.warning("Story pages: fact-checks: %s", e)
            checks = {}
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
            lean_counts = {'left': sum(b < 0 for b in rated), 'center': sum(b == 0 for b in rated),
                           'right': sum(b > 0 for b in rated), 'unrated': len(outlets) - len(rated)}
            ex = dict(extras.get(str(st['id']), {}))
            # The checks found while it was on a card, and since: newest first, each once
            both = {p['url']: p for p in (checks.get(st['id']) or []) + (ex.get('factchecks') or [])}
            ex['factchecks'] = sorted(both.values(), key=lambda p: p.get('published', ''), reverse=True)[:6]
            told = folk.get(st['id'], [])
            self.template.write({
                'title': st['label'] or 'A story', 'story': st, 'outlets': outlets,
                'lean_counts': lean_counts,
                'stickers': stickers(st, outlets, lean_counts, tv.get(st['id']), radio.get(st['id'], []),
                                     told, ex.get('factchecks') or [], st['snapshots']),
                'since': eastern(st['first']), 'until': eastern(st['last']), 'spark': sparkline(st['snapshots']),
                'by_lean': story_charts.by_lean(st, outlets),
                'timeline': story_charts.timeline(st, outlets, (tv.get(st['id']) or {}).get('spots', []),
                                                  radio.get(st['id'], []),
                                                  min((f['day'] for f in told if f['day']), default=None),
                                                  page_tv.CHANNEL_INK),
                'names': list(dict.fromkeys(entities.canonical(n, aliases) for n in names.get(f"s{st['id']}", []))),
                'tv': tv.get(st['id']), 'radio': radio.get(st['id'], [])[:12], 'folklore': told,
                'voters': voters_by_motif(told), 'extras': ex, 'rewordings': rewordings(st['headlines']),
                'wire': wire_copied(st['headlines']),
                'flow': flow(st, outlets, tv.get(st['id']), radio.get(st['id'], []), told),
            }, os.path.join(Config.build, page_name(st['id'])))
        logger.info("...%d story pages", len(stories))
