"""O1 the Wolf in Sheep's Clothing: does an outlet run a ton of straight news to cover a small, separate tail of
ideological framing? (Oct 28; the person: "Within news agencies can we identify if they have like a barbell strategy
of running a ton of straight news to cover for some insanely heterodox bullshit? ... I could conceive of OANN running
wire service basically and then publishing 2% of its headlines as straight propaganda.") The wolf wears the fleece of
the flock: most of what you see is sheep.

Gemma 4 26B reads each article's first headline, blind to the outlet, and gives it a kind (report, opinion, other) and
a slant, 0 (straight, as a wire would write it) to 4 (propaganda or fringe). For each outlet, two models of its slants:

    one shifted mode   an ordered probit on a latent slant, the cut lines and the spread shared by every outlet, the
                       outlet's own centre (mu): the common shape slid along the scale toward heat
    a barbell          the same, plus a separate tail at slant 3-4 holding a share w of its headlines

w (the tail mixture share), its bootstrap interval and a likelihood-ratio test of w = 0 (Holm-corrected over the
outlets) say whether an outlet's tail is more than its bell slid toward heat; an outlet is a barbell when that tail is
real and its bell sits at straight (mode at slant 0). Run on everything it ran (reports and opinion) and on reports
only (the tail dressed as news).

The paper is ~/maudlin-data/papers/the-wolf-in-sheeps-clothing.md (hypotheses and the test written before the run);
the data is motifs/experiments/o1_wolf.sqlite. A rerun with other outlets (Sinclair's stations, when we follow them)
needs nothing but the outlet list: `sample --outlets ...`, or the default rule (US, not an aggregator, MIN_ARTICLES in
the window) picks them up; GROUPS pools outlets (an owner's stations) into one more row.

    o1_wolf.py sample [--days 30] [--cap 400] [--outlets A,B]   CPU: freeze the headline set and draw the hand sample
    o1_wolf.py hand FILE                                        the hand labels (tsv: hid, kind, slant, side) in
    o1_wolf.py trial                                            GPU: the model on the hand sample; agreement, gate
    o1_wolf.py label                                            GPU: the model on the set, if the gate passed; resumes
    o1_wolf.py report                                           CPU: the fits, intervals, tails, into the paper"""
import argparse
import hashlib
import json
import os
import random
import sqlite3
import subprocess
import sys
import time
from datetime import datetime as dt, timedelta as td

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from app.utils import Config  # noqa: E402

DB = os.path.join(Config.data, 'motifs', 'experiments', 'o1_wolf.sqlite')
PAPER = os.path.join(Config.data, 'papers', 'the-wolf-in-sheeps-clothing.md')
MODEL = os.environ.get('MAUDLIN_MODEL_BIG') or 'gemma4:26b'  # the house labeller (local_models.BIG)
DAYS = 30
CAP = 400  # headlines per outlet, drawn at random; an outlet with fewer gives all it has
MIN_ARTICLES = 150  # in the window, for an outlet to be drawn by the default rule
MIN_TESTED = 150  # labelled headlines of a variant for an outlet to be tested
AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire', 'Memeorandum'}
EXTRA = {'Reuters'}  # outside the US but needed: the second wire, a control
CONTROLS = ('AP', 'Reuters')
GROUPS: dict[str, list[str]] = {}  # name -> outlets pooled into one more row (e.g. an owner's local stations)
SEED = 28
HAND_N = 120
BOOTS = 500
LEVEL = 0.05
MATERIAL = 0.01  # a tail share below this isn't a barbell even if it's real
GATE = {'slant_wkappa': 0.5, 'tail_kappa': 0.4, 'kind_kappa': 0.5}  # the model must reach all three on the hand sample
CHUNK = 40
WORKERS = 4

