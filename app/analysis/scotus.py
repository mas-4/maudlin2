"""Supreme Court coverage (#144): which outlets cover which of the Court's cases, at which stage, and from which side.

Headlines that name the Court or a justice are candidates; the language model confirms each is about the US Supreme
Court (not a state's or another country's), says what case or issue it's about in a few words and which stage it
reports (cached per headline, like the saga checks). A headline is tied to a case on the Court's own docket (the
Granted & Noted list, a public-domain government record, fetched at most once a week) only when it names a distinctive
party of exactly one case: "Suncor" or "Boulder", never "Congress" or "Johnson", which turn up in court news about
anything. The press measures and the docket stay separate, so readers can see both."""
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime as dt, timedelta as td

import requests as rq
from sqlalchemy import or_

from app.analysis import llm
from app.models import Session, Headline, Article, Agency
from app.utils import Config, get_logger

logger = get_logger(__name__)

DOCKET = os.path.join(Config.data, 'scotus_docket.json')
JUDGMENTS = os.path.join(Config.data, 'scotus_judgments.json')
DOCKET_URL = 'https://www.supremecourt.gov/orders/{yy}grantednotedlist.pdf'
DOCKET_REFRESH = td(days=7)
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
WINDOW_DAYS = 14
MAX_NEW_JUDGMENTS = 80  # per run, so a backlog can't hold up the hourly build; the rest are judged next run
CASES = os.path.join(Config.data, 'scotus_case_judgments.json')

JUSTICES = ('Roberts', 'Thomas', 'Alito', 'Sotomayor', 'Kagan', 'Gorsuch', 'Kavanaugh', 'Barrett', 'Jackson')
CANDIDATE = re.compile(r"\b(supreme court|scotus|high court|justices|chief justice|justice (?:%s)|alito|sotomayor|"
                       r"kagan|gorsuch|kavanaugh|ketanji|coney barrett|clarence thomas)\b" % '|'.join(JUSTICES), re.I)
# The database prefilter for CANDIDATE (SQLite's LIKE ignores case)
LIKE = ('supreme court', 'scotus', 'high court', 'justice', 'alito', 'sotomayor', 'kagan', 'gorsuch', 'kavanaugh',
        'ketanji', 'coney barrett', 'clarence thomas')

STAGES = ['case taken', 'argument', 'ruling', 'emergency order', 'the justices', 'nomination or retirement',
          'term preview', 'other']
STAGE_EMOJI = {'case taken': '📥', 'argument': '🎤', 'ruling': '🔨', 'emergency order': '🚨', 'the justices': '🧑‍⚖️',
               'nomination or retirement': '🪑', 'term preview': '🗓️', 'other': '⚖️'}

JUDGE_PROMPT = """Headline: {title}

Is this headline about the Supreme Court of the United States: its cases, arguments, rulings, orders or justices? \
A state supreme court, another country's supreme court, or a lower federal court is not.

If it is, also give:
- case: the case or issue in a few words, as the headline describes it (for example "Boulder climate suit" or \
"Trump tariffs"), or "" if it isn't about one case
- stage: which of these it reports: {stages}

reason: a few words
us_supreme_court: true or false
case: the case or issue, or ""
stage: one of the stages"""
JUDGE_SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string"}, "us_supreme_court": {"type": "boolean"}, "case": {"type": "string"},
    "stage": {"type": "string", "enum": STAGES}}, "required": ["reason", "us_supreme_court", "case", "stage"]}

CASE_PROMPT = """Headline: {title}

Supreme Court cases already in the news, each with headlines known to be about it:
{cases}

Is the headline above about one of these cases? The same case is often described by its issue or its place instead of \
its parties' names. Answer "none" if it's about a different case, several cases at once, or the Court in general.

reason: which case it matches and why, in your own words
case: the case number from the list, or none"""

