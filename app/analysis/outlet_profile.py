"""Outlet fingerprints and the outlet map (Oct 28): what each outlet does on its front page, read from its behaviour
and not from its rating. From the Oct 27-28 study (maudlin-notes, moonshot-2026-10-27/outlet-profiles), over the last
WINDOW_DAYS of headlines:

- **Coverage axes**: a correspondence analysis of outlets × stories (did the outlet run the story or not). The first
  axis runs from business, tech and world news to the political fight (the partisan outlets of both sides sit at the
  same end); the second from crime and immigration to Trump-critical stories. Each axis' sign is arbitrary in the
  maths, so it's oriented by the outlets' lean ratings (`orient`): the end where outlets rated far left or right
  gather is the high end of the first, and the end where left-rated outlets gather the high end of the second. The
  ratings only orient the axes; they don't place anyone.
- **Wire** (agenda and wording close to AP and Reuters) and **heat** (heated wording: loaded, combat verbs, anger) as
  percentiles among the profiled outlets. Both were stable traits between the two halves of October (0.92 and 0.95).
- **Type**: Ward clusters on about fifty behaviour features (coverage, agenda, timing, sidedness, headline form, heat,
  labels, churn), each group weighted alike. A type is named only when it holds most of a named type's anchor outlets
  and comes back in at least STABLE of bootstrap reclusterings (clusterwise Jaccard); otherwise the outlet shows its
  broad family, or nothing.
- **Behaves most like**: the outlet's NEIGHBOURS nearest outlets in that same feature space.
- **Its beat** (`find_beats`): independent component analysis of the same outlets × stories table. Where the
  correspondence analysis gives two broad axes, ICA gives groups of stories that rise together in one outlet or a few:
  that outlet's own agenda. A beat is kept only when it comes back in reruns (new seeds, 80% of the stories) and its
  stories hang together (their labels closer in meaning than random sets of our stories); it's named by its stories'
  labels, and by a TOPICS family when most of them share one.

Only outlets with MIN_STORIES of our stories and MIN_ARTICLES articles are profiled (story features need stories:
the site builds them from US and six UK outlets). CPU only, a few seconds; kept for the day in CACHE."""
import collections
import os
import re
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytz
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.stats import norm, rankdata, spearmanr

from app.analysis.edits import LIVE, LIVE_URL, is_minor, overlap
from app.analysis.wire import WIRES
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

WINDOW_DAYS = 28
MIN_STORIES = 20
MIN_ARTICLES = 100
MIN_STORY_OUTLETS = 3  # a story in the coverage analysis: run by this many profiled outlets
NEIGHBOURS = 3
AGREE = 2  # of an outlet's NEIGHBOURS look-alikes that must share its type for it to be shown
STABLE = 0.75  # clusterwise Jaccard (Hennig): above this a cluster is stable
BOOTS = 100
CACHE = os.path.join(Config.data, 'outlet_profile.json')
VERSION = 4  # bump when the method changes, so the day's cache is rebuilt (4: beats)
AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire', 'Memeorandum'}

# Beats (`find_beats`). How many components: ICA here takes the outlets as its samples, so it needs several outlets per
# component. With the 75 outlets of Oct 28, 8 components came back whole (outlet scores matched at r ≥ 0.97 and
# 9 of their 10 top stories in reruns on 80% of the stories); at 12 and 16 each distinctive outlet took a component of
# its own made of its leftover stories, and those came back less (6 to 8 of 10); at 6 beats merged. So one component
# per BEAT_PER outlets, at most BEAT_K; the beats that don't hold are dropped anyway
BEAT_K = 8
BEAT_PER = 9
BEAT_RUNS = 20  # reruns, each with a new seed and BEAT_FRAC of the stories
BEAT_FRAC = 0.8
BEAT_MATCH = 0.8  # a rerun's component is the beat come back when its outlet scores correlate this well...
BEAT_OVERLAP = 0.5  # ...and this share of the beat's defining stories are among the rerun's
BEAT_KEEP = 0.8  # share of the reruns a beat must come back in
BEAT_STORIES = 10  # the stories that define a beat: its highest loadings
BEAT_MIN_SCORE = 2.0  # the outlet furthest out on a beat, at least this far (components: unit variance over outlets)
# An outlet leads a beat when it ran LEAD_RAN of its defining stories and they're LEAD_FOCUS of all it ran (Oct 28:
# MarketWatch and Fox Business, The Daily Kos and the Star Tribune, The American Conservative and RFE/RL)
LEAD_RAN = 0.7
LEAD_FOCUS = 0.2
# Its stories must hang together: the mean similarity of their labels above this share of random sets of our stories.
# The guard against the small outlets: in ICA an outlet that ran only 20 of our stories stands far from the rest
# whatever those stories are, so every one of the Oct 28 leaders was among the smallest; Reason's and Salon's sets were
# a mix (68th and 65th percentile of random sets), the Rays, the Nobels or noncitizen voting were not (97th-100th)
BEAT_COHERENT = 0.95
BEAT_NULL_DRAWS = 500
SHARE_MIN = 4  # another outlet shares a beat when it ran this many of its defining stories...
SHARE_LIFT = 5  # ...at this many times its usual rate of running our stories
SHARE_MAX = 5
# A beat's short name (`beat_name`), from a TOPICS family its defining stories match far more than our stories at
# large; plain subjects, never a word about the outlets
BEAT_NAMES = {'politics': 'politics', 'crime': 'crime', 'immigration': 'immigration', 'world': 'world news',
              'business': 'business', 'tech_science': 'tech and science', 'health': 'health',
              'celebrity': 'entertainment', 'sport': 'sport'}
BEAT_NAME_SHARE = 0.4
BEAT_NAME_LIFT = 2

