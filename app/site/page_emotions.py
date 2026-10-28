"""The emotions page: what feelings the news is stirring, overall, by side and by outlet.

Oct 28 (the site redo): the outlets' ~150 x 8 heatmap of purple percentages became paired boards (Most fearful | Most
hopeful, Angriest | Calmest...) colored by lean, each outlet's eight feelings in its hover card; "By side" became three
stacked bars. The full numbers stay in a folded table."""
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz

from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI, NEWS_THRESHOLD, emotion_weights
from app.models import Session, Headline, Article, Agency, Topic
from app.site import boards as strips
from app.site.common import TemplateHandler, chip_style, j2env
from app.site.data import DataHandler
from app.site.favicons import slug
from app.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 7
MIN_OUTLET_HEADLINES = 30
MIN_TOPIC_HEADLINES = 20
EMOTION_COLUMNS = [e for e in EMOTIONS if e != 'neutral'] + ['neutral']
SIDES = [('Left-leaning', lambda b: b < 0), ('Center', lambda b: b == 0), ('Right-leaning', lambda b: b > 0)]
SIDE_EMOJI = {'Left-leaning': '🫏', 'Center': '⚖️', 'Right-leaning': '🐘'}
# Each feeling's tint, the tiles' own (100-emotion-tiles.css), for the stacked bars and the hover cards' bars
TINT = {'fear': '#e0d4ff', 'anger': '#ffc2c2', 'sadness': '#c9e2ff', 'disgust': '#d6f5c4', 'surprise': '#fff1b3',
        'joy': '#ffe066', 'hope': '#c8f7e6', 'neutral': '#f4f4f4'}
# The outlet boards, in pairs that answer each other: a feeling, the board's title and its banner's color. Disgust
# and surprise don't answer each other; they're the two left over
PAIRS = [('fear', 'Most fearful', '#8a5cff'), ('hope', 'Most hopeful', '#00c2a8'),
         ('anger', 'Angriest', '#ff6b1a'), ('neutral', 'Calmest', '#c8c8d0'),
         ('sadness', 'Saddest', '#8a8f98'), ('joy', 'Most joyful', '#ffc400'),
         ('disgust', 'Most stomach-turning', '#7a8a00'), ('surprise', 'Most jaw-dropping', '#ff4fa3')]
PER_BOARD = 10
LEAN_OF_BIAS = {-2: 'left', -1: 'lean left', 0: 'center', 1: 'lean right', 2: 'right'}
LEAN_WORDS = {'left': 'left', 'lean left': 'leans left', 'center': 'center', 'lean right': 'leans right',
              'right': 'right', 'unrated': 'lean not rated'}


def load(days: int = WINDOW_DAYS) -> pd.DataFrame:
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    with Session() as s:
        rows = s.query(Headline.emotion_ranks, Agency.name, Agency._bias, Agency.lean_rated, Topic.name).join(  # noqa prot attr
            Headline.article).join(Article.agency).join(Article.topic, isouter=True).filter(
            Headline.first_accessed > since, Headline.emotion_ranks.isnot(None), Headline.news_score >= NEWS_THRESHOLD
        ).all()
    df = pd.DataFrame(rows, columns=['ranks', 'agency', 'bias', 'rated', 'topic'])
    # Each headline's vote, split ranked-choice style across the feelings it names (3:2:1, normalized)
    weights = pd.DataFrame([emotion_weights(r) for r in df['ranks']], index=df.index).reindex(
        columns=EMOTION_COLUMNS, fill_value=0).fillna(0)
    return df.join(weights)


def shares(df: pd.DataFrame, by: str, minimum: int) -> list[dict]:
    """One row per group with each emotion's share of the feeling in its headlines (the average of their split
    votes), the dominant feeling first."""
    sizes = df.groupby(by).size()
    table = df.groupby(by)[EMOTION_COLUMNS].mean()[sizes >= minimum]
    rows = []
    for name, row in table.iterrows():
        felt = row.drop('neutral')
        rows.append({'name': name, 'headlines': int(sizes[name]),
                     'shares': {e: round(float(row[e]), 3) for e in EMOTION_COLUMNS},
                     'dominant': felt.idxmax(), 'dominant_share': float(felt.max())})
    return sorted(rows, key=lambda r: (EMOTION_COLUMNS.index(r['dominant']), -r['dominant_share']))


def outlet_lean(name: str, bias: int, rated: bool = True) -> tuple[str, str]:
    """An outlet's place on the lean colors (boards.LEAN_INK) and the words for it: its rating, our estimate where it
    has none (said so), or unrated"""
    estimate = j2env.globals['lean_estimates'].get(name)
    if estimate is not None:
        lean = LEAN_OF_BIAS[max(-2, min(2, int(estimate)))]
        return lean, f'{LEAN_WORDS[lean]} (our estimate, not a rating)'
    if name in j2env.globals['unrated'] or not rated:
        return 'unrated', LEAN_WORDS['unrated']
    lean = LEAN_OF_BIAS[max(-2, min(2, int(bias)))]
    return lean, LEAN_WORDS[lean]


