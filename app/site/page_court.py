"""The Supreme Court page (#144): a card per case in the news, like the front page's story cards (who's covering it and
from which side, the mood and wording of its headlines, the feelings they stir, the phrases quoted, and the left- and
right-leaning headlines side by side), cards for the other Court news by topic, and the term's cases nobody is
covering. From the last two weeks of headlines (app.analysis.scotus)."""
from collections import Counter
from datetime import datetime as dt

import pandas as pd

from app.analysis import scotus
from app.analysis.quotes import story_quotes
from app.analysis.stories import headline_sentiment
from app.site.common import TemplateHandler, chip_style, short_name
from app.site.page_edits import eastern
from app.site.page_headlines import LEAN_RANGE, MOOD_RANGE, meter, story_feelings, weather
from app.utils import Config, get_logger

logger = get_logger(__name__)
SHOWN = 6  # headlines shown on a card before "more"
TOPIC_CARDS = 9
MIN_CARD_OUTLETS = 2  # a case gets a card from two outlets; one is in the term's list with its count

# The docket strips (Oct 28 redo: "Cases in the news" was 30-odd cards, each with three sliders, a chip wall and
# tags like "ruling 6 · term preview 1 · other 1", unexplained). A case's row is colored by where it stands on the
# docket, from its dates (the Granted & Noted list has no decisions: those would be a fourth stage, "decided")
CASE_STAGES = {
    'case taken': {'emoji': '📥', 'ink': '#ffc400', 'about': 'taken, no argument date yet'},
    'to be argued': {'emoji': '🗓️', 'ink': '#00c2a8', 'about': 'its argument date is set'},
    'argued': {'emoji': '🎤', 'ink': '#8a5cff', 'about': 'argued, the ruling to come'},
}
# The other Court news, colored by what its headlines mostly report (the model's stage for each headline, in groups)
NEWS_KINDS = {
    'orders': {'name': 'rulings and orders', 'emoji': '🔨', 'ink': '#ff6b1a', 'stages': ('ruling', 'emergency order')},
    'justices': {'name': 'the justices', 'emoji': '🧑‍⚖️', 'ink': '#ff4fa3',
                 'stages': ('the justices', 'nomination or retirement')},
    'cases': {'name': 'cases and the term', 'emoji': '📜', 'ink': '#7a8a00',
              'stages': ('case taken', 'argument', 'term preview')},
    'other': {'name': 'other Court news', 'emoji': '⚖️', 'ink': '#ffffff', 'stages': ('other',)},
}
# What each headline stage means, for the cards (the old tags, said in words)
STAGE_WORDS = {'case taken': 'the Court taking the case', 'argument': 'the argument', 'ruling': 'a ruling',
               'emergency order': 'an emergency order', 'the justices': 'the justices themselves',
               'nomination or retirement': 'a nomination or retirement', 'term preview': 'a preview of the term',
               'other': 'something else'}


def case_stage(argued_on, today) -> str:
    """Where a case stands on the docket: taken, to be argued (a date set) or argued"""
    if argued_on is None:
        return 'case taken'
    return 'argued' if argued_on <= today else 'to be argued'


def news_kind(stages) -> str:
    """What a group of headlines mostly reports, by the model's stage for each: a NEWS_KINDS key (the first kind on a
    tie)"""
    count = Counter(next((k for k, v in NEWS_KINDS.items() if s in v['stages']), 'other') for s in stages)
    return max(NEWS_KINDS, key=lambda k: (count[k], -list(NEWS_KINDS).index(k))) if count else 'other'


def reported(stage_counts) -> str:
    """The headline stage tags in words: 'a ruling 6 · a preview of the term 1'"""
    return ' · '.join(f"{scotus.STAGE_EMOJI.get(s, '⚖️')} {STAGE_WORDS.get(s, s)} {n}" for s, n in stage_counts)


def lean_split(counts) -> float | None:
    """The share of a group's left- and right-leaning outlets that lean left, for the strip's two-tone bar"""
    left, right = counts.get('left', 0), counts.get('right', 0)
    return left / (left + right) if left + right else None


def sides_text(counts) -> str:
    parts = [f"{counts.get(s, 0)} {w}" for s, w in (('left', 'left-leaning'), ('center', 'center'),
                                                     ('right', 'right-leaning')) if counts.get(s)]
    if counts.get('unrated'):
        parts.append(f"{counts['unrated']} not rated")
    return ', '.join(parts) or 'no rated outlets'


def strip_rows(items: list[dict], axis) -> list[dict]:
    """Cases or stories as a ranked strip: the bar is how many outlets ran a headline on it, in two tones by lean
    (center and unrated outlets out of the split); the disc is the row's colored axis, axis(item) -> (ink, emoji,
    label). A row links to its block below (item['anchor']) or, without one, keeps its card open on a click"""
    from app.site import boards
    top = max((i['outlets'] for i in items), default=1)
    rows = []
    for i in items:
        ink, mark, label = axis(i)
        rows.append(boards.row(i['title'], f"#{i['anchor']}" if i.get('anchor') else None, i['outlets'], top,
                               f"{i['outlets']} outlet{'s' if i['outlets'] != 1 else ''}", ink=ink, mark=mark,
                               mark_label=label, split=lean_split(i['counts'])))
    return rows