# Types named by their anchor outlets (from the study's clusters). A cluster takes the name whose anchors it holds most
# of, and only when it holds more than half of the anchors profiled this window
FAMILIES = {
    # The rest: a catch-all, named for what it isn't (Oct 28, the person, of One America News Network shown as "wire and
    # mainstream": "doesn't this seem wrong to you?")
    'Outside the partisan webs': ['AP', 'Reuters', 'New York Times', 'The Washington Post', 'NBC News', 'CBS News', 'ABC News',
                            'USA Today', 'Bloomberg', 'NPR', 'Axios', 'The Hill'],
    'Right partisan web': ['Breitbart', 'The Gateway Pundit', 'Townhall', 'Red State', 'The Daily Wire', 'PJ Media',
                           'The Western Journal', 'The Federalist', 'The Daily Caller'],
    'Left partisan web': ['Raw Story', 'Alternet', 'Mediaite', 'The Daily Kos', 'Salon', 'The New Republic',
                          'The Daily Beast'],
}
TYPES = {
    'Business desk': ['Bloomberg', 'Reuters', 'Financial Times', 'CNBC', 'MarketWatch', 'Business Insider'],
    'Washington and network news': ['AP', 'New York Times', 'The Washington Post', 'Axios', 'The Hill', 'NBC News',
                                    'CBS News', 'ABC News', 'CNN'],
    'General interest': ['BBC', 'Los Angeles Times', 'Chicago Tribune', 'Star Tribune', 'Tampa Bay Times'],
    'Explainers and public media': ['NPR', 'PBS NewsHour', 'Time', 'Forbes', 'Fortune', 'Scripps News'],
    'Slow analysis and magazines': ['The Economist', 'Semafor', 'Reason', 'The American Conservative'],
    'Right partisan web': FAMILIES['Right partisan web'],
    'Left Trump-watch': ['Raw Story', 'Alternet', 'Mediaite'],
    'Left opinion': ['The Daily Kos', 'Salon', 'The New Republic', 'The Daily Beast', 'MSNBC', 'Crooks and Liars'],
}
# Types named for a side; shown only on outlets rated on that side, or not rated (`_type_of`)
SIDE = {'Right partisan web': 1, 'Left partisan web': -1, 'Left Trump-watch': -1, 'Left opinion': -1}
# What each type does, in a line (the study's medians)
ABOUT = {
    'Outside the partisan webs': "Everyone outside the two partisan webs, from the wires to cable news: a big, mixed "
                                 "group that runs more of the stories everyone runs. Not a mark of quality or lean; "
                                 "its look-alikes say more.",
    'Right partisan web': 'Heated wording, the most crime and immigration stories, and more stories that mostly '
                          'right-leaning outlets run.',
    'Left partisan web': 'Heated wording about Trump and the political fight, with the most quotes and little wire copy.',
    'Business desk': 'Markets and companies, early and plain, and edits its headlines most.',
    'Washington and network news': 'Washington and the big shared stories, close to the wires.',
    'General interest': 'Local news, sport and entertainment alongside the big stories; posts a lot.',
    'Explainers and public media': 'Tech, health and explainers, with questions in headlines; later and calm.',
    'Slow analysis and magazines': 'World news and analysis that stays up for days.',
    'Left Trump-watch': 'Fast: quotes about Trump, mostly politics, often among the first to a story, and the most '
                        'heated.',
    'Left opinion': "Commentary on Trump, late to stories, and furthest from the wires' vocabulary.",
}

# ---- keyword families (the study's lexicons.py), matched on lowercased headlines ----


def _rx(words: list[str]) -> re.Pattern:
    """Any of the words, whole; matched on lowercased text"""
    return re.compile(r'(?<![\w])(?:' + '|'.join(words) + r')(?![\w])')


TOPICS = {
    'politics': _rx([r'trump\w*', 'biden', 'harris', 'vance', r'democrat\w*', 'dems?', r'republican\w*', 'gop', 'senate',
                     r'senators?', r'congress\w*', 'lawmakers?', r'elections?', r'midterms?', 'ballots?', 'voters?',
                     'campaign', 'governor', 'white house', 'maga', 'mamdani', 'newsom', 'schumer', 'pelosi', 'jeffries',
                     'filibuster', 'shutdown', r'polls?', 'primary', r'impeach\w*', 'speaker johnson', 'hegseth',
                     'leavitt', 'rubio', 'administration', 'starmer', 'farage', 'parliament', 'labour', 'tories', 'tory',
                     'modi']),
    'crime': _rx(['police', 'cops?', r'shoot\w*', 'shot', r'murder\w*', r'stabb\w*', r'arrest\w*', 'charged',
                  r'suspects?', 'jail', 'prison', 'sentenced', 'convicted', r'kidnap\w*', 'rape', r'rapist\w*',
                  r'assault\w*', 'robbery', 'homicide', r'gangs?', 'manhunt', r'carjack\w*', 'killer', 'gunman',
                  'indicted', 'indictment', 'fbi', 'cartel']),
    'immigration': _rx([r'immigra\w*', r'migrants?', 'ice', r'deport\w*', 'border', 'asylum', 'illegals',
                        r'aliens?', 'cbp', 'sanctuary', 'green card', 'h-1b']),
    'world': _rx(['ukraine', r'ukrainian\w*', r'russia\w*', 'putin', r'zelensk\w*', 'kyiv', r'israel\w*', 'gaza', 'hamas',
                  r'iran\w*', 'hezbollah', 'nato', 'syria', 'lebanon', r'venezuela\w*', 'ceasefire', r'missiles?', 'troops',
                  'sanctions', r'diplomat\w*', 'summit', 'embassy', 'kremlin', 'taiwan', 'north korea', 'beijing', 'china',
                  'chinese', 'xi', 'netanyahu', 'idf', 'west bank', 'houthis?', 'drones?', 'airstrikes?', 'war']),
    'business': _rx([r'stocks?', r'markets?', 'shares', 'earnings', r'profits?', 'revenue', 'fed', 'rates?', 'inflation',
                     r'econom\w*', 'gdp', r'tariffs?', 'trade', r'banks?', 'dow', 's&p', 'nasdaq', r'investors?', 'oil',
                     'bonds?', r'treasur\w*', 'ceo', 'ipo', 'layoffs?', 'crypto', 'bitcoin', r'billion\w*', 'sales',
                     r'compan\w*', 'firms?', 'deal', 'merger', 'acquisition']),
    'tech_science': _rx(['ai', 'openai', 'chatgpt', 'tech', 'apple', 'google', 'microsoft', 'nvidia', 'space', 'nasa',
                         r'scientists?', 'study', 'research', 'climate', r'cyber\w*', r'hack\w*', r'robot\w*', 'chips?']),
    'health': _rx(['health', 'cancer', r'vaccin\w*', 'covid', 'disease', r'hospitals?', r'doctors?', 'fda', 'cdc',
                   'outbreak', 'diet', 'medicaid', 'medicare', 'obesity', 'dementia', 'heart', 'virus', 'measles']),
    'celebrity': _rx(['star', r'celebrit\w*', 'actor', 'actress', 'singer', 'rapper', 'film', 'movie', 'netflix', 'album',
                      'swift', r'kardashian\w*', 'royals?', 'prince', 'princess', 'king charles', 'meghan', 'oscars?',
                      'grammys?', 'hollywood', 'wedding', 'divorce', 'dating', 'influencer', 'reality', 'bollywood',
                      'box office', 'fans', 'red carpet', 'pregnant', 'bikini', 'stuns', 'glamorous']),
    'sport': _rx(['nfl', 'nba', 'mlb', 'nhl', 'world series', r'playoffs?', 'coach', 'quarterback', 'football', 'soccer',
                  'cricket', 'ipl', 'premier league', 'league', 'match', 'dodgers', 'yankees', 'mets', 'jets', 'knicks',
                  r'olympic\w*', 'tennis', 'golf', 'f1', 'boxing', 'ufc', 'championship', 'tournament', 'innings',
                  'touchdown', 'pitcher', 'wicket', 'striker', 'goalkeeper', 'super bowl', 'wnba', 'nascar']),
}
COMBAT = _rx(['slams?', 'slammed', 'blasts?', 'blasted', 'rips', 'ripped', 'destroys?', 'destroyed', 'torch(?:es|ed)',
              'unloads?', r'eviscerat\w*', 'shreds?', r'obliterat\w*', r'humiliat\w*', 'mocks?', 'mocked',
              'trash(?:es|ed)', 'hammers?', r'scorch\w*', 'lashes out', 'fires back', 'claps back', 'goes off',
              r'melt\s?downs?', 'melts down', 'freaks? out', 'loses it', 'owns', 'owned', 'dunks? on', 'rages?',
              'fumes?', 'fuming', 'unhinged', 'deranged', 'bonkers', r'rant\w*', 'tirade', 'smacks? down', 'savages?',
              'roasts?', 'roasted', 'nukes?', 'skewers?', r'demolish\w*', 'body-?slams?'])
