"""The games on the Play page (Oct 28, from the newsroom probe of Oct 27): which headlines each day's puzzles use, and
the two small models that pick them.

- **Real or satire?** Five headlines a day: satire titles from the satire feeds (left- and right-leaning) among real
  front-page headlines from the same days. The hard ones are preferred: satire a word model takes for real news, real
  headlines it takes for satire. The probe found it fooled by 81% of the Onion's titles.
- **Guess the lean.** Five real headlines whose wording a second model reads with confidence (at 0.9 it was right 91%
  of the time on a held-out week): the player says which side's outlet ran it. The answer is the outlet's AllSides
  rating, never a verdict on the headline.
- **Same story, two papers.** One big story, told by a left-rated outlet and a right-rated one: the left outlet's most
  left-typical headline and the right outlet's most right-typical, as the lean model reads them.

Both models are TF-IDF and logistic regression, trained on the weeks before the puzzles' days and scored on the days
themselves, so no puzzle was in its model's training. Scraper residue ("3 hours ago", bylines glued on the end, "via
Getty", view counts) is stripped first, so the models learn wording rather than page furniture.

A day's puzzles are picked once, from a seed made of the Eastern date, and kept (`kept`), so every build that day
and every player sees the same five."""
import hashlib
import json
import os
import random
import re
from collections import Counter
from datetime import datetime, timedelta as td

import numpy as np
import pytz

from app.utils import Config, get_logger

logger = get_logger(__name__)

EASTERN = pytz.timezone('America/New_York')
AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire'}
TRAIN_DAYS = 21  # the models learn from this many days before the puzzles' window
LEAN_WINDOW = 2  # guess-the-lean headlines come from the last this many days
SATIRE_WINDOW = 3  # real-or-satire headlines, satire and real, from the last this many days
PAIR_HOURS = 30  # same story, two papers: headlines from stories on the front pages this recently
REAL_SAMPLE = 9000  # real headlines set against the satire for its model
PER_GAME = 5
VERSION = 1  # bump to pick a day's puzzles again after a change to the picking

# Scraper residue and house labels (the probe's clean.py, plus view counts)
JUNK = re.compile(r"(?:\b\d+\s*(?:hours?|hrs?|minutes?|mins?|days?)\s+ago\b|\bmin(?:ute)?s?\s+read\b|\b\d+\s+min\b|"
                  r"\bread more\b|\b(?:news|sports|business|opinion|life)?\s*comment\b|\bvia getty(?: images)?\b|"
                  r"\bgetty images\b|[-–|]\s*reuters(?:\.com)?\b|&\s*latest news\b|[-–|]\s*ap news\b|\bapnews\.com\b|"
                  r"\bscripps news group\b|\bfor subscribers\b|\((?:video|watch|photos?)\)|\bopinion\s*\||•|\.\.\.|…|"
                  r"\bupdated?\b\s*\d.*$|\bbreaking news\b|\bcnn exclusive\b|\banalysis by\b.*$|"
                  r"\b\d+(?:[.,]\d+)?\s*[KkMm]?\s+views?\b|:\s*markets wrap\b|^\d*\s*trending:)", re.I)
CAPS_KICKER = re.compile(r'^(?:[A-Z][A-Z0-9\s\'’&]{1,30}(?:\s*[:—–|]|\s{2,}))+\s*')
DESK_KICKER = re.compile(r'^(?:u\.s\.|world|national|local|business|politics) news\s+|\s+scripps$', re.I)
LABEL_KICKER = re.compile(r'^(?:(?:exclusive|watch|video|live|breaking|opinion|analysis|updated?|just in|new)'
                          r'\s*[:—–|-]\s*)+', re.I)
NAME2 = re.compile(r"^[A-Z][a-z'’\-]+ [A-Z][A-Za-z'’\-]+$")