def stage_axis(i):
    s = CASE_STAGES[i['case_stage']]
    return s['ink'], s['emoji'], i['case_stage']


def kind_axis(i):
    k = NEWS_KINDS[i['kind']]
    return k['ink'], k['emoji'], k['name']


def key_of(table: dict, shown: set) -> list[dict]:
    """A strip's color key, in the table's fixed order, of the colors it shows"""
    return [{'name': v.get('name', k), 'mark': v['emoji'], 'ink': v['ink'], 'about': v.get('about', '')}
            for k, v in table.items() if k in shown]


def court_date(text):
    """'10/5/26' -> a date, for sorting and 'Oct 5'."""
    return dt.strptime(text, '%m/%d/%y').date() if text else None


def one_per_outlet(rows: list[dict]) -> list[dict]:
    """Each outlet's latest headline (rows come newest first)."""
    seen = {}
    for r in rows:
        seen.setdefault(r['agency'], r)
    return list(seen.values())


def court_stories(headlines: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    """The other Court news grouped into stories the way the front page groups headlines (connected groups of
    headlines whose embeddings are as alike as the front page's stories need), each led by its most central headline; and the headlines
    in no story of two outlets or more."""
    from app.analysis.clustering import form_clusters, story_similarity
    if len(headlines) < 2:
        return [], list(headlines)
    sim, threshold, _ = story_similarity([h['title'] for h in headlines])
    clusters = form_clusters(sim.copy(), 2, threshold)
    stories, placed = [], set()
    for cluster in clusters:
        members = sorted(cluster)
        if len({headlines[i]['agency'] for i in members}) < 2:
            continue
        central = max(members, key=lambda i: sum(sim[i, j] for j in members if j != i))
        stories.append(sorted((headlines[i] for i in members), key=lambda h: (h is not headlines[central],
                                                                             -h['first'].timestamp())))
        placed.update(members)
    rest = [h for i, h in enumerate(headlines) if i not in placed]
    return sorted(stories, key=lambda hs: -len(one_per_outlet(hs))), rest


def analysis(rows: list[dict], baseline: float) -> dict:
    """What a card shows about a group of headlines: lean of the outlets covering it (against all Court coverage),
    mood, loaded wording, feelings, quoted phrases, and each side's most loaded headline."""
    outlets = one_per_outlet(rows)
    df = pd.DataFrame(outlets)
    rated = df[df['rated']]
    lean = meter(rated['bias'].mean() - baseline if not rated.empty else 0.0, LEAN_RANGE, 'L', 'R')
    mood = meter(float(headline_sentiment(df).mean()), MOOD_RANGE, '', '')
    mood.update(dict(zip(('emoji', 'word'), weather(mood['value']))))
    loaded = df['loaded_score'].dropna()
    sides = {}
    for side in ('left', 'right'):
        mine = [r for r in outlets if r['side'] == side]
        if mine:
            pick = max(mine, key=lambda r: (r['loaded_score'] or 0, r['first']))
            sides[side] = {**pick, 'style': chip_style(pick['agency'], pick['bias'])}
    return {
        'lean': lean, 'mood': mood, 'spice': round(float(loaded.mean()), 2) if not loaded.empty else None,
        'spice_position': round(100 * min(1.0, float(loaded.mean()))) if not loaded.empty else None,
        'feelings': story_feelings(df), 'quotes': story_quotes(outlets),
        'framing': sides if len(sides) == 2 else {},
        'chips': [{'agency': r['agency'], 'short': short_name(r['agency']), 'url': r['url'],
                   'style': chip_style(r['agency'], r['bias'])} for r in sorted(outlets, key=lambda r: r['bias'])],
        'counts': Counter(r['side'] for r in outlets),
    }


class CourtPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('court.html')
        self.context = {'title': 'Supreme Court'}

    def generate(self):
        logger.info("Generating Supreme Court page...")
        if not Config.debug:
            scotus.refresh_docket()  # at most a request to each source a week
        data = scotus.coverage()
        today = dt.now().date()
        everything = [r for c in data['covered'] for r in c['headlines']] + data['other']['headlines']
        rated = [r['bias'] for r in one_per_outlet(everything) if r['rated']]
        baseline = sum(rated) / len(rated) if rated else 0.0

        def rows(headlines):
            return [{**h, 'style': chip_style(h['agency'], h['bias']), 'when': eastern(h['first']),
                     'emoji': scotus.STAGE_EMOJI.get(h['stage'], '⚖️')} for h in headlines]

        def dates(case):
            argued = court_date(case.get('argued'))
            return {'argued_on': argued, 'argued_text': f"{argued:%b} {argued.day}" if argued else None,
                    'argued_past': bool(argued and argued <= today),
                    'docket_url': f"https://www.supremecourt.gov/docket/docketfiles/html/public/{case['docket']}.html"}

        cards = [{**c, **dates(c), **analysis(c['headlines'], baseline), 'rows': rows(c['headlines']),
                  'stage_list': sorted(c['stages'].items(), key=lambda kv: -kv[1])} for c in data['covered']
                 if c['outlets'] >= MIN_CARD_OUTLETS]
        # The other Court news: a card per story (titled by its most central headline), then the headlines in no
        # story, a card per topic (a headline counts under its first topic)
        grouped, rest = court_stories(data['other']['headlines'])
        names = scotus.story_glosses([[h['title'] for h in hs] for hs in grouped])
        stories = [{'lead': hs[0], 'name': name, 'rows': rows(hs), 'outlets': len(one_per_outlet(hs)),
                    'topics': list(dict.fromkeys(t for h in hs for t in h['topics']))[:3],
                    'stage_list': Counter(h['stage'] for h in hs).most_common(), **analysis(hs, baseline)}
                   for hs, name in zip(grouped, names)]
        by_topic = {}
        for h in rest:
            by_topic.setdefault(h['topics'][0] if h['topics'] else 'the Court', []).append(h)
        topics = [{'topic': t, 'rows': rows(hs), 'outlets': len(one_per_outlet(hs)), **analysis(hs, baseline)}
                  for t, hs in sorted(by_topic.items(), key=lambda kv: -len(one_per_outlet(kv[1])))[:TOPIC_CARDS]]
        # The strips: each case, story and topic's title, its block's anchor, its colored axis and its stage tags in words
        for c in cards:
            c.update(title=c['gloss'] or c['name'], anchor=f"case-{c['docket']}",
                     case_stage=case_stage(c['argued_on'], today), reported=reported(c['stage_list']))
        for n, t in enumerate(stories):
            t.update(title=t['name'] or t['lead']['title'], anchor=f'court-story-{n}',
                     kind=news_kind([s for s, k in t['stage_list'] for _ in range(k)]), reported=reported(t['stage_list']))
        for t in topics:
            stage_list = Counter(r['stage'] for r in t['rows']).most_common()
            t.update(title=t['topic'], kind=news_kind([r['stage'] for r in t['rows']]), reported=reported(stage_list))
        for i in cards + stories + topics:
            i['who'] = sides_text(i['counts'])
        from app.site import boards
        strips = {
            'cases': boards.board('court-cases', '⚖️', 'Cases in the news', '#8a5cff', 'the bar is how many outlets ran '
                                  'a headline on it, blue for the share of its left-leaning outlets and red for its '
                                  'right-leaning ones (center outlets aside)', strip_rows(cards, stage_axis)),
            'stories': boards.board('court-stories', '📰', 'Also at the Court', '#00c2a8', 'news not about one of '
                                    "the term's cases, grouped into stories; the bar is outlets, split by lean",
                                    strip_rows(stories, kind_axis)),
            'singles': boards.board('court-singles', '🗞️', 'Single headlines, by topic', '#ffc400', 'Court news no '
                                    'other outlet ran a headline like; the bar is outlets, split by lean',
                                    strip_rows(topics, kind_axis))}
        term_cases = sorted(({**c, **dates(c)} for c in data['cases']),
                            key=lambda c: (c['argued_on'] is None, c['argued_on'] or dt.max.date(), c['name']))
        uncovered = [c for c in term_cases if not c['headlines']]
        argued_soon = [c for c in cards + uncovered
                       if c['argued_on'] and 0 <= (c['argued_on'] - today).days <= 7]
        self.context.update({
            'term': data['term'], 'source': data['source'], 'window_days': data['window_days'], 'total': data['total'],
            'cards': cards, 'stories': stories, 'topics': topics, 'term_cases': term_cases,
            'n_cases': len(data['cases']),
            'argued_soon': sorted(argued_soon, key=lambda c: c['argued_on']), 'shown': SHOWN,
            'stage_emoji': scotus.STAGE_EMOJI, 'wiki': scotus.WIKI_PAGE, 'min_card': MIN_CARD_OUTLETS,
            'strips': strips, 'stage_key': key_of(CASE_STAGES, {c['case_stage'] for c in cards}),
            'kind_key': key_of(NEWS_KINDS, {t['kind'] for t in stories + topics}), 'stage_words': STAGE_WORDS,
            'case_stages': CASE_STAGES, 'news_kinds': NEWS_KINDS,
        })
        self.template.write(self.context)
        logger.info("...%d cases in the news, %d other Court stories, %d topic cards, %d cases uncovered", len(cards),
                    len(stories), len(topics), len(uncovered))