# Party words too common in court news to tie a headline to one case: government parties, generic institutions and
# common surnames (Johnson is also the Speaker; Blanche is the attorney general, a party to many cases)
GENERIC = {
    'united', 'states', 'america', 'congress', 'department', 'homeland', 'security', 'labor', 'force', 'state',
    'county', 'city', 'board', 'regents', 'university', 'system', 'commissioners', 'commission', 'committee',
    'national', 'republican', 'democratic', 'international', 'partners', 'global', 'energy', 'transmission',
    'investment', 'policy', 'comm', 'corp', 'inc', 'llc', 'company', 'district', 'judicial', 'circuit', 'attorney',
    'general', 'gen', 'att’y', "att'y", 'saint', 'mary', 'john', 'baptist', 'catholic', 'parish', 'church', 'ethical',
    'care', 'games', 'heights', 'valley', 'grand', 'black', 'grant', 'johnson', 'blanche', 'alaska', 'florida', 'texas',
    'california', 'trump', 'biden', 'roy', 'cook', 'missionaries', 'ferguson', 'young', 'smith', 'jones', 'brown',
    'univ', 'deptartment',  # (sic: the list's own typo)
}
# Short names the press uses for a party, by a phrase in the party's name
ALIASES = {'REPUBLICAN NATIONAL COMMITTEE': ['RNC']}


def term(now: dt = None) -> int:
    """The Court's term by the year it opens (October Term 2026 runs from October 2026 into 2027)."""
    now = now or dt.now()
    return now.year if now.month >= 10 else now.year - 1


def nice_name(name: str) -> str:
    """'SUNCOR ENERGY (U.S.A.) INC. V. COMMISSIONERS OF BOULDER COUNTY' -> 'Suncor Energy (U.S.A.) Inc. v.
    Commissioners of Boulder County'."""
    words = []
    for i, w in enumerate(name.split()):
        if w in ('V.', 'v.'):
            words.append('v.')
        elif i and w.lower() in ('of', 'the', 'for', 'and', 'on', 'in'):
            words.append(w.lower())
        elif re.fullmatch(r'\(?([A-Z]\.)+\)?,?', w) or len(w) <= 3 and w.isupper() and '.' not in w and w != 'GA':
            words.append(w)  # initials and acronyms (U.S.A., WBI, D. V. D.)
        else:
            words.append(w[0] + w[1:].lower() if w[0].isalpha() else w[:2] + w[2:].lower())
    return ' '.join(words)


def parse_granted(text: str) -> list[dict]:
    """The cases on a Granted & Noted list (pdftotext -layout output): docket number, name, and the grant and
    argument dates shared by each group of consolidated cases."""
    cases, pending, group = [], [], []
    for line in text.splitlines():
        m = re.match(r"\s*(\d{2}-\d+)\)?\d*\s+[A-Z]{3}\s+(\S.*?)\s*$", line)
        if m:
            case = {'docket': m.group(1), 'name': nice_name(m.group(2)), 'raw': m.group(2), 'granted': None,
                    'argued': None, 'from': None}
            cases.append(case)
            pending.append(case)
            continue
        if 'Court:' in line:
            group, pending = pending, []
            granted = re.search(r"Granted:\s*(\d+/\d+/\d+)", line)
            origin = re.search(r"Court:\s*(\S+)", line)
            for case in group:
                case['granted'] = granted.group(1) if granted else None
                case['from'] = origin.group(1) if origin else None
        argued = re.search(r"Argument Date:\s*(\d+/\d+/\d+)", line)
        if argued:
            for case in group:
                case['argued'] = argued.group(1)
    return cases


def refresh_docket(now: dt = None) -> None:
    """Fetch this term's Granted & Noted list if ours is a week old or from another term (one request); on any
    failure keep the copy we have."""
    now = now or dt.now()
    current = docket()
    if current.get('term') == term(now) and now - dt.fromisoformat(current['fetched']) < DOCKET_REFRESH:
        return
    url = DOCKET_URL.format(yy=f'{term(now) % 100:02d}')
    try:
        response = rq.get(url, headers={'User-Agent': USER_AGENT}, timeout=30)
        response.raise_for_status()
        text = subprocess.run(['pdftotext', '-layout', '-', '-'], input=response.content, capture_output=True,
                              timeout=60, check=True).stdout.decode('utf-8', 'replace')
    except (rq.RequestException, OSError, subprocess.SubprocessError) as e:
        logger.warning("Supreme Court docket not refreshed (%s); keeping %d cases", e, len(current.get('cases', [])))
        return
    cases = parse_granted(text)
    if not cases:
        logger.warning("Supreme Court docket: no cases found in %s; keeping the old list", url)
        return
    with open(DOCKET, 'w') as f:
        json.dump({'term': term(now), 'fetched': now.isoformat(timespec='seconds'), 'source': url, 'cases': cases}, f)
    logger.info("Supreme Court docket: %d cases for October Term %d", len(cases), term(now))