# Not on a launch page, real or joke: violence, death, sex, drugs, slurs and identity jokes. Real news about these is
# news, but a game asking "is this a joke?" about it isn't kind.
OFFENSIVE = re.compile(
    r"\b(?:kill\w*|dead|death\w*|dies|died|dying|murder\w*|shoot\w*|shot|stab\w*|rape\w*|sexual\w*|sex|porn\w*|nude\w*|"
    r"naked|abus\w*|suicid\w*|corpse\w*|bod(?:y|ies) found|massacre\w*|genocide|terror\w*|bomb\w*|hostage\w*|"
    r"nazi\w*|hitler|holocaust|slave\w*|lynch\w*|racis\w*|n-word|retard\w*|cocaine|coke[ds]?|heroin|meth|fentanyl|"
    r"overdos\w*|drunk\w*|defecat\w*|poop\w*|shit\w*|piss\w*|fuck\w*|damn\w*|ass|asshole|bitch\w*|penis\w*|vagina\w*|"
    r"genital\w*|boob\w*|breast\w*|orgasm\w*|horny|erotic\w*|incest|pedo\w*|child(?:ren)? (?:abuse|porn)|trans|"
    r"transgender\w*|tranny|gay|lesbian\w*|queer|muslim\w*|islam\w*|jew\w*|jihad\w*|black (?:man|men|woman|women|people)|"
    r"cornrows|homeless|mental(?:ly)? ill\w*|disabled|cancer|abortion\w*|miscarr\w*|gaza|hamas|israel\w*|ukrain\w*|"
    r"war crime\w*|shooting|gunman|gunmen|gunning|firing squad|execution\w*|electrocut\w*|behead\w*|supremac\w*|"
    r"mohammed\w*|gender\w*|pronoun\w*|biological|white (?:man|men|woman|women|people)|attack\w*|assault\w*|arson\w*|"
    r"violen\w*|grave|bod(?:y|ies)|dui|cops?|prison\w*|jail\w*|bra|bras)\b", re.I)
# Not headlines, or not fair as puzzles: cartoons, slideshows, quizzes, podcasts, regular features, shopping
NOT_PUZZLE = re.compile(r"cartoon|slide ?show|^episode|crossword|\bquiz\b|horoscope|\bpodcast\b|\bnewsletter\b|"
                        r"\bwordle\b|connections hints|\bpuzzle\b|\bdeals?\b|\bsale\b|% off|coupon|\bgift guide\b|"
                        r"\bthe week in\b|\bweek in review\b|\blive updates?\b|\blive:|\bvideo\b|\bwatch\b|\bphotos?\b|"
                        r"\bopinion\b|\bexclusive\b|\beditorial\b|\bletters?\b to the editor|\binterview\b|\||\*", re.I)
FIRST_PERSON = re.compile(r"\b(?:I|I'm|I’m|I've|I’ve|me|my|we|our)\b")
STOP = set(re.findall(r'\w+', """a an the and or but of to in on at for from by with about as into over after before under than then
that this these those is are was were be been being it its he she they them his her their our we you your i me my
not no yes all any some more most less least new says said say will would could should may might can just also
how what when where who why which there here up down out off again amid via"""))


# <editor-fold desc="cleaning">
def bylines(rows: list[tuple[str, str]], min_count: int = 8, end_share: float = 0.9) -> dict[str, set[str]]:
    """outlet -> the two-word capitalized names the scraper glued on the end of its headlines (author bylines): a pair
    counts when it ends at least `min_count` of the outlet's headlines and nearly all its uses anywhere are those
    endings ("Amy Curtis" yes; "Saudi Arabia", "White House", "Senate Race" no). rows: (outlet, title)"""
    found: dict[str, set[str]] = {}
    for _ in range(2):  # twice: a byline can sit before another glued-on pair ("… Susie Moore Continue Reading")
        anywhere, ended = Counter(), Counter()
        endings: dict[str, Counter] = {}
        for outlet, title in rows:
            words = title.split()
            anywhere.update({f'{a} {b}' for a, b in zip(words, words[1:])})
            while len(words) >= 4 and ' '.join(words[-2:]) in found.get(outlet, ()):
                words = words[:-2]
            if len(words) >= 2:
                endings.setdefault(outlet, Counter())[' '.join(words[-2:])] += 1
                ended[' '.join(words[-2:])] += 1
        # a writer's name can end headlines at two outlets (Red State's and Townhall's share some): ends anywhere count
        found = {outlet: found.get(outlet, set()) | {
            pair for pair, n in ends.items()
            if n >= min_count and NAME2.match(pair) and ended[pair] / max(anywhere[pair], 1) >= end_share}
            for outlet, ends in endings.items()}
    return found


