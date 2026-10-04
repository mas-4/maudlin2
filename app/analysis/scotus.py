"""Supreme Court coverage (#144): which outlets cover which of the Court's cases, at which stage, and from which side.

The term's cases come from the Court's own Granted & Noted list (a public-domain government record); what each is
about comes from the questions presented on Wikipedia's list of pending cases (CC BY-SA), which the language model
turns into a plain gloss a headline would use ("Cook County assault weapons ban"). Both are fetched at most weekly.

Headlines that name the Court or a justice are candidates. The model reads each with the outlet and its country and
says whether it's about the US Supreme Court (not a state's or another country's), which of the term's cases it's about
(chosen from the glossed list; several for a term preview), a few topic words, and the stage it reports. A headline
that names a distinctive party of exactly one case ("Suncor", never "Congress") is tied to that case as well. Verdicts
are cached per headline, outlet country and case list, at most MAX_NEW_JUDGMENTS new ones a run."""
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
from app.utils.constants import Country

logger = get_logger(__name__)

DOCKET = os.path.join(Config.data, 'scotus_docket.json')
JUDGMENTS = os.path.join(Config.data, 'scotus_judgments.json')
DOCKET_URL = 'https://www.supremecourt.gov/orders/{yy}grantednotedlist.pdf'
DOCKET_REFRESH = td(days=7)
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
WINDOW_DAYS = 14
MAX_NEW_JUDGMENTS = 80  # per run, so a backlog can't hold up the hourly build; the rest are judged next run
GLOSSES = os.path.join(Config.data, 'scotus_glosses.json')
WIKI_API = 'https://en.wikipedia.org/w/api.php'
WIKI_PAGE = 'List of pending United States Supreme Court cases'

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
Outlet: {outlet} ({country})

Is this headline about the Supreme Court of the United States: its cases, arguments, rulings, orders or justices? \
A state supreme court, another country's supreme court (India's, for example), or a lower federal court is not.

If it is, also give:
- cases: the numbers of the cases from this list the headline is about. None if it's about a case not on the list, \
the justices, or the Court in general; several for a preview of the term that names several.
{cases}
- topics: 1 to 3 short words for its specific subject, like "climate", "guns", "immigration", "abortion", \
"elections", "religion", "retirement", "ethics". Not general words like "law", "government", "justices", "court" or \
"politics". Reuse these when they fit: {topics}
- stage: which of these it reports: {stages}

reason: in your own words, briefly
us_supreme_court: true or false
cases: the case numbers, or an empty list
topics: the topic words
stage: one of the stages"""
MAX_VOCABULARY = 40  # topic words shown to the model to reuse, most used first
VAGUE = {'law', 'laws', 'legal', 'government', 'governments', 'justice', 'justices', 'court', 'courts', 'politics',
         'supreme court', 'scotus', 'judiciary', 'policy', 'news', 'governance', 'constitutional', 'constitution',
         'rule', 'rules', 'executive', 'power', 'powers', 'rights', 'ruling', 'rulings', 'cases', 'case'}  # topic words that say nothing; dropped

CONFIRM_PROMPT = """Headline: {title}

Supreme Court case: {name}: {gloss}
What it asks: {question}
{only}
Is the headline about this case? It counts if the headline describes the case by its subject, place or parties, \
including a preview of the term that names its subject. It doesn't count if the headline is about something else \
that merely shares a broad area, or about the Court or the justices in general.

reason: in your own words, briefly
refers: true or false"""
CONFIRM_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string"}, "refers": {"type": "boolean"}},
                  "required": ["reason", "refers"]}
AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire'}  # as in page_headlines

GLOSS_PROMPT = """Supreme Court case: {name}{origin}
Question presented: {question}