KINDS = ['report', 'opinion', 'other']
SIDES = ['right', 'left', 'none']
PROMPT = """You are reading one headline from a news outlet's front page. Judge only the headline's own words; you are \
not told which outlet it is.

kind:
- report: reports an event, statement, finding or development as news, however dramatic ("Strike kills 12 in \
Gaza", "Senate passes funding bill", "Trump says he will fire the Fed chair")
- opinion: the outlet's own opinion, column, analysis or commentary: it argues a point, gives a verdict, or asks a \
rhetorical question ("Democrats' priorities endanger the nation", "Why the Fed is wrong", "The case for a wealth \
tax")
- other: sport, lifestyle, celebrity, entertainment, weather, consumer advice, puzzles, not a headline

note: in under 12 words, what the headline asserts or implies beyond the bare facts, or "nothing".

slant: how far the headline's own framing pushes an ideological line, whichever side, 0 to 4. Dramatic events \
reported plainly are 0. Words quoted from a source count only when the headline adopts them as its own.
0: straight: the facts in neutral words, as a wire service would write them ("Judge blocks Texas immigration law", \
"Hamas releases three hostages", "Gunman kills four at mall")
1: a slight lean: one charged word, or an emphasis that favours a side ("Trump slams judge over ruling", "GOP \
blocks bill to lower drug prices")
2: clear slant: the framing takes a side, on a mainstream claim ("Biden's border chaos deepens", "Republicans' \
cruel cuts hit children")
3: strong one-sided framing: loaded labels for opponents, a contested claim stated as fact, outrage built in \
("Radical left judge unleashes illegals on Texas", "MAGA extremists plot to end democracy")
4: propaganda or fringe: conspiracy, culture-war panic, dehumanizing labels, or claims far outside mainstream \
reporting ("Globalists' plan to replace Americans is working", "Vaccines are killing millions, data shows", \
"Christian nationalists are building camps for gay people")

side: whose line the framing favours: right, left or none (none when slant is 0).

Headline: {title}"""
SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": KINDS},
        "note": {"type": "string", "maxLength": 100},  # written before the slant, it steers it
        "slant": {"type": "integer", "enum": [0, 1, 2, 3, 4]},
        "side": {"type": "string", "enum": SIDES},
    },
    "required": ["kind", "note", "slant", "side"],
    "additionalProperties": False,
}
PROMPT_ID = hashlib.sha1((PROMPT + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:10]

SCHEMA_SQL = """
create table if not exists runs (id text primary key, stage text, at text, git_commit text, model text, prompt text,
    notes text);
create table if not exists headlines (hid integer, sample text, aid integer, outlet text, title text, seen text,
    rank integer, primary key (sample, hid));
create table if not exists hand (hid integer primary key, outlet text, title text, kind text, slant integer,
    side text, by text, at text);
create table if not exists labels (hid integer, model text, prompt text, kind text, note text, slant integer,
    side text, seconds real, at text, primary key (hid, model, prompt));
create table if not exists agreement (run text, measure text, value real, n integer, primary key (run, measure));
create table if not exists results (run text, variant text, outlet text, n integer, straight real, middle real,
    tail real, top real, opinion real, mean real, mu real, w real, w_lo real, w_hi real, lr real, p real, p_holm real,
    bell_mode integer, valley real, tail_right real, tail_left real, verdict text, primary key (run, variant, outlet));
create table if not exists shape (run text, variant text, c2 real, c3 real, c4 real, q real, primary key (run, variant));
"""


def connect(path: str = DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, timeout=60)
    con.executescript(SCHEMA_SQL)
    return con


def now() -> str:
    return dt.now().isoformat(timespec='seconds')


def new_run(con, stage: str, notes: str = '') -> str:
    commit = subprocess.run(['git', '-C', HERE, 'rev-parse', '--short', 'HEAD'], capture_output=True,
                            text=True).stdout.strip()
    rid = f'O1:{stage}:{now()}'
    con.execute('insert into runs values (?, ?, ?, ?, ?, ?, ?)', (rid, stage, now(), commit, MODEL, PROMPT_ID, notes))
    con.commit()
    return rid


# ---- the shape: one shifted mode, or a bell plus a tail ----

def _ncdf(x):
    from scipy.stats import norm
    return norm.cdf(x)


def cuts_of(theta) -> np.ndarray:
    """The four cut lines from three free numbers: the first at 0 (the latent's origin), the rest spaced positively"""
    a, b, c = theta
    return np.array([0.0, np.exp(a), np.exp(a) + np.exp(b), np.exp(a) + np.exp(b) + np.exp(c)])


def bell(mu: float, cuts: np.ndarray) -> np.ndarray:
    """P(slant = 0..4) for a latent N(mu, 1) cut at `cuts`"""
    edges = np.concatenate([[-np.inf], cuts, [np.inf]])
    p = np.diff(_ncdf(edges - mu))
    return np.clip(p, 1e-12, 1)


def mixture(mu: float, w: float, cuts: np.ndarray, q: float) -> np.ndarray:
    """The bell with a share w moved to a separate tail, split q : 1 - q between slants 3 and 4"""
    return (1 - w) * bell(mu, cuts) + w * np.array([0, 0, 0, q, 1 - q]) + 1e-12


def loglik(counts: np.ndarray, p: np.ndarray) -> float:
    return float(np.sum(counts * np.log(p)))


def fit_bell(counts: np.ndarray, cuts: np.ndarray) -> tuple[float, float]:
    """(mu, log-likelihood) of one shifted mode"""
    from scipy.optimize import minimize_scalar
    r = minimize_scalar(lambda m: -loglik(counts, bell(m, cuts)), bounds=(-8, 12), method='bounded')
    return float(r.x), -float(r.fun)


def fit_mixture(counts: np.ndarray, cuts: np.ndarray, q: float) -> tuple[float, float, float]:
    """(mu, w, log-likelihood) of the bell plus a tail, w in [0, 0.5]"""
    from scipy.optimize import minimize
    mu0, ll0 = fit_bell(counts, cuts)
    best = (mu0, 0.0, ll0)
    for w0 in (0.01, 0.05, 0.15):
        r = minimize(lambda x: -loglik(counts, mixture(x[0], x[1], cuts, q)), x0=[mu0, w0],
                     bounds=[(-8, 12), (0, 0.5)], method='L-BFGS-B')
        if -r.fun > best[2]:
            best = (float(r.x[0]), float(r.x[1]), -float(r.fun))
    return best


def fit_shape(table: dict[str, np.ndarray]) -> tuple[np.ndarray, float]:
    """The cut lines shared by every outlet (one shifted mode each, fitted together) and the tail's split q (the
    share of slant 3 among every outlet's 3s and 4s)"""
    from scipy.optimize import minimize
    rows = list(table.values())

    def nll(theta):
        cuts = cuts_of(theta)
        return -sum(fit_bell(c, cuts)[1] for c in rows)
    r = minimize(nll, x0=[np.log(0.8), np.log(0.8), np.log(0.8)], method='Nelder-Mead',
                 options={'xatol': 1e-3, 'fatol': 1e-2, 'maxiter': 400})
    pooled = np.sum(rows, axis=0)
    q = float(pooled[3] / max(pooled[3] + pooled[4], 1))
    return cuts_of(r.x), q


def lr_p(lr: float) -> float:
    """p of the likelihood ratio for w = 0, on the boundary: half chi-square(0), half chi-square(1) (Self and Liang)"""
    from scipy.stats import chi2
    return 1.0 if lr <= 0 else float(0.5 * chi2.sf(lr, 1))


def holm(ps: list[float]) -> list[float]:
    """Holm's step-down adjusted p values, in the input's order"""
    order = np.argsort(ps)
    m = len(ps)
    out = np.empty(m)
    run = 0.0
    for i, j in enumerate(order):
        run = max(run, min(1.0, (m - i) * ps[j]))
        out[j] = run
    return out.tolist()


def valley(p) -> float:
    """How deep the pmf's deepest dip is below the lower of its highest points on either side (> 0: two modes)"""
    p = np.asarray(p, float)
    return max([min(p[:k].max(), p[k + 1:].max()) - p[k] for k in range(1, len(p) - 1)] + [0.0]) if len(p) > 2 else 0.0


def boot_w(counts: np.ndarray, cuts: np.ndarray, q: float, boots: int, rng) -> tuple[float, float]:
    """The 95% interval of w over the outlet's headlines drawn again with replacement (the shape held fixed)"""
    n = int(counts.sum())
    p = counts / n
    ws = [fit_mixture(rng.multinomial(n, p).astype(float), cuts, q)[1] for _ in range(boots)]
    return float(np.percentile(ws, 2.5)), float(np.percentile(ws, 97.5))


def counts_of(slants) -> np.ndarray:
    return np.bincount(np.asarray(slants, int), minlength=5)[:5].astype(float)


def verdict(row: dict) -> str:
    """barbell, one shifted mode (a tail no more than its bell slid toward heat), heat (a bell away from straight),
    can't tell (a tail that might be there), or too few"""
    if row['n'] < MIN_TESTED:
        return 'too few'
    tail_real = row['w_lo'] > 0 and row['p_holm'] < LEVEL and row['w'] >= MATERIAL
    if row['bell_mode'] != 0:
        return 'heat' + (' with a tail' if tail_real else '')
    if tail_real:
        return 'barbell'
    if row['w_hi'] < MATERIAL:
        return 'one shifted mode'
    return "can't tell"


def analyse(labelled: dict[str, list[dict]], boots: int | None = None, seed: int = SEED) -> tuple[list[dict], dict]:
    """Per outlet, from its labelled headlines ({'kind', 'slant', 'side'}) of one variant: shares, the two fits, w's
    interval, the test; and the shared shape"""
    rng = np.random.default_rng(seed)
    boots = boots or BOOTS
    table = {o: counts_of([h['slant'] for h in hs]) for o, hs in labelled.items() if len(hs) >= MIN_TESTED}
    if not table:
        return [], {}
    cuts, q = fit_shape(table)
    rows = []
    for o, hs in labelled.items():
        c = counts_of([h['slant'] for h in hs])
        n = int(c.sum())
        row = {'outlet': o, 'n': n}
        if n:
            p = c / n
            tail = [h for h in hs if h['slant'] >= 3]
            row.update(straight=p[0], middle=p[1] + p[2], tail=p[3] + p[4], top=p[4],
                       opinion=np.mean([h['kind'] == 'opinion' for h in hs]), mean=float(np.dot(p, range(5))),
                       valley=valley(p),
                       tail_right=np.mean([h['side'] == 'right' for h in tail]) if tail else 0.0,
                       tail_left=np.mean([h['side'] == 'left' for h in tail]) if tail else 0.0)
        if n >= MIN_TESTED:
            mu0, ll0 = fit_bell(c, cuts)
            mu, w, ll1 = fit_mixture(c, cuts, q)
            lo, hi = boot_w(c, cuts, q, boots, rng)
            lr = max(0.0, 2 * (ll1 - ll0))
            row.update(mu=mu, w=w, w_lo=lo, w_hi=hi, lr=lr, p=lr_p(lr),
                       bell_mode=int(np.argmax(bell(mu, cuts))))
        rows.append(row)
    tested = [r for r in rows if 'p' in r]
    for r, ph in zip(tested, holm([r['p'] for r in tested])):
        r['p_holm'] = ph
    for r in rows:
        r['verdict'] = verdict(r) if 'p' in r else 'too few'
    return rows, {'c2': cuts[1], 'c3': cuts[2], 'c4': cuts[3], 'q': q}


# ---- agreement ----

def kappa(a: list, b: list, weights: str | None = None, levels: list | None = None) -> float:
    """Cohen's kappa of two raters' labels; weights 'quadratic' for ordered levels"""
    levels = levels or sorted(set(a) | set(b))
    k = len(levels)
    ix = {v: i for i, v in enumerate(levels)}
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[ix[x], ix[y]] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(1), obs.sum(0))
    if weights == 'quadratic':
        wt = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)], float) / max((k - 1) ** 2, 1)
    else:
        wt = 1 - np.eye(k)
    den = (wt * exp).sum()
    return float(1 - (wt * obs).sum() / den) if den else 1.0