def clean(title: str, outlet: str = '', names: dict | None = None) -> str:
    """A headline without scraper residue or house labels: a glued-on byline, "3 hours ago", "via Getty", kickers
    ("WATCH:", "POLITICS |"), view counts"""
    t = ' '.join(str(title or '').split())
    glued = (names or {}).get(outlet, ())
    while glued:
        n = next((n for n in glued if t.endswith(' ' + n)), None)
        if not n:
            break
        t = t[: -len(n) - 1]
    t = JUNK.sub(' ', t)
    t = CAPS_KICKER.sub('', t)
    t = LABEL_KICKER.sub('', t)
    t = DESK_KICKER.sub('', t)
    t = re.sub(r'\s+[-–|:]\s*$', '', ' '.join(t.split()))
    return re.sub(r'^[-–|:,\s]+', '', t).strip()


def side(bias: int | None) -> str:
    return 'left' if bias < 0 else 'right' if bias > 0 else 'center'


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'’\-]+", text.lower()) if len(w) >= 4 and w not in STOP}


def fit_for_puzzle(title: str, outlets_re: re.Pattern | None = None, words: tuple = (6, 20)) -> bool:
    """A headline a puzzle can show: a sensible length, nothing offensive, not a feature, no outlet's name in it"""
    n = len(title.split())
    if not words[0] <= n <= words[1] or OFFENSIVE.search(title) or NOT_PUZZLE.search(title):
        return False
    return not (outlets_re and outlets_re.search(title))
# </editor-fold>


# <editor-fold desc="picking (pure: tested without the database)">
def rng(day: str, game: str) -> random.Random:
    """The day's dice for one game: the same date always rolls the same"""
    return random.Random(int(hashlib.sha1(f'{day}:{game}:{VERSION}'.encode()).hexdigest()[:12], 16))


def apart(x: dict, picked: list[dict]) -> bool:
    """`x` can join `picked`: another outlet, another story, and not two words that matter in common with any (a day's
    five shouldn't be three takes on one row)"""
    for p in picked:
        if x['outlet'] == p['outlet'] or x['title'] == p['title']:
            return False
        if x.get('story') is not None and x.get('story') == p.get('story'):
            return False
        if len(content_words(x['title']) & content_words(p['title'])) >= 2:
            return False
    return True


def pick_real_or_satire(satire: list[dict], real: list[dict], day: str, n: int = PER_GAME) -> list[dict]:
    """The day's real-or-satire puzzles. satire: [{title, outlet, group (left, right or center), p, ...}], real:
    [{title, outlet, p, ...}], p being the model's chance it's satire. Two or three are satire (the day's dice say
    which), with a right-leaning and a left-leaning source among them where both have any; the hardest are preferred
    (satire the model calls real, real it calls satire), drawn from the hardest few so days differ."""
    r = rng(day, 'satire')
    k = min(r.choice((2, 3)), len(satire))
    picked = []

    def draw(hardest_first: list[dict], size: int, kind: str) -> bool:
        options = [x for x in hardest_first if apart(x, picked)][:size]
        if options:
            picked.append({**r.choice(options), 'kind': kind})
        return bool(options)

    sat = sorted(satire, key=lambda x: (x['p'], x['title']))  # most real-looking first
    right = [x for x in sat if x.get('group') == 'right']
    left = [x for x in sat if x.get('group') != 'right']
    for pool in ([right, left] if r.random() < 0.5 else [left, right]):
        if len(picked) < k:
            draw(pool, 4, 'satire')
    while len(picked) < k and draw(sat, 6, 'satire'):
        pass
    hard_real = sorted(real, key=lambda x: (-x['p'], x['title']))  # most satire-looking first
    while len(picked) < n and draw(hard_real, 8, 'real'):
        pass
    r.shuffle(picked)
    return picked