gloss: in 3 to 8 plain words, what is this case about, the way a news headline would put it? Use the place, party or \
subject a reader would know (for example "Texas abortion pill ban" or "Louisiana congressional map").
keywords: 2 to 5 words or short phrases a news headline about this case would likely use: its subject in everyday \
words, places, well-known parties (for example "abortion pill", "mifepristone", "Texas"). Not legal terms of art.
Use only what's given here.
"""
GLOSS_SCHEMA = {"type": "object", "properties": {"gloss": {"type": "string"},
                                                "keywords": {"type": "array", "items": {"type": "string"},
                                                             "maxItems": 5}},
                "required": ["gloss", "keywords"]}

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
    'dist', 'younge', 'young', 'north', 'south', 'maxwell',  # Maxwell: also Ghislaine Maxwell, in court news on her own
}
# Short names the press uses for a party, by a phrase in the party's name
ALIASES = {'REPUBLICAN NATIONAL COMMITTEE': ['RNC']}


def term(now: dt = None) -> int:
    """The Court's term by the year it opens (October Term 2026 runs from October 2026 into 2027)."""
    now = now or dt.now()
    return now.year if now.month >= 10 else now.year - 1


# Short words in the Court's all-caps names that are words, not acronyms ("Air Force", not "AIR Force")
WORDS = {'AIR', 'SUN', 'NEW', 'OLD', 'BIG', 'RED', 'ONE', 'TWO', 'ART', 'LAW', 'OIL', 'GAS', 'BAY', 'CAR', 'ICE', 'FOX',
         'GA', 'DA', 'DE', 'LA', 'VON', 'VAN', 'MI'}


def nice_name(name: str) -> str:
    """'SUNCOR ENERGY (U.S.A.) INC. V. COMMISSIONERS OF BOULDER COUNTY' -> 'Suncor Energy (U.S.A.) Inc. v.
    Commissioners of Boulder County'."""
    words, versus = [], False
    for i, w in enumerate(name.split()):
        if w in ('V.', 'v.') and not versus:  # the first is "versus"; later ones are initials (D. V. D.)
            words.append('v.')
            versus = True
        elif i and w.lower() in ('of', 'the', 'for', 'and', 'on', 'in'):
            words.append(w.lower())
        elif re.fullmatch(r'\(?([A-Z]\.)+\)?,?', w) or (len(w) <= 3 and w.isupper() and '.' not in w
                                                          and w.rstrip(',') not in WORDS):
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

def parse_pending(html: str) -> list[dict]:
    """The rows of Wikipedia's pending-cases table: case name, docket numbers (consolidated cases share a row) and
    the question presented."""
    from bs4 import BeautifulSoup
    rows = []
    for table in BeautifulSoup(html, 'html.parser').select('table.wikitable'):
        header = [th.get_text(' ', strip=True).lower() for th in table.select('tr')[0].select('th')]
        if not header or 'docket' not in ' '.join(header):
            continue
        name_col = 0
        docket_col = next(i for i, h in enumerate(header) if 'docket' in h)
        question_col = next((i for i, h in enumerate(header) if 'question' in h), None)
        for tr in table.select('tr')[1:]:
            cells = tr.select('td, th')
            if len(cells) <= max(docket_col, question_col or 0):
                continue
            question = cells[question_col].get_text(' ', strip=True) if question_col is not None else ''
            rows.append({'name': cells[name_col].get_text(' ', strip=True),
                         'dockets': re.findall(r'\d{2}[-A]\d+', cells[docket_col].get_text(' ', strip=True)),
                         'question': re.sub(r'\s+', ' ', re.sub(r'\s+([,.;:)])', r'\1', question))[:1200]})
    return rows


def add_questions(cases: list[dict], pending: list[dict]) -> None:
    """Each case's question presented, by docket number, or else by a distinctive party word in the row's name
    (Wikipedia gives some cases their application number)."""
    by_docket = {d: row for row in pending for d in row['dockets']}
    for case in cases:
        row = by_docket.get(case['docket'])
        if row is None:
            words = party_words(case['raw'])
            row = next((r for r in pending if words and words & {w.lower() for w in re.findall(r"[A-Za-z']+", r['name'])}),
                       None)
        if row:
            case['question'] = row['question']