def docket() -> dict:
    try:
        with open(DOCKET) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def party_words(raw: str) -> set[str]:
    """The distinctive words in a case's party names, lowercased: 'Suncor', 'Boulder'; not 'Congress'."""
    found = set()
    for word in re.findall(r"[A-Za-z][A-Za-z'’]*", raw):
        w = word.lower()
        if len(w) >= 4 and w not in GENERIC:
            found.add(w)
    for phrase, aliases in ALIASES.items():
        if phrase in raw.upper():
            found.update(a.lower() for a in aliases)
    return found


def matcher(cases: list[dict]):
    """A function from a headline to the one docket case it names a distinctive party of, or None (no case, or more
    than one)."""
    patterns = [(case, re.compile(r"\b(%s)\b" % '|'.join(map(re.escape, sorted(words))), re.I))
                for case in cases if (words := party_words(case['raw']))]

    def match(title: str):
        hits = [case for case, pattern in patterns if pattern.search(title)]
        return hits[0] if len(hits) == 1 else None
    return match


def _key(title: str) -> str:
    return hashlib.sha1(title.encode()).hexdigest()


def judge(title: str, cache: dict, ask: bool = True):
    """The model's reading of one headline (cached by its text). None when it's unjudged and `ask` is off, or the
    model gave no answer (asked again next run)."""
    key = _key(title)
    if key not in cache:
        if not ask:
            return None
        answer = llm.complete_json(JUDGE_PROMPT.format(title=title, stages=', '.join(STAGES)), JUDGE_SCHEMA,
                                   max_tokens=100)
        if not answer or 'us_supreme_court' not in answer:
            return None
        cache[key] = {**answer, 'title': title, 'model': llm.model()}
    return cache[key]


def candidates(since: dt) -> list[dict]:
    """Headlines first seen since `since` that name the Court or a justice, newest first, one per outlet and title."""
    with Session() as session:
        rows = session.query(
            Headline.processed, Headline.first_accessed, Agency.name, Agency._bias, Agency.lean_rated, Article.url,  # noqa
        ).join(Headline.article).join(Article.agency).filter(
            Headline.first_accessed > since,
            or_(*[Headline.processed.ilike(f'%{w}%') for w in LIKE]),
        ).order_by(Headline.first_accessed.desc()).all()
    seen, out = set(), []
    for title, first, agency, bias, rated, url in rows:
        if not title or not CANDIDATE.search(title) or (agency, title) in seen:
            continue
        seen.add((agency, title))
        out.append({'title': title, 'first': first, 'agency': agency, 'bias': bias, 'rated': bool(rated), 'url': url})
    return out


def case_options(by_case: dict, cases: list[dict]) -> list[dict]:
    """The cases the press has named a party of, each with the court it came from and up to 3 of those headlines
    (the earliest, so the list holds steady as more coverage comes in): what the press says the case is about."""
    known = {c['docket']: c for c in cases}
    options = []
    for number, rows in by_case.items():
        if rows:
            case = known.get(number, {})
            titles = list(dict.fromkeys(r['title'] for r in sorted(rows, key=lambda r: r['first'])))[:3]
            options.append({'docket': number, 'name': case.get('name', number), 'from': case.get('from'),
                            'titles': titles})
    return sorted(options, key=lambda o: o['docket'])