def pick_lean(cands: list[dict], day: str, n: int = PER_GAME, min_conf: float = 0.85) -> list[dict]:
    """The day's guess-the-lean puzzles: headlines the model reads confidently and rightly (cands: [{title, outlet,
    side, guess, conf, ...}]), a mix of sides (two of two sides and one of the third, the day's dice say which). An
    outlet is drawn first, then one of its surest headlines: else a few house styles (Bloomberg's, the Daily Beast's)
    would fill every day."""
    r = rng(day, 'lean')
    sure = sorted((c for c in cands if c['conf'] >= min_conf and c['guess'] == c['side']),
                  key=lambda c: (-c['conf'], c['title']))
    counts = r.choice(({'left': 2, 'center': 1, 'right': 2}, {'left': 2, 'center': 2, 'right': 1},
                       {'left': 1, 'center': 2, 'right': 2}))
    picked = []
    for s in ('left', 'center', 'right'):
        by_outlet: dict[str, list[dict]] = {}
        for c in sure:
            if c['side'] == s:
                by_outlet.setdefault(c['outlet'], []).append(c)
        outlets = sorted(by_outlet)
        r.shuffle(outlets)
        wanted = len(picked) + counts[s]
        for o in outlets:
            if len(picked) >= wanted:
                break
            options = [c for c in by_outlet[o] if apart(c, picked)][:5]
            if options:
                picked.append(r.choice(options))
    for c in sure:  # a side short of headlines: the rest from any side
        if len(picked) >= n:
            break
        if apart(c, picked):
            picked.append(c)
    picked = picked[:n]
    r.shuffle(picked)
    return picked


def best_pair(stories: list[dict]) -> dict | None:
    """Same story, two papers: of the biggest stories (stories: [{id, label, outlets, headlines: [{title, outlet,
    side, tilt, ...}]}], tilt being the lean model's p(right) - p(left)), the one whose left-rated outlet's most
    left-typical headline and right-rated outlet's most right-typical one are furthest apart, among pairs that share a
    word that matters (a pair with nothing in common is often about different events in one story)"""
    best = None
    for st in sorted(stories, key=lambda s: (-s['outlets'], s['id']))[:6]:
        lefts = sorted((h for h in st['headlines'] if h['side'] == 'left'), key=lambda h: (h['tilt'], h['title']))
        rights = sorted((h for h in st['headlines'] if h['side'] == 'right'), key=lambda h: (-h['tilt'], h['title']))
        for left in lefts[:4]:
            right = next((h for h in rights[:4] if content_words(left['title']) & content_words(h['title'])), None)
            if not right:
                continue
            gap = right['tilt'] - left['tilt']
            if best is None or gap > best['gap']:
                best = {'story': st['id'], 'label': st['label'], 'outlets': st['outlets'], 'left': left,
                        'right': right, 'gap': round(float(gap), 3)}
            break
    return best


def score(kinds: list[str], answers: list[str]) -> dict:
    """A round's score. For real or satire, both kinds of right answer count (calling satire satire and real news
    real), so calling everything "satire" scores no better than calling everything real. The page's script counts the
    same way (its score(), checked against this one in tests/test_play.py)."""
    sat = [a == 'satire' for k, a in zip(kinds, answers) if k == 'satire']
    real = [a == 'real' for k, a in zip(kinds, answers) if k == 'real']
    return {'satire_hits': sum(sat), 'satire': len(sat), 'real_hits': sum(real), 'real': len(real),
            'right': sum(k == a for k, a in zip(kinds, answers)), 'of': len(kinds),
            'grid': ''.join('🟩' if k == a else '🟥' for k, a in zip(kinds, answers))}


# </editor-fold>


# <editor-fold desc="the models">
def lean_model():
    """Logistic regression fitted by stochastic gradient descent: on Oct 28's preview data it fitted 100k headlines in
    0.9 s against 26 s for the probe's solver, with the same accuracy on the next week (62.6% against 62.3%), and at
    0.85 confidence it covered 17% of headlines at 91% precision (25% at 87%)"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import SGDClassifier
    from sklearn.pipeline import make_pipeline
    return make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, dtype=np.float32,
                                         token_pattern=r"(?u)\b[\w'’]+\b"),
                         SGDClassifier(loss='log_loss', alpha=2e-6, max_iter=20, tol=None, random_state=0))


def satire_model():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union
    return make_pipeline(make_union(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, dtype=np.float32),
                                    TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), min_df=3, sublinear_tf=True,
                                                    dtype=np.float32)),
                         LogisticRegression(max_iter=500, C=4.0, class_weight='balanced'))
# </editor-fold>


# <editor-fold desc="the data">
def eastern_day(t: datetime) -> str:
    return pytz.UTC.localize(t).astimezone(EASTERN).strftime('%Y-%m-%d')


def latest() -> datetime | None:
    """The newest headline's time (UTC): the puzzles' "now", so a preview of old data gets that day's puzzles"""
    from sqlalchemy import text
    from app.models import engine
    with engine.connect() as c:
        t = c.execute(text('select max(first_accessed) from headline')).scalar()
    return datetime.fromisoformat(str(t)) if t else None