def lean_key(rows: list[dict]) -> list[dict]:
    """The lean colors' key: the leans the rows hold, left to right"""
    held = {r['lean'] for r in rows}
    return [{'name': LEAN_WORDS[k].capitalize(), 'mark': strips.LEAN_EMOJI[k], 'ink': strips.LEAN_INK[k]}
            for k in ('left', 'lean left', 'center', 'lean right', 'right', 'unrated') if k in held]


def outlet_boards(outlets: list[dict]) -> list[dict]:
    """For each feeling, the outlets whose news headlines stir it most, by its share of their feeling; rows colored
    by lean, each outlet's eight feelings in its hover card"""
    out = []
    for feeling, title, stage in PAIRS:
        ranked = sorted(outlets, key=lambda o: (-o['shares'][feeling], o['name']))[:PER_BOARD]
        top = ranked[0]['shares'][feeling] if ranked else 1
        rows = []
        for o in ranked:
            r = strips.row(o['name'], o['href'], o['shares'][feeling], top, f"{o['shares'][feeling]:.0%}",
                           tip=o['tip'], ink=strips.LEAN_INK[o['lean']], mark=strips.LEAN_EMOJI[o['lean']],
                           mark_label=o['lean_words'])
            r['lean'] = o['lean']
            rows.append(r)
        sub = (f"the bar is the share of its headlines' feeling that's {feeling}" if feeling != 'neutral' else
               "the bar is the share of its headlines' vote that went to no strong feeling at all (🥛)")
        out.append(strips.board(f'feel-{feeling}', EMOTION_EMOJI[feeling], title, stage, sub, rows))
    return out


def side_bars(sides: list[dict]) -> list[dict]:
    """By side: a stacked bar each for left-leaning, center and right-leaning outlets, the feelings in a fixed order
    so the three compare"""
    return [{'name': s['name'], 'emoji': SIDE_EMOJI[s['name']], 'headlines': s['headlines'],
             'segments': [{'emotion': e, 'emoji': EMOTION_EMOJI[e], 'share': s['shares'][e], 'tint': TINT[e],
                           'pct': round(100 * s['shares'][e])} for e in EMOTION_COLUMNS]}
            for s in sides if s['name'] in SIDE_EMOJI]


class EmotionsPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('emotions.html')
        self.context = {'title': 'Emotions', 'window_days': WINDOW_DAYS, 'emotions': EMOTION_COLUMNS,
                        'emoji': EMOTION_EMOJI, 'min_outlet_headlines': MIN_OUTLET_HEADLINES, 'tints': TINT}

    def generate(self):
        logger.info("Generating emotions page...")
        df = load()
        if df.empty:
            self.context['available'] = False
            self.template.write(self.context)
            return
        overall = df[EMOTION_COLUMNS].mean()
        df['side'] = df['bias'].map(lambda b: next(name for name, test in SIDES if test(b)))
        df.loc[~df['rated'].astype(bool), 'side'] = 'Not rated'
        first = df.drop_duplicates('agency').set_index('agency')
        outlets = shares(df, 'agency', MIN_OUTLET_HEADLINES)
        for row in outlets:
            b = int(first['bias'][row['name']])
            row['style'] = chip_style(row['name'], b)
            row['lean'], row['lean_words'] = outlet_lean(row['name'], b, bool(first['rated'][row['name']]))
            row['href'] = f"outlet-{slug(row['name'])}.html"
            row['tip'] = '\n'.join([f"{row['lean_words'].capitalize()} · {row['headlines']:,} news headlines"] + [
                f"{EMOTION_EMOJI[e]} {e} {row['shares'][e]:.0%}"
                for e in sorted(EMOTION_COLUMNS, key=lambda e: -row['shares'][e])])
        outlets.sort(key=lambda r: r['name'].lower())  # the folded table, by name; the boards rank them
        sides = sorted(shares(df, 'side', 1),
                       key=lambda r: [n for n, _ in SIDES + [('Not rated', None)]].index(r['name']))
        boards = outlet_boards(outlets)
        self.context.update({
            'available': True,
            'total': len(df),
            'overall': sorted(({'emotion': e, 'share': float(overall[e]), 'count': int((df[e] > 0).sum())}
                               for e in EMOTION_COLUMNS), key=lambda o: -o['share']),
            'sides': sides,
            'side_bars': side_bars(sides),
            'unrated_side': next((s for s in sides if s['name'] == 'Not rated'), None),
            'outlets': outlets,
            'boards': boards,
            'lean_key': lean_key([r for b in boards for r in b['rows']]),
            # each outlet's hover card: its lean and its eight feelings, drawn by the page's script
            'cards': {o['name']: {'lean': o['lean_words'], 'mark': strips.LEAN_EMOJI[o['lean']],
                                  'ink': strips.LEAN_INK[o['lean']], 'n': o['headlines'],
                                  'shares': [[e, round(100 * o['shares'][e], 1)] for e in EMOTION_COLUMNS]}
                      for o in outlets},
            'max_share': max(max(r['shares'][e] for e in EMOTION_COLUMNS if e != 'neutral')
                             for r in outlets) if outlets else 1,
        })
        self.template.write(self.context)
        logger.info("...%d headlines, %d outlets", len(df), len(outlets))