SENSATIONAL = _rx(['bombshell', 'shocking', 'shock', 'stunning', 'stuns?', 'explosive', 'jaw-?dropping', 'insane', 'wild',
                   'brutal', 'epic', 'chilling', 'horrifying', 'terrifying', 'disturbing', 'incredible', 'unbelievable',
                   'massive', 'huge', 'must-see', "you won't believe", 'outrage', 'outraged', 'furious', 'fury'])
# Each side's words for the other ("R": the right's for the left; "L": the left's for the right). Whose vocabulary a
# headline borrows, quotes included; not proof of side
R_LABELS = _rx([r'leftists?', 'radical left', r'far[- ]left', 'woke', 'libs', r'commie\w*', r'communists?', r'marxists?',
                r'socialists?', 'dems', 'democrat party', 'illegals', r'illegal aliens?', 'antifa', r'globalists?',
                r'groomers?', 'legacy media', 'corporate media', 'mainstream media', 'msm', 'trump derangement', 'tds',
                'regime media', 'leftwing', 'left-wing', 'democrat-run', 'blue-state', 'soros'])
L_LABELS = _rx(['maga', r'far[- ]right', r'fascis\w*', r'authoritarian\w*', r'autocra\w*', r'christian nationalis\w*',
                r'white nationalis\w*', r'white supremac\w*', 'cult', 'trump regime', 'regime', r'oligarch\w*',
                r'kleptocra\w*', 'gestapo', r'insurrection\w*', 'trumpism', 'right-wing', 'rightwing', 'felon',
                'extremist', 'project 2025', r'dictator\w*', 'goons?'])
# Argument vocabulary of both directions (the study's audited lists): a clustering input, never shown or scored
ARGUMENT = _rx(['deep state', r'cover-?ups?', 'covered up', 'rigged', 'false flag', r'globalists?', 'cabal', 'plandemic',
                'great reset', 'great replacement', r'psy-?ops?', 'stolen election', 'ballot harvesting', r'two-tier\w*',
                'lawfare', 'big pharma', r'chemtrails?', 'soros', 'uniparty', 'sharia', 'crisis actors?',
                'sleeper cells?', r'weaponiz\w*', 'shadow government', 'swamp', 'regime media', 'russian asset',
                'kremlin asset', 'foreign asset', r'puppets?', 'kompromat', 'dark money', 'secret plot', 'power grab',
                'slush fund', 'shadow network', 'billionaire-funded', r'stochastic terror\w*', 'self-coup',
                'coup attempt'])
TRUMP = _rx([r'trump\w*'])
NAMES = _rx([r'trump\w*', 'biden', 'harris', 'kamala', 'vance', 'obama', 'musk', 'newsom', 'hochul', 'mamdani',
             'ocasio-cortez', 'aoc', 'pelosi', 'schumer', 'jeffries', 'omar', 'hegseth', 'rubio', 'leavitt', 'patel',
             'bondi', 'rfk', 'kennedy', 'epstein', 'netanyahu', 'putin', r'zelensk\w*', 'starmer', 'farage', 'modi',
             'swalwell', 'talarico', 'el-sayed', 'clinton', 'desantis', 'maxwell', 'comey', 'mike johnson', 'thune',
             'crockett', 'walz', 'pritzker', 'xi'])
FIRST_PERSON = _rx(['i', "i'm", "i've", 'my', 'we', "we're", 'our', 'you', 'your', "you're"])
QUOTE = re.compile(r"(?:^|[\s:(—–-])[\"“‘'][^\"“”]{3,}?[\"”’'](?=$|[\s,.:;?!)—–-])")
# Scraper residue and house labels, stripped before counting words and matching
JUNK = re.compile(r"(?:\b\d+\s*(?:hours?|hrs?|minutes?|mins?|days?)\s+ago\b|\bmin(?:ute)?s?\s+read\b|\b\d+\s+min\b|"
                  r"\bread more\b|\bvia getty(?: images)?\b|\bgetty images\b|[-–|]\s*reuters(?:\.com)?\b|"
                  r"[-–|]\s*ap news\b|\bfor subscribers\b|\((?:video|watch|photos?)\)|\bopinion\s*\||•|\.\.\.|…|"
                  r"\bbreaking news\b|\banalysis by\b.*$)", re.I)
KICKER = re.compile(r'^(?:[A-Z][A-Z0-9\s\'’&]{1,30}(?:\s*[:—–|]|\s{2,}))+\s*|'
                    r'^(?:(?:exclusive|watch|video|live|breaking|opinion|analysis|updated?|just in|new)\s*[:—–|-]\s*)+',
                    re.I)
TOKEN = re.compile(r"[A-Za-z][A-Za-z'’]{3,}")
DEK = re.compile(r'\.\s+[A-Z]')  # a second sentence: the scraper took the dek too
WORD = re.compile(r"[\w$%'’]+")
STOP = {'a', 'an', 'the', 'of', 'to', 'in', 'on', 'for', 'and', 'or', 'at', 'by', 'with', 'from', 'as', 'is', 'are',
        'was', 'be', 'after', 'over', 'amid', 'says', 'said', 'new', 'its', 'it', 'that', 'this'}

# Feature groups, each weighted alike in the clustering (1/sqrt of its size)
GROUPS = {
    'coverage': ['ca1', 'ca2', 'ca3', 't_politics', 't_crime', 't_immigration', 't_world', 't_business',
                 't_tech_science', 't_health', 't_celebrity', 't_sport'],
    'agenda': ['wire_overlap', 'wire_nearcopy', 'wire_sim', 'wire_vocab_sim', 'story_headline_share',
               'small_story_share'],
    'timing': ['early_lift', 'median_lag_h', 'span_vs_life'],
    'sidedness': ['one_sided_R', 'one_sided_L', 'other_right_share'],
    'form': ['words', 'question', 'exclaim', 'quote', 'caps', 'number', 'first_person'],
    'heat': ['combat', 'sensational', 'loaded', 'loaded2', 'outrage_emotion', 'e_fear', 'e_neutral', 'event', 'vader'],
    'labels': ['r_labels', 'l_labels', 'argument', 'trump', 'names'],
    'churn': ['log_articles_per_day', 'log_median_life_h', 'edits_per_100', 'news_share'],
}
WIRE_AXIS = {'wire_overlap': 1, 'wire_sim': 1, 'wire_nearcopy': 1, 'wire_vocab_sim': 1, 'story_headline_share': 1}
HEAT_AXIS = {'loaded': 1, 'combat': 1, 'sensational': 1, 'outrage_emotion': 1, 'label_rate': 1, 'e_neutral': -1}


# ---------------------------------------------------------------- reading