def agreement(pairs: list[tuple[dict, dict]]) -> dict[str, float]:
    """The model against the hand labels: kind, slant, the tail (3-4) and straight (0) as yes or no"""
    h = [p[0] for p in pairs]
    m = [p[1] for p in pairs]
    hs, ms = [x['slant'] for x in h], [x['slant'] for x in m]
    return {
        'n': len(pairs),
        'kind_accuracy': float(np.mean([x['kind'] == y['kind'] for x, y in pairs])),
        'kind_kappa': kappa([x['kind'] for x in h], [x['kind'] for x in m], levels=KINDS),
        'slant_exact': float(np.mean([x == y for x, y in zip(hs, ms)])),
        'slant_within_one': float(np.mean([abs(x - y) <= 1 for x, y in zip(hs, ms)])),
        'slant_wkappa': kappa(hs, ms, 'quadratic', levels=list(range(5))),
        'tail_kappa': kappa([x >= 3 for x in hs], [x >= 3 for x in ms], levels=[False, True]),
        'straight_kappa': kappa([x == 0 for x in hs], [x == 0 for x in ms], levels=[False, True]),
        'tail_hand': float(np.mean([x >= 3 for x in hs])), 'tail_model': float(np.mean([x >= 3 for x in ms])),
    }


def gate_passes(a: dict) -> bool:
    return all(a.get(k, 0) >= v for k, v in GATE.items())