def by_issue(unnamed: list[dict], by_case: dict, cases: list[dict] = (), cache: dict = None) -> list:
    """For each headline that names no party, the docket number of the case the language model says it's about,
    choosing among the cases the press has named a party of (case_options), or None. The press teaches the docket
    what each case is about: the Court's list gives only the parties' names. Term previews (several cases at once)
    and headlines with no case are skipped; answers are cached per headline and set of choices, at most
    MAX_NEW_JUDGMENTS new ones a run."""
    cache = {} if cache is None else cache
    options = case_options(by_case, list(cases))
    out = [None] * len(unnamed)
    if not options:
        return out
    listing = '\n'.join(f"- {o['docket']}: {o['name']}" + (f" (from {o['from']})" if o['from'] else '') + ''.join(
        f'\n    "{t}"' for t in o['titles']) for o in options)
    schema = {"type": "object", "properties": {
        "reason": {"type": "string"}, "case": {"type": "string", "enum": [o['docket'] for o in options] + ['none']}},
        "required": ["reason", "case"]}
    asked = 0
    for i, row in enumerate(unnamed):
        if not row.get('issue', '').strip() or row.get('stage') == 'term preview':
            continue
        key = _key(row['title'] + '\n' + listing)
        if key not in cache:
            if asked >= MAX_NEW_JUDGMENTS:
                continue
            asked += 1
            answer = llm.complete_json(CASE_PROMPT.format(title=row['title'], cases=listing), schema, max_tokens=250)
            if not answer or 'case' not in answer:
                continue
            cache[key] = {**answer, 'title': row['title'], 'model': llm.model()}
        if cache[key]['case'] != 'none':
            out[i] = cache[key]['case']
    return out


def side(row: dict) -> str:
    if not row['rated']:
        return 'unrated'
    return 'left' if row['bias'] < 0 else 'right' if row['bias'] > 0 else 'center'


def coverage(now: dt = None) -> dict:
    """The last WINDOW_DAYS of US Supreme Court headlines: grouped by docket case where a headline names one, the
    rest together; and the term's cases with how many outlets covered each, from which side."""
    now = now or Config.last_accessed
    try:
        with open(JUDGMENTS) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    before = len(cache)
    rows = candidates(now - td(days=WINDOW_DAYS))
    asked = 0
    court = []
    for row in rows:
        new = _key(row['title']) not in cache
        verdict = judge(row['title'], cache, ask=asked < MAX_NEW_JUDGMENTS)
        asked += new and asked < MAX_NEW_JUDGMENTS
        if verdict and verdict['us_supreme_court']:
            court.append({**row, 'stage': verdict['stage'], 'issue': verdict['case'], 'side': side(row)})
    if len(cache) > before:
        with open(JUDGMENTS, 'w') as f:
            json.dump(cache, f)
    logger.info("Supreme Court: %d candidate headlines, %d about the Court; %d newly judged",
                len(rows), len(court), len(cache) - before)

    cases = docket().get('cases', [])
    match = matcher(cases)
    by_case = {c['docket']: [] for c in cases}
    unnamed = []
    for row in court:
        case = match(row['title'])
        if case:
            row['via'] = 'party'
            by_case[case['docket']].append(row)
        else:
            unnamed.append(row)
    other = []
    try:
        with open(CASES) as f:
            case_cache = json.load(f)
    except (OSError, ValueError):
        case_cache = {}
    known = len(case_cache)
    joined = by_issue(unnamed, by_case, cases, case_cache)
    if len(case_cache) > known:
        with open(CASES, 'w') as f:
            json.dump(case_cache, f)
    for row, docket_number in zip(unnamed, joined):
        if docket_number:
            row['via'] = 'issue'
            by_case[docket_number].append(row)
        else:
            other.append(row)
    for rows in by_case.values():
        rows.sort(key=lambda r: r['first'], reverse=True)

    def summary(rows: list[dict]) -> dict:
        one_each = {}
        for r in rows:  # newest first, so each outlet's latest headline
            one_each.setdefault(r['agency'], r)
        return {'outlets': len(one_each), 'sides': dict(Counter(r['side'] for r in one_each.values())),
                'stages': dict(Counter(r['stage'] for r in rows)), 'headlines': rows}
    term_cases = []
    for case in cases:
        term_cases.append({**case, **summary(by_case[case['docket']])})
    covered = sorted([c for c in term_cases if c['headlines']], key=lambda c: c['headlines'][0]['first'],
                     reverse=True)
    return {'term': docket().get('term'), 'source': docket().get('source'), 'covered': covered,
            'cases': term_cases, 'other': summary(other), 'total': len(court), 'window_days': WINDOW_DAYS}