def load(since: dt, con=None) -> dict[str, pd.DataFrame]:
    """Headline rows since `since` with their outlet, the story links among them, the outlets and story labels"""
    from sqlalchemy import text
    if con is None:
        from app.models import engine
        with engine.connect() as c:
            return load(since, c)

    def q(sql, **params):
        if hasattr(con, 'execute') and not hasattr(con, 'cursor'):  # a SQLAlchemy connection
            return pd.read_sql(text(sql), con, params=params)
        return pd.read_sql(sql.replace(':since', '?'), con, params=list(params.values()))
    s = since.strftime('%Y-%m-%d %H:%M:%S')
    heads = q('''select h.id, h.article_id, h.title, h.first_accessed hfa, h.last_accessed hla, h.news_score news,
                        h.event_score event, h.loaded_score loaded, h.vader_compound vader, h.emotion, ar.url, g.name
                 from headline h join article ar on ar.id = h.article_id join agency g on g.id = ar.agency_id
                 where h.first_accessed >= :since''', since=s)
    links = q('''select sh.story_id, sh.headline_id id from story_headline sh join headline h on h.id = sh.headline_id
                 where h.first_accessed >= :since''', since=s)
    outlets = q('select name, _bias bias, lean_rated rated from agency')
    labels = q('select id story_id, label from story')
    for c in ('hfa', 'hla'):
        heads[c] = pd.to_datetime(heads[c], format='mixed')
    return {'heads': heads, 'links': links, 'outlets': outlets, 'labels': labels}


# ---------------------------------------------------------------- maths


def rank_gauss(col: pd.Series) -> pd.Series:
    """Ranks mapped onto a normal curve (ties share a rank); missing stays missing"""
    x = col.to_numpy(dtype=float)
    ok = ~np.isnan(x)
    out = np.full(len(x), np.nan)
    if ok.any():
        out[ok] = norm.ppf((rankdata(x[ok]) - 0.5) / ok.sum())
    return pd.Series(out, index=col.index)


def axis_score(F: pd.DataFrame, signs: dict) -> pd.Series:
    """The mean rank-normal score of the named features, each with its sign"""
    return pd.concat([rank_gauss(F[c]) * s for c, s in signs.items()], axis=1).mean(axis=1)


def percentile(x: pd.Series) -> pd.Series:
    """Each value's share of the others below it (ties count half), 0-100"""
    r = rankdata(x.to_numpy(dtype=float))
    return pd.Series(np.round(100 * (r - 1) / max(len(x) - 1, 1)).astype(int), index=x.index)


def correspondence(X: pd.DataFrame, dims: int = 3) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Correspondence analysis of a 0/1 outlets × stories table: the rows' and columns' principal coordinates on the
    first `dims` axes, and each axis' share of the inertia"""
    P = X.to_numpy(dtype=float)
    P = P / P.sum()
    r, c = P.sum(1), P.sum(0)
    S = (P - np.outer(r, c)) / np.sqrt(np.outer(r, c))
    U, s, Vt = np.linalg.svd(S, full_matrices=False)
    rows = pd.DataFrame(U[:, :dims] * s[:dims] / np.sqrt(r)[:, None], index=X.index,
                        columns=[f'ca{i + 1}' for i in range(dims)])
    cols = pd.DataFrame(Vt[:dims].T * s[:dims] / np.sqrt(c)[:, None], index=X.columns, columns=rows.columns)
    cols['mass'] = c
    return rows, cols, (s ** 2 / (s ** 2).sum())[:dims]