# ---- the paper ----

def replace_section(text: str, name: str, body: str) -> str:
    """The text between <!-- wolf:NAME --> and <!-- /wolf:NAME --> replaced by body (markers kept)"""
    start, end = f'<!-- wolf:{name} -->', f'<!-- /wolf:{name} -->'
    if start not in text or end not in text:
        raise ValueError(f'the paper has no {name} section')
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return f'{head}{start}\n{body.strip()}\n{end}{tail}'


def write_section(name: str, body: str, path: str | None = None):
    path = path or PAPER
    with open(path) as f:
        text = f.read()
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(replace_section(text, name, body))
    os.replace(tmp, path)


# ---- the set ----

def outlets_by_rule(arts, min_articles: int = MIN_ARTICLES) -> list[str]:
    """US outlets (and EXTRA) that aren't aggregators, with min_articles in the window"""
    n = arts.groupby('outlet').size()
    keep = arts.drop_duplicates('outlet').set_index('outlet')
    return sorted(o for o, k in n.items() if k >= min_articles and o not in AGGREGATORS
                  and (keep.loc[o, 'country'] == 0 or o in EXTRA))


def round_robin(hids_by_outlet: dict[str, list[int]], cap: int, seed: int = SEED) -> list[tuple[str, int, int]]:
    """(outlet, hid, rank): each outlet's headlines shuffled, cut at cap, ranked, so labelling in rank order covers
    every outlet evenly whenever it stops"""
    rng = random.Random(seed)
    out = []
    for o in sorted(hids_by_outlet):
        hs = sorted(hids_by_outlet[o])
        rng.shuffle(hs)
        out += [(o, h, r) for r, h in enumerate(hs[:cap])]
    return sorted(out, key=lambda t: (t[2], t[0]))


def first_headlines(since: str, until: str):
    """Each article's first headline, articles first seen in the window, news by the newsfilter (non-news and junk
    out), from the site's database read-only"""
    import pandas as pd
    src = sqlite3.connect(f'file:{Config.db_file_path}?mode=ro', uri=True, timeout=60)
    a = pd.read_sql('select h.id hid, h.article_id aid, h.title, h.news_score, ar.first_accessed seen, g.name outlet, '
                    'g._country country from headline h join article ar on ar.id = h.article_id join agency g on '
                    'g.id = ar.agency_id where ar.first_accessed >= ? and ar.first_accessed < ?', src,
                    params=[since, until])
    a = a.sort_values('hid').drop_duplicates('aid')
    return a[(a.news_score.isna() | (a.news_score >= 0.5)) & (a.title.str.strip().str.len() > 0)]