def headlines(since: datetime, until: datetime):
    """Headlines from rated and unrated outlets (aggregators left out) first seen in [since, until), one per outlet
    and wording, cleaned, with the story each is in (if any)"""
    import pandas as pd
    from app.models import engine
    df = pd.read_sql(
        '''select h.id, h.title, h.first_accessed, h.news_score, ar.url, ag.name outlet, ag._bias bias,
                  ag.lean_rated rated, ag.lean_url lean_url,
                  (select max(sh.story_id) from story_headline sh where sh.headline_id = h.id) story
           from headline h join article ar on ar.id = h.article_id join agency ag on ag.id = ar.agency_id
           where h.first_accessed >= :since and h.first_accessed < :until''', engine,
        params={'since': str(since), 'until': str(until)})
    df = df[~df['outlet'].isin(AGGREGATORS)].copy()
    df['t'] = pd.to_datetime(df['first_accessed'], format='mixed')
    df['raw'] = df['title'].astype(str).str.split().str.join(' ')
    df = df.assign(_k=df['raw'].str.lower()).sort_values('t').drop_duplicates(['outlet', '_k']).drop(columns='_k')
    return df


def satire_items(since: datetime, until: datetime) -> list[dict]:
    from app import sidefeeds
    from app.models import Session, SideItem
    keys = {s['key']: s for s in sidefeeds.SOURCES if s['kind'] == 'satire'}
    with Session() as s:
        rows = s.query(SideItem.source, SideItem.title, SideItem.url, SideItem.published, SideItem.first_seen) \
            .filter(SideItem.source.in_(list(keys)), SideItem.first_seen >= since - td(days=2),
                    SideItem.first_seen < until).all()
    out, seen = [], set()
    for source, title, url, published, first in rows:
        when = published or first
        title = ' '.join((title or '').split())
        if not since <= when < until or title.lower() in seen:
            continue
        seen.add(title.lower())
        out.append({'title': title, 'url': url, 'outlet': keys[source]['name'], 'group': keys[source]['group'],
                    'when': when})
    return sorted(out, key=lambda x: (x['when'], x['title']))


def outlet_names_re(names) -> re.Pattern:
    words = [re.escape(n.lower()) for n in names if len(n) > 3]
    return re.compile('|'.join(words + [r'\bfox\b', r'\bcnn\b', r'\bmsnbc\b', r'\bnpr\b', r'\bbbc\b', r'\bap\b']), re.I)


def story_pages() -> set[int]:
    """Stories with a page this build (page_story: seen in the last week, or kept in its archive)"""
    from sqlalchemy import text
    from app.models import engine
    from app.site.page_story import DAYS, archived_ids
    since = datetime.utcnow() - td(days=DAYS)
    with engine.connect() as c:
        ids = {i for (i,) in c.execute(text('select id from story where last_seen >= :s'), {'s': str(since)})}
    return ids | archived_ids()
# </editor-fold>


def cache_dir() -> str:
    return os.path.join(Config.data, 'play')


def kept(kind: str, day: str) -> str:
    """The day's kept puzzles (json) or lean model (pkl)"""
    return os.path.join(cache_dir(), f"{kind}-{day}-v{VERSION}.{'json' if kind == 'puzzles' else 'pkl'}")


def keep(kind: str, day: str, write):
    """Write the day's file, and drop earlier days' of its kind"""
    os.makedirs(cache_dir(), exist_ok=True)
    for name in os.listdir(cache_dir()):
        if name.startswith(kind + '-'):
            os.remove(os.path.join(cache_dir(), name))
    with open(kept(kind, day), 'wb') as f:
        write(f)


def cleaned(df, names: dict):
    df = df.assign(title=[clean(t, o, names) for t, o in zip(df['raw'], df['outlet'])])
    df = df[df['title'].str.split().str.len() >= 3].copy()
    df['side'] = [side(b) if r else None for b, r in zip(df['bias'], df['rated'])]
    return df


