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
STORY_THRESHOLD = 0.7  # as the front page's stories


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
    headlines whose embeddings are STORY_THRESHOLD alike), each led by its most central headline; and the headlines
    in no story of two outlets or more."""
    from app.analysis.clustering import form_clusters, prepare_embedding_cosine
    if len(headlines) < 2:
        return [], list(headlines)
    sim = prepare_embedding_cosine([h['title'] for h in headlines])
    clusters = form_clusters(sim.copy(), 2, STORY_THRESHOLD)
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
        })
        self.template.write(self.context)
        logger.info("...%d cases in the news, %d other Court stories, %d topic cards, %d cases uncovered", len(cards),
                    len(stories), len(topics), len(uncovered))