def sample(days: int, cap: int, outlets: list[str] | None):
    con = connect()
    until = dt.now().strftime('%Y-%m-%d %H:%M:%S')
    since = (dt.now() - td(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    arts = first_headlines(since, until)
    chosen = outlets or outlets_by_rule(arts)
    arts = arts[arts.outlet.isin(chosen)]
    run = new_run(con, 'sample', json.dumps({'since': since, 'until': until, 'cap': cap, 'outlets': chosen}))
    by = {o: g.hid.tolist() for o, g in arts.groupby('outlet')}
    info = arts.set_index('hid')
    rows = [(int(h), run, int(info.loc[h, 'aid']), o, info.loc[h, 'title'], info.loc[h, 'seen'], r)
            for o, h, r in round_robin(by, cap)]
    con.executemany('insert into headlines values (?, ?, ?, ?, ?, ?, ?)', rows)
    con.commit()
    print(f'sample {run}: {len(rows)} headlines from {len(chosen)} outlets, {since} to {until}')
    # the hand sample: stratified so every kind of outlet and the hot end are in it
    rng = random.Random(SEED)
    pool = {r[0]: r for r in rows}
    strata = [(['One America News Network', 'Newsmax', 'Just the News'], 30), (list(CONTROLS), 15),
              (FAMILY_RIGHT + FAMILY_LEFT, 30)]
    picked = []
    for names, k in strata:
        cand = [r for r in rows if r[3] in names and r[0] not in picked]
        picked += [r[0] for r in rng.sample(cand, min(k, len(cand)))]
    rest = [r for r in rows if r[0] not in picked]
    picked += [r[0] for r in rng.sample(rest, HAND_N - len(picked))]
    out = os.path.join(os.path.dirname(DB), 'o1_wolf_hand_sample.tsv')
    order = sorted(picked, key=lambda h: rng.random())  # shuffled, so outlets don't come in blocks
    with open(out, 'w') as f:
        f.write('hid\tkind\tslant\tside\ttitle\n')
        for h in order:
            f.write(f'{h}\t\t\t\t{pool[h][4]}\n')
    print(f'hand sample ({len(order)}, outlet hidden) -> {out}')


FAMILY_RIGHT = ['Breitbart', 'The Gateway Pundit', 'Townhall', 'Red State', 'The Daily Wire', 'PJ Media',
                'The Western Journal', 'The Federalist', 'The Daily Caller']
FAMILY_LEFT = ['Raw Story', 'Alternet', 'Mediaite', 'The Daily Kos', 'Salon', 'The New Republic', 'The Daily Beast']


def latest_sample(con) -> str:
    return con.execute("select id from runs where stage = 'sample' order by at desc limit 1").fetchone()[0]


def hand(path: str):
    con = connect()
    run = latest_sample(con)
    info = {h: (o, t) for h, o, t in con.execute('select hid, outlet, title from headlines where sample = ?', (run,))}
    n = 0
    with open(path) as f:
        next(f)
        for line in f:
            hid, kind, slant, side = line.rstrip('\n').split('\t')[:4]
            if not kind:
                continue
            assert kind in KINDS and side in SIDES and slant in '01234', line
            o, t = info[int(hid)]
            con.execute('insert or replace into hand values (?, ?, ?, ?, ?, ?, ?, ?)',
                        (int(hid), o, t, kind, int(slant), side, 'claude', now()))
            n += 1
    con.commit()
    print(f'hand: {n} labels')


# ---- the model ----

def ask(title: str) -> dict | None:
    from app.analysis import llm
    t = time.time()
    got = llm.complete_json(PROMPT.format(title=title.strip()), SCHEMA, max_tokens=80, model=MODEL)
    if got and got.get('kind') in KINDS and got.get('slant') in range(5) and got.get('side') in SIDES:
        return {**got, 'seconds': time.time() - t}
    return None


def label_all(con, todo: list[tuple[int, str]], what: str):
    from app.analysis import llm
    done = {h for (h,) in con.execute('select hid from labels where model = ? and prompt = ?', (MODEL, PROMPT_ID))}
    todo = [(h, t) for h, t in todo if h not in done]
    total, t0 = len(todo), time.time()
    print(f'{what}: {total} to ask {MODEL} (prompt {PROMPT_ID})', flush=True)
    for i in range(0, total, CHUNK):
        part = todo[i:i + CHUNK]
        got = llm.parallel(lambda ht: ask(ht[1]), part, workers=WORKERS)
        con.executemany('insert or replace into labels values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        [(h, MODEL, PROMPT_ID, g['kind'], g['note'], g['slant'], g['side'], g['seconds'], now())
                         for (h, _), g in zip(part, got) if g])
        con.commit()
        k = min(i + CHUNK, total)
        print(f'{what}: {k}/{total} in {time.time() - t0:.0f}s', flush=True)


def trial():
    con = connect()
    rows = con.execute('select hid, title from hand').fetchall()
    if not rows:
        sys.exit('trial: no hand labels yet')
    label_all(con, rows, 'trial')
    run = new_run(con, 'trial')
    pairs = [({'kind': k, 'slant': s, 'side': d}, {'kind': mk, 'slant': ms, 'side': md}) for k, s, d, mk, ms, md in
             con.execute('select h.kind, h.slant, h.side, l.kind, l.slant, l.side from hand h join labels l on '
                         'l.hid = h.hid and l.model = ? and l.prompt = ?', (MODEL, PROMPT_ID))]
    a = agreement(pairs)
    a['passes'] = float(gate_passes(a))
    secs = [s for (s,) in con.execute('select seconds from labels where prompt = ? and hid in (select hid from hand)',
                                      (PROMPT_ID,))]
    con.executemany('insert or replace into agreement values (?, ?, ?, ?)',
                    [(run, k, v, a['n']) for k, v in a.items() if k != 'n'])
    con.commit()
    misses = con.execute('select h.title, h.outlet, h.kind, h.slant, l.kind, l.slant, l.note from hand h join labels l '
                         'on l.hid = h.hid and l.model = ? and l.prompt = ? where abs(h.slant - l.slant) >= 2 or '
                         '(h.slant >= 3) != (l.slant >= 3) order by abs(h.slant - l.slant) desc limit 12',
                         (MODEL, PROMPT_ID)).fetchall()
    body = validation_text(a, misses, float(np.median(secs)) if secs else None)
    write_section('validation', body)
    print(body, flush=True)


def validation_text(a: dict, misses: list, median_secs: float | None) -> str:
    lines = [f"Run {now()[:16]} by the trial step: {MODEL} on the {a['n']} hand-labelled headlines (prompt "
             f"{PROMPT_ID}){f', a median {median_secs:.1f} s a request, four at a time' if median_secs else ''}.", '',
             '| measure | value | the gate |', '|---|---|---|',
             f"| kind, agreement | {a['kind_accuracy']:.0%} | |",
             f"| kind, Cohen's kappa | {a['kind_kappa']:.2f} | {GATE['kind_kappa']} |",
             f"| slant, exact | {a['slant_exact']:.0%} | |",
             f"| slant, within one | {a['slant_within_one']:.0%} | |",
             f"| slant, quadratic-weighted kappa | {a['slant_wkappa']:.2f} | {GATE['slant_wkappa']} |",
             f"| tail (slant 3-4) yes or no, kappa | {a['tail_kappa']:.2f} | {GATE['tail_kappa']} |",
             f"| straight (slant 0) yes or no, kappa | {a['straight_kappa']:.2f} | |",
             f"| tail share, hand / model | {a['tail_hand']:.0%} / {a['tail_model']:.0%} | |", '',
             ('**The gate passed**: the full reading went ahead.' if a['passes'] else
              '**The gate failed**: the full reading did not run. The prompt needs another look before a second try.')]
    if misses:
        lines += ['', 'The widest disagreements (hand, then model):', '']
        lines += [f'- "{t}" ({o}): hand {k} {s}, model {mk} {ms} ("{n}")' for t, o, k, s, mk, ms, n in misses]
    return '\n'.join(lines)


def gate_state(con) -> bool | None:
    row = con.execute("select value from agreement where measure = 'passes' order by run desc limit 1").fetchone()
    return None if row is None else bool(row[0])


def label():
    con = connect()
    state = gate_state(con)
    if state is None:
        sys.exit('label: the trial step has not run')
    if not state:
        print('label: the gate failed on the hand sample; nothing asked (the paper says so)')
        return
    run = latest_sample(con)
    todo = con.execute('select hid, title from headlines where sample = ? order by rank, outlet', (run,)).fetchall()
    label_all(con, todo, 'label')


# ---- the report ----

def labelled_by_outlet(con, run: str, reports_only: bool) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for o, hid, title, kind, slant, side in con.execute(
            'select h.outlet, h.hid, h.title, l.kind, l.slant, l.side from headlines h join labels l on l.hid = h.hid '
            "and l.model = ? and l.prompt = ? where h.sample = ? and l.kind != 'other'", (MODEL, PROMPT_ID, run)):
        if reports_only and kind != 'report':
            continue
        out.setdefault(o, []).append({'hid': hid, 'title': title, 'kind': kind, 'slant': slant, 'side': side})
    for g, members in GROUPS.items():
        pooled = [h for m in members for h in out.get(m, [])]
        if pooled:
            out[f'{g} (pooled)'] = pooled
    return out


def pct(x) -> str:
    return '' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{100 * x:.1f}%'


def table_text(rows: list[dict]) -> str:
    lines = ['| outlet | n | straight (0) | middle (1-2) | tail (3-4) | 4 | opinion | mean | w [95%] | Holm p | '
             'valley | tail right / left | verdict |', '|' + '---|' * 13]
    for r in sorted(rows, key=lambda r: (-(r.get('w') or -1), r['outlet'])):
        if not r['n']:
            continue
        w = f"{pct(r['w'])} [{pct(r['w_lo'])}-{pct(r['w_hi'])}]" if 'w' in r else ''
        ph = f"{r['p_holm']:.3f}" if 'p_holm' in r else ''
        lines.append(f"| {r['outlet']} | {r['n']} | {pct(r['straight'])} | {pct(r['middle'])} | {pct(r['tail'])} | "
                     f"{pct(r['top'])} | {pct(r['opinion'])} | {r['mean']:.2f} | {w} | {ph} | {r['valley']:.3f} | "
                     f"{pct(r['tail_right'])} / {pct(r['tail_left'])} | {r['verdict']} |")
    return '\n'.join(lines)


def tails_text(labelled: dict, names: list[str], k: int, rng) -> list[str]:
    out = []
    for o in names:
        tail = [h for h in labelled.get(o, []) if h['slant'] >= 3]
        if not tail:
            continue
        pick = rng.sample(tail, min(k, len(tail)))
        out.append(f"**{o}** ({len(tail)} of {len(labelled[o])} at slant 3-4):")
        out += [f"- \"{h['title'].strip()}\" ({h['kind']}, {h['slant']}, {h['side']})" for h in pick]
        out.append('')
    return out


NAMED = ['One America News Network', 'Newsmax', 'Just the News', 'New York Times', 'The Hill']


def hypotheses_text(by: dict[str, dict[str, dict]]) -> list[str]:
    """The registered hypotheses against the verdicts (by[variant][outlet] = row)"""
    allv, news = by['all'], by['reports']

    def v(variant, o):
        return variant.get(o, {}).get('verdict', 'not in the data')
    out = []
    ctrl = {o: (v(allv, o), v(news, o)) for o in CONTROLS}
    broken = [o for o, (a, b) in ctrl.items() if a.startswith('barbell') or a == 'heat with a tail' or b == 'barbell']
    out.append(f"0. The controls (AP, Reuters) show no tail: {'**failed**, ' + ', '.join(broken) + ' show one, so the reading flags straight copy and nothing below can be trusted' if broken else 'held'} "
               f"({'; '.join(f'{o}: {a}, reports only {b}' for o, (a, b) in ctrl.items())}).")
    o = 'One America News Network'
    a, b = v(allv, o), v(news, o)
    res = ('held' if a == 'barbell' and b == 'barbell' else 'partly held (a barbell with its opinion, not as news)'
           if a == 'barbell' else 'no' if a in ('one shifted mode', 'heat') else "can't tell" if a == "can't tell"
           else a)
    out.append(f'1. One America News Network is a barbell, and stays one on reports alone: {res} ({a}; reports only, {b}).')
    o = 'Newsmax'
    a, b = v(allv, o), v(news, o)
    res = 'held' if a == 'barbell' and b != 'barbell' else 'no: a barbell in its reports too' if b == 'barbell' else \
        "can't tell" if a == "can't tell" else 'no'
    out.append(f"2. Newsmax's tail is its opinion: a barbell on everything, not on reports alone: {res} ({a}; reports only, {b}).")
    nh = {x: v(allv, x) for x in ('New York Times', 'The Hill')}
    untested = all(s in ('not in the data', 'too few') for s in nh.values())
    held = all(not s.startswith('barbell') for s in nh.values())
    out.append(f"3. The New York Times and The Hill are not barbells under the reading: "
               f"{'not tested' if untested else 'held' if held else 'no'} "
               f"({'; '.join(f'{x}: {s}' for x, s in nh.items())}).")
    web = {x: v(allv, x) for x in FAMILY_RIGHT + FAMILY_LEFT if x in allv and allv[x].get('n', 0) >= MIN_TESTED}
    shifted = [x for x, s in web.items() if s.startswith('heat') or s == 'one shifted mode']
    out.append(f"4. The partisan webs are one shifted mode, not barbells (at least three in four not barbells): "
               f"{'held' if web and sum(not s.startswith('barbell') for s in web.values()) >= 0.75 * len(web) else 'no'} "
               f"({len(web) - len(shifted)} of {len(web)} otherwise: "
               f"{', '.join(f'{x} ({s})' for x, s in web.items() if x not in shifted) or 'none'}).")
    found = sorted(x for x, r in allv.items() if r.get('verdict') == 'barbell')
    out.append(f"5. Barbells exist as a type (one or more outlets besides the controls): "
               f"{'held: ' + ', '.join(found) if [x for x in found if x not in CONTROLS] else 'no'}.")
    return out


def report():
    con = connect()
    run_s = latest_sample(con)
    if gate_state(con) is False:
        write_section('results', 'Not run: the trial step\'s gate failed on the hand sample (see Validation), so the '
                                 'full reading did not go ahead and there is nothing to report. The prompt needs another '
                                 'look; nothing else here has been tested.')
        print('report: the gate failed; the paper says so')
        return
    n_set = con.execute('select count(*) from headlines where sample = ?', (run_s,)).fetchone()[0]
    n_lab = con.execute('select count(*) from headlines h join labels l on l.hid = h.hid and l.model = ? and '
                        'l.prompt = ? where h.sample = ?', (MODEL, PROMPT_ID, run_s)).fetchone()[0]
    kinds = dict(con.execute('select l.kind, count(*) from headlines h join labels l on l.hid = h.hid and l.model = ? '
                             'and l.prompt = ? where h.sample = ? group by l.kind', (MODEL, PROMPT_ID, run_s)))
    run = new_run(con, 'report', json.dumps({'sample': run_s}))
    rng = random.Random(SEED)
    by, shapes, texts = {}, {}, {}
    for variant, only in (('all', False), ('reports', True)):
        labelled = labelled_by_outlet(con, run_s, only)
        rows, shape = analyse(labelled)
        by[variant] = {r['outlet']: r for r in rows}
        shapes[variant] = shape
        texts[variant] = (labelled, rows)
        con.executemany('insert or replace into results values (' + ','.join('?' * 22) + ')',
                        [(run, variant, r['outlet'], r['n'], r.get('straight'), r.get('middle'), r.get('tail'),
                          r.get('top'), r.get('opinion'), r.get('mean'), r.get('mu'), r.get('w'), r.get('w_lo'),
                          r.get('w_hi'), r.get('lr'), r.get('p'), r.get('p_holm'), r.get('bell_mode'), r.get('valley'),
                          r.get('tail_right'), r.get('tail_left'), r['verdict']) for r in rows])
        if shape:
            con.execute('insert or replace into shape values (?, ?, ?, ?, ?, ?)',
                        (run, variant, shape['c2'], shape['c3'], shape['c4'], shape['q']))
    con.commit()
    sample_notes = json.loads(con.execute('select notes from runs where id = ?', (run_s,)).fetchone()[0])
    lines = [f"Run {now()[:16]} by the report step, on {n_lab} of the {n_set} headlines drawn "
             f"({sample_notes['since'][:10]} to {sample_notes['until'][:10]}, up to {sample_notes['cap']} an outlet, "
             f"{len(sample_notes['outlets'])} outlets); the model's kinds: "
             + ', '.join(f'{k} {v}' for k, v in sorted(kinds.items())) + ". 'other' is left out of everything below.",
             '']
    for variant, title in (('all', 'Everything it ran (reports and opinion)'), ('reports', 'Reports only')):
        s = shapes[variant]
        lines += [f'### {title}', '']
        if s:
            lines += [f"The shared shape: cut lines at 0, {s['c2']:.2f}, {s['c3']:.2f}, {s['c4']:.2f} on the latent "
                      f"slant (spread 1); the tail's split between 3 and 4, {s['q']:.0%} : {1 - s['q']:.0%}.", '']
        lines += [table_text(texts[variant][1]), '']
        found = sorted(o for o, r in by[variant].items() if r['verdict'] == 'barbell')
        lines += [f"Barbells: {', '.join(found) if found else 'none'}.", '']
    lines += ['### Against the hypotheses', ''] + hypotheses_text(by) + ['']
    cands = sorted({o for v in by.values() for o, r in v.items() if r['verdict'] == 'barbell'} | set(NAMED))
    lines += ['### The tails', '', 'Up to eight of the tail headlines (slant 3-4, everything it ran) of each barbell '
              'and each outlet named in the hypotheses, drawn at random; the model\'s kind, slant and side after each.',
              '']
    lines += tails_text(texts['all'][0], cands, 8, rng)
    lines += ['### Doubts the numbers raise', ''] + doubts(by, kinds) + ['']
    lines += ['### Every outlet\'s tail', '', 'Three tail headlines of each other outlet, drawn at random.', '']
    lines += tails_text(texts['all'][0], sorted(o for o in texts['all'][0] if o not in cands), 3, rng)
    write_section('results', '\n'.join(lines))
    print('\n'.join(lines[:60]), flush=True)


def doubts(by: dict, kinds: dict) -> list[str]:
    """Doubts the run's own numbers raise, written out so the paper has them whatever comes back"""
    out = []
    allv = by['all']
    thin = sorted(o for o, r in allv.items() if r['n'] < MIN_TESTED)
    if thin:
        out.append(f"- Too few headlines to test ({MIN_TESTED} needed): {', '.join(thin)}.")
    tell = sorted(o for o, r in allv.items() if r['verdict'] == "can't tell")
    if tell:
        out.append(f"- A tail that may be there but can't be told from none at this size: {', '.join(tell)}.")
    grid = [r for r in allv.values() if 'w' in r]
    if grid:
        at_edge = [r['outlet'] for r in grid if r['w'] >= 0.49]
        if at_edge:
            out.append(f"- w at its bound (0.5), so the mixture is not describing a small tail: {', '.join(at_edge)}.")
    flip = sorted(o for o in allv if allv[o]['verdict'] == 'barbell' and by['reports'].get(o, {}).get('verdict') != 'barbell')
    if flip:
        out.append(f"- Barbells on everything but not on reports alone (the tail is in its opinion, or reports are "
                   f"too few): {', '.join(flip)}.")
    other = kinds.get('other', 0) / max(sum(kinds.values()), 1)
    out.append(f"- The model called {other:.0%} of the set 'other' and those are left out; a headline it wrongly put "
               f"there drops out of both modes.")
    out.append('- Every verdict rests on one model, one prompt and one reading per headline; the hand check is '
               'Claude\'s, not the person\'s.')
    return out


def main():
    p = argparse.ArgumentParser(prog='o1_wolf.py')
    sub = p.add_subparsers(dest='what', required=True)
    s = sub.add_parser('sample')
    s.add_argument('--days', type=int, default=DAYS)
    s.add_argument('--cap', type=int, default=CAP)
    s.add_argument('--outlets', help='comma-separated outlet names in place of the default rule')
    h = sub.add_parser('hand')
    h.add_argument('file')
    for name in ('trial', 'label', 'report'):
        sub.add_parser(name)
    a = p.parse_args()
    if a.what == 'sample':
        sample(a.days, a.cap, [x.strip() for x in a.outlets.split(',')] if a.outlets else None)
    elif a.what == 'hand':
        hand(a.file)
    else:
        {'trial': trial, 'label': label, 'report': report}[a.what]()


if __name__ == '__main__':
    main()