def refresh_docket(now: dt = None) -> None:
    """Fetch this term's Granted & Noted list and Wikipedia's pending-cases table if ours are a week old or from
    another term (one request each); on any failure keep the copy we have."""
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
    try:
        response = rq.get(WIKI_API, params={'action': 'parse', 'page': WIKI_PAGE, 'prop': 'text', 'format': 'json',
                                            'formatversion': 2}, headers={'User-Agent': USER_AGENT}, timeout=30)
        response.raise_for_status()
        add_questions(cases, parse_pending(response.json()['parse']['text']))
    except (rq.RequestException, ValueError, KeyError) as e:
        logger.warning("Supreme Court questions not fetched from Wikipedia (%s); keeping the old ones", e)
        old = {c['docket']: c.get('question') for c in current.get('cases', [])}
        for case in cases:
            if old.get(case['docket']):
                case['question'] = old[case['docket']]
    with open(DOCKET, 'w') as f:
        json.dump({'term': term(now), 'fetched': now.isoformat(timespec='seconds'), 'source': url, 'cases': cases}, f)
    logger.info("Supreme Court docket: %d cases for October Term %d, %d with a question presented", len(cases),
                term(now), sum(bool(c.get('question')) for c in cases))


def docket() -> dict:
    try:
        with open(DOCKET) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def add_glosses(cases: list[dict]) -> None:
    """Each case's plain gloss from its question presented (the model, cached by name and question); a case without
    a question gets none rather than a guess from its name."""
    try:
        with open(GLOSSES) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    before = len(cache)
    for case in cases:
        if not case.get('question'):
            continue
        key = hashlib.sha1((case['name'] + '\n' + case['question'] + '\nkeywords').encode()).hexdigest()
        if key not in cache:
            origin = f" (from {case['from']})" if case.get('from') else ''
            answer = llm.complete_json(GLOSS_PROMPT.format(name=case['name'], origin=origin,
                                                           question=case['question']), GLOSS_SCHEMA, max_tokens=120)
            if not answer or not answer.get('gloss', '').strip():
                continue
            cache[key] = {'gloss': answer['gloss'].strip().strip('."'), 'name': case['name'], 'model': llm.model(),
                          'keywords': [k.strip() for k in answer.get('keywords', []) if k.strip()][:5]}
        case['gloss'] = cache[key]['gloss']
        case['keywords'] = cache[key].get('keywords', [])
    if len(cache) > before:
        with open(GLOSSES, 'w') as f:
            json.dump(cache, f)


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


def _key(*parts: str) -> str:
    return hashlib.sha1('\n'.join(parts).encode()).hexdigest()


def vocabulary(cache: dict) -> list[str]:
    """The topic words given so far, most used first, for the model to reuse."""
    counts = Counter(t for v in cache.values() if v.get('us_supreme_court') for t in v.get('topics', []))
    return [t for t, _ in counts.most_common(MAX_VOCABULARY)]


def listing(cases: list[dict]) -> str:
    """The term's cases as the model sees them: number, name and gloss."""
    return '\n'.join(f"  {c['docket']}: {c['name']}" + (f": {c['gloss']}" if c.get('gloss') else '') for c in cases)


# Words too general to tie a headline to a case on their own
CUE_STOP = {'supreme', 'court', 'case', 'cases', 'justice', 'justices', 'rule', 'rules', 'ruling', 'right', 'rights',
            'law', 'laws', 'state', 'states', 'federal', 'united', 'america', 'american', 'review', 'reviews', 'weigh',
            'weighs', 'challenge', 'claim', 'claims', 'new', 'debate', 'act', 'v.', 'inc', 'corp', 'county', 'city',
            'department', 'circuit', 'ninth', 'fifth', 'district', 'error', 'standard', 'authority', 'term'}


def _stems(text: str) -> set[str]:
    from nltk.corpus import stopwords
    from nltk.stem.snowball import SnowballStemmer
    stem = SnowballStemmer('english').stem
    stop = set(stopwords.words('english')) | CUE_STOP
    return {stem(w) for w in re.findall(r"[a-z0-9][a-z0-9'-]*[a-z0-9]", text.lower()) if w not in stop and len(w) >= 3}