def build(now: datetime | None = None) -> dict:
    """Everything the Play page shows: {day, satire: [...], lean: [...], pair: {...} or None}. The day's two games and
    its lean model are made at the day's first build and kept (that build takes ~20 s; Oct 28, preview data); later
    builds that day only pick the pair again, as the day's stories grow (a few seconds)."""
    import pickle
    import time
    t0 = time.time()
    now = now or latest()
    if now is None:
        return {'day': None, 'satire': [], 'lean': [], 'pair': None}
    day = eastern_day(now)
    games = model = None
    if os.path.exists(kept('puzzles', day)) and os.path.exists(kept('model', day)):
        with open(kept('puzzles', day), encoding='utf-8') as f:
            games = json.load(f)
        with open(kept('model', day), 'rb') as f:
            model = pickle.load(f)  # our own file, written below
    pages = story_pages()
    if model is None:
        df = headlines(now - td(days=TRAIN_DAYS + SATIRE_WINDOW), now + td(minutes=1))
        names = bylines(list(zip(df['outlet'], df['raw'])))
        df = cleaned(df, names)
        rated = df[df['rated'] == 1]
        train = rated[rated['t'] < now - td(days=LEAN_WINDOW)]
        lean = lean_model().fit(train['title'], train['side'])
        logger.info("Play: lean model on %d headlines in %.1fs", len(train), time.time() - t0)
        model = {'names': names, 'lean': lean}
        out_re = outlet_names_re(df['outlet'].unique())
        games = {'day': day, 'satire': satire_game(df, now, day, pages, out_re),
                 'lean': lean_game(rated, lean, now, day, pages, out_re)}
        keep('puzzles', day, lambda f: f.write(json.dumps(games, ensure_ascii=False, indent=1, default=str).encode()))
        keep('model', day, lambda f: pickle.dump(model, f))
    else:
        rated = cleaned(headlines(now - td(hours=PAIR_HOURS), now + td(minutes=1)), model['names'])
        rated = rated[rated['rated'] == 1]
    games['pair'] = pair_now(rated, model['lean'], now, pages)
    logger.info("Play: %d satire puzzles, %d lean puzzles, pair %s, in %.1fs", len(games['satire']),
                len(games['lean']), bool(games['pair']), time.time() - t0)
    return games


def tilt(model, titles) -> np.ndarray:
    """The lean model's p(right) - p(left) for each title: below 0 reads left-typical, above 0 right-typical"""
    P = model.predict_proba(list(titles))
    classes = list(model.classes_)
    return P[:, classes.index('right')] - P[:, classes.index('left')]


def story_id(value) -> int | None:
    """A story id from a pandas cell (NaN where the headline is in no story)"""
    return None if value is None or value != value else int(value)


def link(row, pages: set[int]) -> str:
    """Where a puzzle's reveal links: the story's page where it has one, else the outlet's own article"""
    st = story_id(row.get('story'))
    if st is not None and st in pages:
        return f'story-{st}.html'
    return row.get('url') or ''


def satire_game(df, now: datetime, day: str, pages: set[int], out_re) -> list[dict]:
    since = now - td(days=SATIRE_WINDOW)
    sat = satire_items(now - td(days=TRAIN_DAYS + SATIRE_WINDOW), now + td(minutes=1))
    train_sat = [s['title'] for s in sat if s['when'] < since and not NOT_PUZZLE.search(s['title'])]
    recent_sat = [s for s in sat if s['when'] >= since and fit_for_puzzle(s['title'], words=(5, 22))]
    if len(train_sat) < 50 or not recent_sat:
        logger.info("Play: too little satire for the game (%d to learn from, %d recent)", len(train_sat), len(recent_sat))
        return []
    older = df[df['t'] < since]
    older = older.sample(min(REAL_SAMPLE, len(older)), random_state=1)
    model = satire_model()
    model.fit(list(older['title']) + train_sat, [0] * len(older) + [1] * len(train_sat))
    for s, p in zip(recent_sat, model.predict_proba([s['title'] for s in recent_sat])[:, 1]):
        s['p'] = float(p)
    # Real headlines from news reports (not opinion) by center, leaning or unrated outlets, none in the first person:
    # the most satire-looking headlines from the strongly partisan outlets are mostly outrage pieces about named
    # people, and a game built on them would mock one side's press rather than test reading
    recent = df[(df['t'] >= since) & (df['news_score'].fillna(0) >= 0.5) & ((df['rated'] == 0) | (df['bias'].abs() <= 1))]
    recent = recent[[fit_for_puzzle(t, out_re) and not FIRST_PERSON.search(t) for t in recent['title']]]
    recent = recent.assign(p=model.predict_proba(recent['title'])[:, 1])
    real = [{'title': r['title'], 'outlet': r['outlet'], 'p': float(r['p']), 'link': link(r, pages),
             'story': story_id(r['story']),
             'url': r['url'], 'bias': int(r['bias']) if r['rated'] else None,
             'when': r['t'].to_pydatetime()} for r in recent.sort_values('p', ascending=False).head(60).to_dict('records')]
    for s in recent_sat:
        s['link'] = s['url']
    picked = pick_real_or_satire(recent_sat, real, day)
    return [{'title': x['title'], 'kind': x['kind'], 'outlet': x['outlet'], 'link': x['link'],
             'group': x.get('group'), 'bias': x.get('bias'), 'p': round(x['p'], 3),
             'when': EASTERN.normalize(pytz.UTC.localize(x['when']).astimezone(EASTERN)).strftime('%b %-d')}
            for x in picked]