def orient(rows: pd.DataFrame, cols: pd.DataFrame, bias: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Fix each axis' sign, which the maths leaves arbitrary, so the map doesn't flip from one week to the next. By
    the rated outlets (`bias`, -2..2, rated ones only): ca1's high end is where outlets rated far left or right gather
    (rank correlation with |lean| positive), ca2's high end is where left-rated ones gather (with lean negative).
    ca3 follows lean like ca2. Returns the flipped rows and columns and the two correlations, after the flip."""
    rated = bias.reindex(rows.index).dropna()
    rows, cols = rows.copy(), cols.copy()
    rho = {}
    for axis, target, want in (('ca1', rated.abs(), 1), ('ca2', rated, -1), ('ca3', rated, -1)):
        if axis not in rows:
            continue
        r = spearmanr(rows.loc[rated.index, axis], target)[0] if len(rated) >= 3 else np.nan
        if np.isnan(r):  # no rated outlets to go by (or no spread): the side with the heavier tail is high
            r = want * float(np.sign((rows[axis] ** 3).sum()) or 1)
        if np.sign(r) != want:
            rows[axis] *= -1
            cols[axis] *= -1
            r = -r
        rho[axis] = round(float(r), 3)
    return rows, cols, rho


def nearest(Z: pd.DataFrame, k: int = NEIGHBOURS) -> dict[str, list[str]]:
    """Each row's k nearest other rows by Euclidean distance, nearest first (ties by name)"""
    X = Z.to_numpy(dtype=float)
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    names = list(Z.index)
    out = {}
    for i, name in enumerate(names):
        order = sorted((j for j in range(len(names)) if j != i), key=lambda j: (round(D[i, j], 9), names[j]))
        out[name] = [names[j] for j in order[:k]]
    return out


def ward(X: np.ndarray, k: int) -> np.ndarray:
    return fcluster(linkage(X, 'ward'), k, 'maxclust')


def jaccard(X: np.ndarray, labels: np.ndarray, k: int, boots: int = BOOTS, frac: float = 0.8,
            seed: int = 1) -> dict[int, float]:
    """Clusterwise stability (Hennig): for each cluster, its mean best Jaccard with a cluster of a reclustered 80%
    subsample"""
    rng = np.random.default_rng(seed)
    n = len(X)
    res = {int(c): [] for c in np.unique(labels)}
    for _ in range(boots):
        idx = np.sort(rng.choice(n, int(frac * n), replace=False))
        lb = ward(X[idx], k)
        for c in res:
            a = set(idx[labels[idx] == c])
            if a:
                res[c].append(max(len(a & set(idx[lb == d])) / len(a | set(idx[lb == d])) for d in np.unique(lb)))
    return {c: float(np.mean(v)) if v else 0.0 for c, v in res.items()}


def name_clusters(labels: pd.Series, anchors: dict[str, list[str]]) -> dict[int, str]:
    """cluster -> name: a name goes to the cluster holding more than half of its anchors (of those present). A cluster
    claimed by two names (one holding both the left and the right partisan web, say) gets neither"""
    claims = collections.defaultdict(list)
    for name, members in anchors.items():
        present = [m for m in members if m in labels.index]
        if present:
            counts = labels[present].value_counts()
            if counts.iloc[0] / len(present) > 0.5:
                claims[int(counts.index[0])].append(name)
    return {c: names[0] for c, names in claims.items() if len(names) == 1}


def find_types(Z: pd.DataFrame, anchors: dict[str, list[str]], ks=range(2, 11), stability: dict | None = None) -> dict:
    """Each named type at the cut of the Ward tree where it's most stable (clusterwise Jaccard), kept when that's at
    least STABLE: name -> {'members', 'stability', 'k'}. Pass the same `stability` dict to share the bootstraps"""
    X = Z.to_numpy()
    tree = linkage(X, 'ward')
    stability = {} if stability is None else stability
    best = {}
    for k in ks:
        if k > len(Z):
            break
        labels = pd.Series(fcluster(tree, k, 'maxclust'), index=Z.index)
        names = name_clusters(labels, anchors)
        if not names:
            continue
        if k not in stability:
            stability[k] = jaccard(X, labels.to_numpy(), k)
        for c, name in names.items():
            s = stability[k][c]
            if name not in best or s > best[name]['stability']:
                best[name] = {'members': sorted(labels.index[labels == c]), 'stability': round(s, 2), 'k': k}
    return {n: t for n, t in best.items() if t['stability'] >= STABLE}


# ---------------------------------------------------------------- features


def _clean(title: str) -> str:
    t = JUNK.sub(' ', ' '.join(str(title).split()))
    t = KICKER.sub('', t)
    return re.sub(r'\s+[-–|:]\s*$', '', ' '.join(t.split())).strip()


def _words(text: str) -> frozenset:
    return frozenset(w for w in (x.lower().replace('’', "'") for x in WORD.findall(text)) if w not in STOP and len(w) > 1)


def run_starts(times: pd.Series) -> np.ndarray:
    """The start of each hourly scrape run: first-seen times more than 10 minutes after the one before"""
    t = np.sort(times.unique())
    if not len(t):
        return t
    gaps = np.diff(t) > np.timedelta64(10, 'm')
    return t[np.concatenate([[True], gaps])]


def features(data: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """One row per outlet: the study's behaviour features. Also returns the articles and who ran which story"""
    H = data['heads']
    H = H[~H['name'].isin(AGGREGATORS)].copy()
    rating = data['outlets'].set_index('name')
    side = pd.Series(np.where(rating['rated'].astype(bool), np.sign(rating['bias']), np.nan), index=rating.index)
    H = H.sort_values(['article_id', 'hfa'])
    H['clean'] = H['title'].map({t: _clean(t) for t in H['title'].unique()})
    # the article is the unit for style and topics (its first wording), so edits don't count twice
    art = H.groupby('article_id').agg(name=('name', 'first'), title=('title', 'first'), clean=('clean', 'first'),
                                      hfa=('hfa', 'min'), hla=('hla', 'max'), news=('news', 'first'),
                                      loaded=('loaded', 'first'), event=('event', 'first'), vader=('vader', 'first'),
                                      emotion=('emotion', 'first'))
    art['life_h'] = (art['hla'] - art['hfa']).dt.total_seconds() / 3600
    lc = art['clean'].str.lower()
    # ALL CAPS: a word of 4+ letters in capitals that's usually written in lower or title case elsewhere
    caps, every = collections.Counter(), collections.Counter()
    for t in H['title'].drop_duplicates():
        for w in TOKEN.findall(t):
            every[w.lower()] += 1
            if w.isupper():
                caps[w.lower()] += 1
    shout = {k for k in caps if every[k] >= 5 and caps[k] / every[k] < 0.3}
    art['words'] = art['clean'].str.split().str.len()
    art['question'] = art['clean'].str.contains('?', regex=False)
    art['exclaim'] = art['clean'].str.contains('!', regex=False)
    art['quote'] = art['title'].str.contains(QUOTE)
    art['caps'] = art['title'].map(lambda t: any(w.isupper() and w.lower() in shout for w in TOKEN.findall(t)))
    art['number'] = art['clean'].str.contains(r'\d')
    for col, rx in (('first_person', FIRST_PERSON), ('combat', COMBAT), ('sensational', SENSATIONAL),
                    ('r_labels', R_LABELS), ('l_labels', L_LABELS), ('argument', ARGUMENT), ('trump', TRUMP),
                    ('names', NAMES)):
        art[col] = lc.str.contains(rx)
    for k, rx in TOPICS.items():
        art['t_' + k] = lc.str.contains(rx)
    art['is_news'] = art['news'] >= 0.5
    art['loaded2'] = art['loaded'] >= 2
    for e in ('fear', 'anger', 'disgust', 'neutral'):
        art['e_' + e] = art['emotion'] == e
    days = max((H['hfa'].max() - H['hfa'].min()).total_seconds() / 86400, 1 / 24)
    g = art.groupby('name')
    F = pd.DataFrame({'articles': g.size()})
    F['log_articles_per_day'] = np.log(F['articles'] / days)
    F['log_median_life_h'] = np.log(g['life_h'].median().clip(lower=1))
    F['news_share'] = g['is_news'].mean()
    gn = art[art['is_news']].groupby('name')  # style on news headlines only
    for c in ('words', 'question', 'exclaim', 'quote', 'caps', 'number', 'first_person', 'combat', 'sensational',
              'r_labels', 'l_labels', 'argument', 'trump', 'names', 'loaded', 'loaded2', 'event', 'vader', 'e_fear',
              'e_anger', 'e_disgust', 'e_neutral'):
        F[c] = gn[c].mean()
    F['outrage_emotion'] = F['e_anger'] + F['e_disgust']
    F['label_rate'] = F['r_labels'] + F['l_labels']
    for k in TOPICS:
        F['t_' + k] = g['t_' + k].mean()  # topics on every article

    # headline rewrites, by the edits page's rules
    edits = collections.Counter()
    multi = H[H.groupby('article_id')['title'].transform('nunique') > 1]
    rows = list(multi[['article_id', 'title', 'hfa', 'hla', 'news', 'url', 'name']].itertuples(index=False))
    for a, b in zip(rows, rows[1:]):  # each wording against the one before it on the same article
        if a.article_id != b.article_id:
            continue
        if a.title.strip() == b.title.strip() or a.hla >= b.hfa:
            continue
        if any(pd.notna(r.news) and r.news < 0.5 for r in (a, b)):
            continue
        if LIVE.search(a.title) or LIVE.search(b.title) or LIVE_URL.search(b.url or ''):
            continue
        if overlap(a.title, b.title) < 0.2 or is_minor(a.title, b.title):
            continue
        if max(len(a.title.split()), len(b.title.split())) > 22 or DEK.search(a.title) or DEK.search(b.title):
            continue  # a dek, not a headline
        edits[b.name] += 1
    F['edits_per_100'] = 100 * pd.Series(edits, dtype=float).reindex(F.index).fillna(0) / F['articles']

    # ---- story features: who ran which of our stories, when, and with whom
    starts = run_starts(H['hfa'])
    sm = data['links'].merge(H[['id', 'name', 'hfa', 'hla', 'clean']], on='id')
    sm['side'] = sm['name'].map(side)
    sm['run'] = np.searchsorted(starts, sm['hfa'].to_numpy(), side='right') - 1
    os_ = sm.groupby(['story_id', 'name']).agg(t=('hfa', 'min'), last=('hla', 'max'), run=('run', 'min'),
                                               side=('side', 'first')).reset_index()
    if os_.empty:
        return F.assign(stories=0), art, os_
    os_['span_h'] = (os_['last'] - os_['t']).dt.total_seconds() / 3600
    st = os_.groupby('story_id').agg(n=('name', 'size'), first_run=('run', 'min'),
                                     L=('side', lambda x: (x < 0).sum()), R=('side', lambda x: (x > 0).sum()),
                                     C=('side', lambda x: (x == 0).sum()))
    runs = os_.groupby('story_id')['run'].apply(lambda x: np.sort(x.to_numpy()))
    st['third_run'] = runs.map(lambda r: r[min(2, len(r) - 1)])
    st['gap_next_h'] = runs.map(lambda r: (starts[r[r > r[0]][0]] - starts[r[0]]) / np.timedelta64(1, 'h')
                                if (r > r[0]).any() else np.nan)
    os_ = os_.merge(st, left_on='story_id', right_index=True)
    # the side mix of the *other* rated outlets on each story (leave one out)
    oL = os_['L'] - (os_['side'] < 0)
    oR = os_['R'] - (os_['side'] > 0)
    rated_o = oL + oR + os_['C'] - (os_['side'] == 0)
    share_r = oR / rated_o.where(rated_o > 0)
    share_l = oL / rated_o.where(rated_o > 0)
    os_['other_right_share'] = share_r
    os_['one_sided_R'] = np.where(rated_o >= 5, share_r >= 0.8, np.nan)
    os_['one_sided_L'] = np.where(rated_o >= 5, share_l >= 0.8, np.nan)
    os_['small'] = os_['n'] <= 7
    wire_on = os_[os_['name'].isin(WIRES)].groupby('story_id')['name'].apply(set)
    os_['wire_other'] = [bool(wire_on.get(s, set()) - {n}) for s, n in zip(os_['story_id'], os_['name'])]
    # arriving early: by the run of the story's third outlet, against the share of its outlets that did
    valid = (os_['n'] >= 5) & (os_['gap_next_h'] <= 24) & \
        (starts[os_['first_run']] >= starts[0] + np.timedelta64(2, 'h'))
    os_['early'] = os_['run'] <= os_['third_run']
    os_['exp_early'] = os_.groupby('story_id')['early'].transform('sum') / os_['n']
    os_['lag_h'] = (starts[os_['run']] - starts[os_['first_run']]) / np.timedelta64(1, 'h')
    in_story = sm.groupby('name')['id'].nunique()
    gs = os_.groupby('name')
    S = pd.DataFrame({'stories': gs.size(),
                      'story_headline_share': in_story / H.groupby('name')['id'].nunique(),
                      'wire_overlap': gs['wire_other'].mean(), 'other_right_share': gs['other_right_share'].mean(),
                      'one_sided_R': gs['one_sided_R'].mean(), 'one_sided_L': gs['one_sided_L'].mean(),
                      'small_story_share': gs['small'].mean(), 'median_span_h': gs['span_h'].median()})
    v = os_[valid].groupby('name')
    S['early_lift'] = v['early'].mean() / v['exp_early'].mean()
    S['median_lag_h'] = v['lag_h'].median()
    # on stories a wire ran too: the best word-set Jaccard between this outlet's headline and a wire's
    sm['tok'] = sm['clean'].map(_words)
    wire_tok = {s: list(zip(x['name'], x['tok'])) for s, x in sm[sm['name'].isin(WIRES)].groupby('story_id')}
    best = collections.defaultdict(list)
    for (s, name), x in sm[sm['story_id'].isin(wire_tok)].groupby(['story_id', 'name']):
        wt = [tk for wn, tk in wire_tok[s] if wn != name]
        if wt:
            best[name].append(max(len(a & w) / max(len(a | w), 1) for a in x['tok'] for w in wt))
    S['wire_sim'] = pd.Series({k: np.mean(b) for k, b in best.items()}, dtype=float)
    S['wire_nearcopy'] = pd.Series({k: np.mean(np.array(b) >= 0.5) for k, b in best.items()}, dtype=float)
    F = F.join(S, how='left')
    F['span_vs_life'] = F['median_span_h'] / np.exp(F['log_median_life_h'])
    F['wire_vocab_sim'] = wire_vocabulary(art)
    return F, art, os_[['story_id', 'name']]


def wire_vocabulary(art: pd.DataFrame, per_outlet: int = 300, draws: int = 3) -> pd.Series:
    """TF-IDF cosine of each outlet's news vocabulary against AP's and Reuters', on equal samples of headlines (so a
    big outlet doesn't look wire-like by volume); each wire against the other wire"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    news = art[art['is_news']].copy()
    news['lc'] = news['clean'].str.lower()
    sims = []
    for seed in range(draws):
        smp = news.sample(frac=1, random_state=seed).groupby('name').head(per_outlet)
        smp = smp[smp.groupby('name')['lc'].transform('size') >= 100]
        docs = smp.groupby('name')['lc'].apply(' '.join)
        wires = sorted(w for w in WIRES if w in docs.index)
        if not wires:
            return pd.Series(dtype=float)
        tv = TfidfVectorizer(min_df=3, max_df=0.9, sublinear_tf=True, token_pattern=r"[a-z][a-z'\-]+")
        M = tv.fit_transform(list(docs.values) + [' '.join(docs[wires])] + [docs[w] for w in wires])
        sim = pd.Series(cosine_similarity(M[:len(docs)], M[len(docs)]).ravel(), index=docs.index)
        if len(wires) == 2:
            for i, w in enumerate(wires):
                sim[w] = cosine_similarity(M[docs.index.get_loc(w)], M[len(docs) + 2 - i])[0, 0]
        sims.append(sim)
    return pd.concat(sims, axis=1).mean(axis=1)


# ---------------------------------------------------------------- beats


def ica(X: pd.DataFrame, k: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """FastICA on the outlets' coverage profiles (each outlet's row as shares, each story centred, as in the Oct 28
    study): the outlets' scores (outlets × k, unit variance, each turned so its long tail is positive) and the
    stories' loadings (stories × k, the profiles projected on the scores)"""
    import warnings
    from sklearn.decomposition import FastICA
    from sklearn.exceptions import ConvergenceWarning
    P = X.to_numpy(dtype=float)
    P = P / P.sum(axis=1, keepdims=True)
    P = P - P.mean(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', ConvergenceWarning)
        S = FastICA(k, random_state=seed, max_iter=2000, whiten='unit-variance').fit_transform(P)
    sign = np.sign((S ** 3).sum(axis=0))
    S = S * np.where(sign == 0, 1, sign)
    return S, P.T @ S / len(P)


def _corr(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Pearson correlations between the columns of A and those of B"""
    A = (A - A.mean(0)) / (A.std(0) + 1e-12)
    B = (B - B.mean(0)) / (B.std(0) + 1e-12)
    return A.T @ B / len(A)


def beat_stability(X: pd.DataFrame, k: int, S0: np.ndarray, L0: np.ndarray, runs: int = BEAT_RUNS,
                   seed: int = 0) -> np.ndarray:
    """For each component of the full run, the share of reruns (each with its own seed and BEAT_FRAC of the stories)
    it comes back in: a rerun component whose outlet scores correlate at least BEAT_MATCH with it and whose top
    stories hold BEAT_OVERLAP of its own top stories among those drawn"""
    rng = np.random.default_rng(seed)
    n = X.shape[1]
    back = np.zeros(S0.shape[1])
    for r in range(runs):
        cols = np.sort(rng.choice(n, int(BEAT_FRAC * n), replace=False))
        S, L = ica(X.iloc[:, cols], k, seed + r + 1)
        C = _corr(S0, S)
        for c in range(S0.shape[1]):
            d = int(np.abs(C[c]).argmax())
            if abs(C[c, d]) < BEAT_MATCH:
                continue
            ref = L0[cols, c]
            got = L[:, d] * np.sign(C[c, d])
            m = min(BEAT_STORIES, len(cols))
            mine, theirs = set(np.argsort(-ref)[:m]), set(np.argsort(-got)[:m])
            back[c] += len(mine & theirs) / m >= BEAT_OVERLAP
    return back / runs


def coherence(vectors: np.ndarray, idx: np.ndarray, draws: int = BEAT_NULL_DRAWS, seed: int = 0) -> float:
    """How well a set of stories hangs together: the share of random sets of as many of our stories whose labels'
    mean pairwise cosine is below the set's (vectors: one unit row per story)"""
    def mean_cos(i):
        V = vectors[i]
        G = V @ V.T
        return (G.sum() - np.trace(G)) / (len(i) * (len(i) - 1))
    if len(idx) < 2:
        return 0.0
    rng = np.random.default_rng(seed)
    mine = mean_cos(idx)
    null = np.array([mean_cos(rng.choice(len(vectors), len(idx), replace=False)) for _ in range(draws)])
    return float(np.mean(null < mine))


def label_vectors(texts: list[str]) -> np.ndarray:
    """The story labels as unit vectors, by the site's own story embedder (a small static model, on the CPU)"""
    from app.analysis import clustering
    from app.analysis.embeddings import static, unit
    return unit(static(texts, clustering.EMBEDDING_MODEL))


def topic_shares(labels: list[str]) -> dict[str, float]:
    """The share of the labels each TOPICS family matches"""
    low = [t.lower() for t in labels]
    return {k: sum(bool(rx.search(t)) for t in low) / max(len(low), 1) for k, rx in TOPICS.items()}


def beat_name(labels: list[str], base: dict[str, float]) -> str | None:
    """A short name: the TOPICS family matching at least BEAT_NAME_SHARE of the labels and BEAT_NAME_LIFT times its
    share of all our stories (`base`: politics matches a third of them, so it names only a beat that's mostly
    politics); the most matched of those, or None"""
    shares = topic_shares(labels)
    fits = [k for k, v in shares.items() if v >= BEAT_NAME_SHARE and v >= BEAT_NAME_LIFT * base.get(k, 0)]
    return BEAT_NAMES.get(max(fits, key=lambda k: (shares[k], k))) if fits else None


def find_beats(X: pd.DataFrame, labels: pd.Series, vectors=None, k: int | None = None) -> list[dict]:
    """Each outlet's own agenda, from ICA on the coverage table: the beats that hold (BEAT_KEEP of the reruns) and
    hang together (BEAT_COHERENT), each with the outlets leading it (LEAD_RAN, LEAD_FOCUS; by score, highest first),
    the other outlets that share it (ran SHARE_MIN of its stories at SHARE_LIFT times their usual rate), its defining
    stories (with the leaders that ran each) and a short name when its stories give one. An outlet leading two beats
    keeps the one that's the bigger part of what it ran; an outlet leading none has no beat. `vectors`: the story
    labels' embedder (label_vectors)"""
    k = k or min(BEAT_K, max(2, len(X) // BEAT_PER))
    if len(X) < 2 * k or X.shape[1] < 2 * BEAT_STORIES:
        return []
    S, L = ica(X, k, 0)
    held = beat_stability(X, k, S, L)
    texts = [str(labels.get(s, '') or '') for s in X.columns]
    try:
        V = (vectors or label_vectors)(texts)
    except Exception:  # noqa: BLE001 - no embedder: no way to tell a beat from a small outlet's mix, so none
        logger.exception("Beats: the story labels couldn't be embedded; no beats this time")
        return []
    base = X.mean(axis=1)
    topics = topic_shares([t for t in texts if t])
    found = []
    total = X.sum(axis=1)
    for c in range(k):
        s = pd.Series(S[:, c], index=X.index)
        defining = np.argsort(-L[:, c])[:BEAT_STORIES]
        ran = X.iloc[:, defining].sum(axis=1)
        lift = (ran / len(defining)) / base.where(base > 0)
        # leading: most of the beat's stories, and they're a good part of all it ran (not a big outlet that runs
        # everything); the outlet ICA puts furthest out must be one, or the component isn't anyone's beat
        focus = ran / total.where(total > 0)
        leads = (ran >= LEAD_RAN * len(defining)) & (focus >= LEAD_FOCUS)
        first = s.idxmax()
        leaders = sorted(leads.index[leads], key=lambda o: -s[o])
        coh = coherence(V, defining)
        logger.info("Beat %d: %s (score %.1f), leading %s, came back %.0f%%, hangs together %.2f", c, first,
                    s[first], ', '.join(leaders) or '-', 100 * held[c], coh)
        if first not in leaders or s[first] < BEAT_MIN_SCORE or held[c] < BEAT_KEEP or coh < BEAT_COHERENT:
            continue
        shared = [o for o in lift.sort_values(ascending=False).index
                  if o not in leaders and ran[o] >= SHARE_MIN and lift[o] >= SHARE_LIFT][:SHARE_MAX]
        stories = []
        for j in defining:
            sid = X.columns[j]
            label = labels.get(sid)
            if not isinstance(label, str) or not label.strip():
                continue
            stories.append({'id': int(sid) if isinstance(sid, (int, np.integer)) else str(sid), 'label': label.strip(),
                            'outlets': int(X.iloc[:, j].sum()), 'by': [o for o in leaders if X.iloc[:, j][o]]})
        found.append({'component': c, 'score': round(float(s[first]), 2), 'held': round(float(held[c]), 2),
                      'coherence': round(coh, 2), 'leaders': leaders,
                      'focus': {o: round(float(focus[o]), 3) for o in leaders},
                      'shared': [{'name': o, 'ran': int(ran[o]), 'lift': round(float(lift[o]), 1)} for o in shared],
                      'name': beat_name([x['label'] for x in stories], topics), 'stories': stories})
    # an outlet leads one beat at most: the one that's the biggest part of what it ran. Two outlets on one beat can
    # each get a component of their own (ICA splits them into spikes), so the same beat can turn up twice: the
    # copy left with no leader goes
    best = {}
    for b in sorted(found, key=lambda b: -b['score']):
        for o in b['leaders']:
            if o not in best or b['focus'][o] > best[o]['focus'][o]:
                best[o] = b
    for b in found:
        b['leaders'] = [o for o in b['leaders'] if best[o] is b]
        for st in b['stories']:
            st['by'] = [o for o in st['by'] if o in b['leaders']]
    beats = sorted((b for b in found if b['leaders']), key=lambda b: -b['score'])
    logger.info("Beats: %s", '; '.join(f"{', '.join(b['leaders'])} ({b['name'] or 'unnamed'})" for b in beats)
                or 'none held')
    return beats


# ---------------------------------------------------------------- the profile


def build(data: dict, until: dt) -> dict:
    """Everything the outlet map and the outlet pages show, from `load`'s frames"""
    F, art, os_ = features(data)
    if os_.empty:
        return {'outlets': {}, 'types': [], 'axes': {}}
    tier = F[(F['stories'] >= MIN_STORIES) & (F['articles'] >= MIN_ARTICLES)].copy()
    rating = data['outlets'].set_index('name')
    bias = rating['bias'].where(rating['rated'].astype(bool))
    # coverage: our stories that MIN_STORY_OUTLETS or more profiled outlets ran
    X = pd.crosstab(os_['name'], os_['story_id']).reindex(tier.index).fillna(0).clip(upper=1)
    X = X.loc[:, X.sum(axis=0) >= MIN_STORY_OUTLETS]
    X = X[X.sum(axis=1) > 0]
    tier = tier.loc[X.index]
    if len(tier) < 8:
        return {'outlets': {}, 'types': [], 'axes': {}}
    rows, cols, inertia = correspondence(X)
    rows, cols, rho = orient(rows, cols, bias.dropna())
    tier = tier.join(rows)
    tier['wire_axis'] = axis_score(tier, WIRE_AXIS)
    tier['heat_axis'] = axis_score(tier, HEAT_AXIS)
    # the clustering space: each feature on a normal curve, each group weighted alike, missing at the median
    feats = [c for cs in GROUPS.values() for c in cs]
    weights = np.array([1 / np.sqrt(len(cs)) for cs in GROUPS.values() for _ in cs])
    Z = tier[feats].apply(rank_gauss).fillna(0.0) * weights
    like = nearest(Z)
    stability = {}
    families, kinds = find_types(Z, FAMILIES, stability=stability), find_types(Z, TYPES, stability=stability)
    labels = data['labels'].set_index('story_id')['label']
    try:
        beats = find_beats(X, labels)
    except Exception:  # noqa: BLE001 - the profile without beats beats no profile
        logger.exception("Beats failed; the profile goes without them")
        beats = []
    beat_of = {o: i for i, b in enumerate(beats) for o in b['leaders']}
    wire_pct, heat_pct = percentile(tier['wire_axis']), percentile(tier['heat_axis'])
    first = {name: (_type_of(name, families, bias.get(name)), _type_of(name, kinds, bias.get(name))) for name in tier.index}
    out = {}
    for name, r in tier.iterrows():
        lean = bias.get(name)
        fam, sub = (agreed(name, level, first, like) for level in (0, 1))
        out[name] = {'x': round(float(r['ca1']), 5), 'y': round(float(r['ca2']), 5),
                     'wire': round(float(r['wire_axis']), 3), 'heat': round(float(r['heat_axis']), 3),
                     'wire_pct': int(wire_pct[name]), 'heat_pct': int(heat_pct[name]),
                     'family': fam, 'type': sub or fam, 'like': like[name], 'is_wire': name in WIRES,
                     'lean': None if lean is None or pd.isna(lean) else int(lean),
                     'stories': int(r['stories']), 'articles': int(r['articles']), 'beat': beat_of.get(name)}
    types = []
    for level, found in (('family', families), ('type', kinds)):
        for n, t in found.items():
            if level == 'type' and n in families:
                continue  # the same name as a family (the right partisan web is both)
            shown = sorted((o for o in t['members'] if out[o][level] == n), key=lambda o: o.removeprefix('The '))
            types.append({'name': n, 'level': level, 'stability': t['stability'], 'k': t['k'],
                          'about': ABOUT.get(n, ''), 'members': shown})
    logger.info("Outlet types: %s", ', '.join(f"{t['name']} {len(t['members'])} ({t['stability']}, k={t['k']})"
                                               for t in types) or 'none stable')
    return {'day': until.strftime('%Y-%m-%d'), 'since': (until - td(days=WINDOW_DAYS)).isoformat(timespec='minutes'),
            'until': until.isoformat(timespec='minutes'), 'window_days': WINDOW_DAYS,
            'headlines': int(len(data['heads'])), 'articles': int(len(art)), 'stories': int(X.shape[1]),
            'outlets': out, 'types': types, 'beats': beats,
            'axes': {'inertia': [round(100 * float(i), 1) for i in inertia[:2]], 'rho': rho,
                     'x': _ends(cols, 'ca1', labels), 'y': _ends(cols, 'ca2', labels),
                     'pull': {ax: _pulls(cols, X, f'ca{i}', labels, bias) for i, ax in ((1, 'x'), (2, 'y'))}}}


def agreed(outlet: str, level: int, first: dict, like: dict) -> str | None:
    """The outlet's family (level 0) or type (1), kept only when at least AGREE of the outlets it behaves most like
    share it: an outlet on a type's edge shows none (Oct 28: One America News Network clustered with the wires and
    networks while two of its three look-alikes were the right partisan web)"""
    mine = first[outlet][level]
    if mine is None:
        return None
    return mine if sum(first.get(o, (None, None))[level] == mine for o in like[outlet]) >= AGREE else None


def _type_of(outlet: str, found: dict, lean) -> str | None:
    """The smallest stable type holding the outlet. A type named for a side isn't given to an outlet rated on the
    other side or center: the profile describes behaviour and never contradicts a rating"""
    held = sorted((len(t['members']), n) for n, t in found.items() if outlet in t['members'])
    for _, n in held:
        side = SIDE.get(n)
        if side is None or lean is None or pd.isna(lean) or np.sign(lean) == side:
            return n
    return None


def _ends(cols: pd.DataFrame, axis: str, labels: pd.Series, n: int = 4) -> dict:
    """The stories that pull hardest toward each end of an axis (mass × coordinate²), by their labels"""
    contrib = cols['mass'] * cols[axis] ** 2
    out = {}
    for end, mask in (('low', cols[axis] < 0), ('high', cols[axis] > 0)):
        top = contrib[mask].sort_values(ascending=False).index
        out[end] = [str(labels[s]) for s in top if isinstance(labels.get(s), str) and labels[s].strip()][:n]
    return out


def _pulls(cols: pd.DataFrame, X: pd.DataFrame, axis: str, labels: pd.Series, bias: pd.Series, n: int = 8) -> dict:
    """The stories that pull hardest toward each end of an axis, as `_ends` but each with its id, how many of the
    profiled outlets ran it, and the share of the left-rated and of the right-rated ones that did (for the outlet
    map's lists, Oct 28: which side ran each story more)"""
    rated = bias.reindex(X.index)
    left, right = X[rated < 0], X[rated > 0]
    contrib = cols['mass'] * cols[axis] ** 2
    out = {}
    for end, mask in (('low', cols[axis] < 0), ('high', cols[axis] > 0)):
        rows = []
        for s in contrib[mask].sort_values(ascending=False).index:
            label = labels.get(s)
            if not isinstance(label, str) or not label.strip():
                continue
            rows.append({'id': int(s) if isinstance(s, (int, np.integer)) else str(s), 'label': label.strip(), 'outlets': int(X[s].sum()),
                         'left': round(float(left[s].mean()), 3) if len(left) else None,
                         'right': round(float(right[s].mean()), 3) if len(right) else None})
            if len(rows) >= n:
                break
        out[end] = rows
    return out


def profiles(refresh: bool = False, con=None, now: dt | None = None) -> dict:
    """The day's profile, from CACHE when it was made today with this method"""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    key = f"{now:%Y-%m-%d}/v{VERSION}"
    cached = read_json(CACHE, {})
    if not refresh and cached.get('key') == key:
        return cached['profile']
    started = dt.now()
    data = load(now - td(days=WINDOW_DAYS), con)
    profile = build(data, now)
    write_json(CACHE, {'key': key, 'profile': profile})
    logger.info("Outlet profiles: %d outlets, %d stories, in %.1f s", len(profile['outlets']),
                profile.get('stories', 0), (dt.now() - started).total_seconds())
    return profile