# State courts the Court hears cases from ("SC-KY", "SC-Colo."): the state is a cue ("Kentucky church shrine")
STATES = {'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CAL': 'California',
          'CO': 'Colorado', 'COLO': 'Colorado', 'CT': 'Connecticut', 'CONN': 'Connecticut', 'DE': 'Delaware',
          'FL': 'Florida', 'FLA': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
          'ILL': 'Illinois', 'IN': 'Indiana', 'IND': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KAN': 'Kansas',
          'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts',
          'MASS': 'Massachusetts', 'MI': 'Michigan', 'MICH': 'Michigan', 'MN': 'Minnesota', 'MINN': 'Minnesota',
          'MS': 'Mississippi', 'MISS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'MONT': 'Montana',
          'NE': 'Nebraska', 'NEB': 'Nebraska', 'NV': 'Nevada', 'NEV': 'Nevada', 'NH': 'New Hampshire',
          'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota',
          'OH': 'Ohio', 'OK': 'Oklahoma', 'OKLA': 'Oklahoma', 'OR': 'Oregon', 'ORE': 'Oregon', 'PA': 'Pennsylvania',
          'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee', 'TENN': 'Tennessee',
          'TX': 'Texas', 'TEX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington',
          'WASH': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WIS': 'Wisconsin', 'WY': 'Wyoming'}


def origin_state(court: str) -> str:
    """'SC-KY' -> 'Kentucky'; federal appeals courts ('USCA-6') have none."""
    m = re.fullmatch(r'(?:SC|CA|Dist\.)-([A-Za-z]+)\.?', (court or '').strip())
    return STATES.get(m.group(1).upper(), '') if m else ''


def cue_sets(cases: list[dict]) -> dict[str, set[str]]:
    """Docket number -> the words a headline about that case would likely share with it: from its gloss, its
    parties' names and its question presented, keeping only words found in at most two cases' texts, so legal
    vocabulary every case shares drops out and names and subjects ("Kentucky", "AR-15", "climate") stay."""
    texts = {c['docket']: _stems(' '.join([c.get('gloss') or '', ' '.join(party_words(c['raw'])),
                                           c.get('question') or '', origin_state(c.get('from'))])) for c in cases}
    seen = Counter(w for words in texts.values() for w in words)
    return {number: {w for w in words if seen[w] <= 2} for number, words in texts.items()}


# Capitalized words in keywords that aren't names a headline would single a case out by
NOT_NAMES = {'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
             'fourteenth', 'step', 'act', 'amendment', 'amendments', 'clause', 'court', 'courts', 'supreme', 'federal',
             'national', 'title', 'us', 'u.s.', 'american', 'act', 'bill', 'rights', 'circuit', 'appeals'}


def keyword_sets(cases: list[dict]) -> dict[str, dict[str, set[str]]]:
    """Docket number -> {'names': ..., 'subjects': ...}: stems of the words a headline about it would use that no
    other case shares (a case argued alongside it, with the same question, may). Names are the places, parties and
    labels with a capital or a digit (Boulder, Kentucky, AR-15, from the model's keywords, the distinctive party
    names and the state its case came from); subjects are the everyday words (climate, asylum)."""
    names, subjects = {}, {}
    for c in cases:
        phrases = c.get('keywords', [])
        # Within a keyword, the words with a capital or a digit ("Kentucky", "AR-15"), less the ones common in court
        # news whatever the case ("First", "Second", "Congress")
        capitals = [w for k in phrases for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", k)
                    if re.search(r'[A-Z0-9]', w) and w.lower() not in GENERIC | NOT_NAMES]
        # A state is in court news about anything from it, so it's a subject (checked by the model), not a name
        states = _stems(' '.join(set(STATES.values())))
        names[c['docket']] = _stems(' '.join(capitals) + ' ' + ' '.join(party_words(c['raw']))) - states
        subjects[c['docket']] = (_stems(' '.join(k for k in phrases if not re.search(r'[A-Z0-9]', k)) + ' ' +
                                        origin_state(c.get('from'))) |
                                 (_stems(' '.join(capitals)) & states)) - names[c['docket']]
    question = {c['docket']: c.get('question') for c in cases}
    owners = {}
    for group in (names, subjects):
        for number, ws in group.items():
            for w in ws:
                owners.setdefault(w, set()).add(number)

    def own(number, ws):
        return {w for w in ws if all(o == number or (question[o] and question[o] == question[number])
                                     for o in owners[w])}
    return {c['docket']: {'names': own(c['docket'], names[c['docket']]),
                          'subjects': own(c['docket'], subjects[c['docket']])} for c in cases}


def confirm(title: str, case: dict, subject: str = '') -> bool:
    """Whether the headline is about this case (the model; part of the headline's cached verdict). `subject`: a word
    the headline shares with this case only, which the model is told."""
    only = f'It is the only case this term about "{subject}".\n' if subject else ''
    answer = llm.complete_json(CONFIRM_PROMPT.format(title=title, name=case['name'], gloss=case.get('gloss') or '',
                                                     question=(case.get('question') or '')[:400], only=only),
                               CONFIRM_SCHEMA, max_tokens=150)
    return bool(answer and answer.get('refers'))


def judge(row: dict, cache: dict, cases: list[dict] = (), ask: bool = True):
    """The model's reading of one headline (cached by its text, the outlet's country and the case list). None when
    it's unjudged and `ask` is off, or the model gave no answer (asked again next run)."""
    shown = listing(list(cases))
    key = _key(row['title'], row.get('country', ''), shown)
    if key not in cache:
        if not ask:
            return None
        topics = vocabulary(cache)
        schema = {"type": "object", "properties": {
            "reason": {"type": "string"}, "us_supreme_court": {"type": "boolean"},
            "cases": {"type": "array", "items": {"type": "string", "enum": [c['docket'] for c in cases] or ['none']},
                      "maxItems": 6},
            "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "stage": {"type": "string", "enum": STAGES}},
            "required": ["reason", "us_supreme_court", "cases", "topics", "stage"]}
        answer = llm.complete_json(JUDGE_PROMPT.format(
            title=row['title'], outlet=row.get('agency', ''), country=row.get('country', ''), cases=shown or '  (none)',
            topics=', '.join(topics) if topics else '(none yet)', stages=', '.join(STAGES)), schema, max_tokens=250)
        if not answer or 'us_supreme_court' not in answer:
            return None
        known = {c['docket'] for c in cases}
        answer['cases'] = list(dict.fromkeys(d for d in answer.get('cases', []) if d in known))
        answer['topics'] = list(dict.fromkeys(t.strip().lower() for t in answer.get('topics', [])
                                              if t.strip() and t.strip().lower() not in VAGUE))[:3]
        # The first pass suggests; each suggested case is confirmed on its own, since a small model reading a list
        # of thirty cases will match a term preview to half of them
        # Only cases the headline shares a specific word with are confirmed: "Colorado" for the Boulder climate case,
        # "AR-15" for the AR-15 cases; never a guess from the subject area alone
        by_number, cue, keys = {c['docket']: c for c in cases}, cue_sets(list(cases)), keyword_sets(list(cases))
        words = _stems(row['title'])
        answer['suggested'] = answer['cases']
        # A name only one case has ("Boulder", "Kentucky", "AR-15") ties the headline to it outright. A subject only
        # one case is about ("climate") or the model's own suggestion needs a word specific to the case and the
        # model's second look at that case alone
        sure = [d for d in by_number if words & keys[d]['names']]
        maybe = {d: words & keys[d]['subjects'] for d in by_number if d not in sure and words & keys[d]['subjects']}
        maybe.update({d: set() for d in answer['cases'] if d not in sure and d not in maybe and words & cue[d]})
        terms = {d: next((k for k in by_number[d].get('keywords', []) if _stems(k) & hits), '') if hits else ''
                 for d, hits in maybe.items()}
        answer['cases'] = sure + [d for d in maybe if confirm(row['title'], by_number[d], terms[d])]
        cache[key] = {**answer, 'title': row['title'], 'model': llm.model()}
    return cache[key]


def candidates(since: dt) -> list[dict]:
    """Headlines first seen since `since` that name the Court or a justice, newest first, one per outlet and title."""
    with Session() as session:
        rows = session.query(
            Headline.processed, Headline.first_accessed, Agency.name, Agency._bias, Agency.lean_rated, Article.url,  # noqa
            Agency._country, Headline.event_score, Headline.afinn, Headline.vader_compound, Headline.loaded_score,  # noqa
            Headline.emotion_ranks,
        ).join(Headline.article).join(Article.agency).filter(
            Headline.first_accessed > since,
            or_(*[Headline.processed.ilike(f'%{w}%') for w in LIKE]),
        ).order_by(Headline.first_accessed.desc()).all()
    seen, out = set(), []
    for title, first, agency, bias, rated, url, country, event, afinn, vader, loaded, ranks in rows:
        if not title or agency in AGGREGATORS or not CANDIDATE.search(title) or (agency, title) in seen:
            continue
        seen.add((agency, title))
        out.append({'title': title, 'first': first, 'agency': agency, 'bias': bias, 'rated': bool(rated), 'url': url,
                    'country': str(Country(country)) if country is not None else '', 'event_score': event,
                    'afinn': afinn or 0.0, 'vader_compound': vader or 0.0, 'loaded_score': loaded,
                    'emotion_ranks': ranks})
    return out


def side(row: dict) -> str:
    if not row['rated']:
        return 'unrated'
    return 'left' if row['bias'] < 0 else 'right' if row['bias'] > 0 else 'center'


def coverage(now: dt = None) -> dict:
    """The last WINDOW_DAYS of US Supreme Court headlines, by the term's cases they're about (the rest together),
    with how many outlets covered each case, from which side and at which stage."""
    now = now or Config.last_accessed
    cases = docket().get('cases', [])
    add_glosses(cases)
    match = matcher(cases)
    try:
        with open(JUDGMENTS) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    before = len(cache)
    rows = candidates(now - td(days=WINDOW_DAYS))
    asked = 0
    court = []
    shown = listing(cases)
    for row in rows:
        new = _key(row['title'], row.get('country', ''), shown) not in cache
        verdict = judge(row, cache, cases, ask=asked < MAX_NEW_JUDGMENTS)
        asked += new and asked < MAX_NEW_JUDGMENTS
        if verdict and verdict['us_supreme_court']:
            named = match(row['title'])
            on = list(verdict.get('cases', []))
            if named and named['docket'] not in on:
                on.append(named['docket'])
            court.append({**row, 'stage': verdict['stage'], 'topics': verdict.get('topics', []), 'cases': on,
                          'named': named['docket'] if named else None, 'side': side(row)})
    if len(cache) > before:
        with open(JUDGMENTS, 'w') as f:
            json.dump(cache, f)
    logger.info("Supreme Court: %d candidate headlines, %d about the Court; %d newly judged",
                len(rows), len(court), len(cache) - before)

    by_case = {c['docket']: [] for c in cases}
    other = []
    for row in court:
        for number in row['cases']:
            by_case[number].append(row)
        if not row['cases']:
            other.append(row)

    def summary(rows: list[dict]) -> dict:
        one_each = {}
        for r in rows:  # newest first, so each outlet's latest headline
            one_each.setdefault(r['agency'], r)
        return {'outlets': len(one_each), 'sides': dict(Counter(r['side'] for r in one_each.values())),
                'stages': dict(Counter(r['stage'] for r in rows)), 'headlines': rows}
    term_cases = [{**case, **summary(by_case[case['docket']])} for case in cases]
    covered = sorted([c for c in term_cases if c['headlines']], key=lambda c: (-c['outlets'], c['name']))
    topics = Counter(t for r in other for t in r['topics']).most_common()
    return {'term': docket().get('term'), 'source': docket().get('source'), 'covered': covered,
            'cases': term_cases, 'other': {**summary(other), 'topics': topics}, 'total': len(court),
            'window_days': WINDOW_DAYS, 'glosses': {c['docket']: c.get('gloss') for c in cases}}