def lean_game(rated, model, now: datetime, day: str, pages: set[int], out_re) -> list[dict]:
    recent = rated[(rated['t'] >= now - td(days=LEAN_WINDOW)) & (rated['news_score'].fillna(0) >= 0.5)
                   & ((rated['bias'].abs() == 2) | (rated['bias'] == 0))]
    recent = recent[[fit_for_puzzle(t, out_re, (7, 18)) for t in recent['title']]]
    if recent.empty:
        return []
    P = model.predict_proba(recent['title'])
    recent = recent.assign(guess=np.array(model.classes_)[P.argmax(1)], conf=P.max(1))
    cands = [{'title': r['title'], 'outlet': r['outlet'], 'side': r['side'], 'bias': int(r['bias']),
              'guess': r['guess'], 'conf': float(r['conf']), 'story': story_id(r['story']), 'url': r['url'],
              'lean_url': r['lean_url'], 'id': int(r['id'])} for r in recent.to_dict('records')]
    picked = pick_lean(cands, day)
    out = []
    for c in picked:
        other = other_side(rated, model, c)
        out.append({'title': c['title'], 'outlet': c['outlet'], 'side': c['side'], 'bias': c['bias'],
                    'conf': round(c['conf'], 3), 'link': link(c, pages), 'url': c['url'],
                    'lean_url': c['lean_url'] or '', 'other': other})
    return out


def other_side(rated, model, c: dict) -> list[dict]:
    """The same story's headline from the other side: a right-rated outlet's for a left one, and so on; a center
    outlet's story gets one from each side. The most typical of its side, as the model reads it."""
    st = c.get('story')
    if st is None:
        return []
    same = rated[(rated['story'] == st) & (rated['outlet'] != c['outlet'])]
    if same.empty:
        return []
    same = same.assign(tilt=tilt(model, same['title']))
    wanted = {'left': ['right'], 'right': ['left'], 'center': ['left', 'right']}[c['side']]
    out = []
    for s in wanted:
        rows = same[same['side'] == s].sort_values('tilt', ascending=(s == 'left'))
        rows = rows[[not OFFENSIVE.search(t) for t in rows['title']]]
        if not rows.empty:
            r = rows.iloc[0]
            out.append({'title': r['title'], 'outlet': r['outlet'], 'side': s, 'bias': int(r['bias'])})
    return out


def pair_now(rated, model, now: datetime, pages: set[int]) -> dict | None:
    recent = rated[(rated['t'] >= now - td(hours=PAIR_HOURS)) & rated['story'].notna()]
    if recent.empty:
        return None
    from sqlalchemy import text
    from app.models import engine
    ids = sorted({int(s) for s in recent['story']})
    with engine.connect() as c:
        labels = dict(c.execute(text(f"select id, label from story where id in ({','.join(map(str, ids))})")).all())
    recent = recent.assign(tilt=tilt(model, recent['title']))
    stories = []
    for sid, g in recent.groupby('story'):
        sid = int(sid)
        if not labels.get(sid):
            continue
        hs = [{'title': r['title'], 'outlet': r['outlet'], 'side': r['side'], 'bias': int(r['bias']),
               'tilt': round(float(r['tilt']), 3), 'url': r['url']}
              for r in g.to_dict('records') if len(r['title'].split()) >= 5]
        stories.append({'id': sid, 'label': labels[sid], 'outlets': int(g['outlet'].nunique()), 'headlines': hs})
    pair = best_pair(stories)
    if pair:
        pair['link'] = f"story-{pair['story']}.html" if pair['story'] in pages else ''
    return pair
