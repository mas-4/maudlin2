"""Headline edits: when an outlet rewrites the headline on an article it has already published.

Every article url can collect several headlines over time. Most pairs aren't edits, so a pair counts only when:

- the old headline stopped appearing before the new one first appeared. Two wordings seen in the same run are
  usually the same article placed twice on a page (a big hero headline and a short sidebar one), not a rewrite;
- both are news (the llm's judgment, when there is one);
- it's a rewrite of the same story: live blogs (one url, a new headline per development) and urls whose two
  headlines share almost no words (reused for another story) are skipped;
- the wording really changed. Changes that only touch case or punctuation, add or drop a kicker ("WEEKEND:",
  "Exclusive —"), or where one version contains the other (truncation, or a change in how we scrape the page)
  are kept apart as minor."""
import difflib
import html
import hashlib
import json
import os
import re
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz
from sqlalchemy import func

from app.models import Session, Headline, Article, Agency
from app.analysis import llm
from app.utils import Config, get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 7
NEWS_THRESHOLD = 0.5

# Labels outlets bolt onto the front or back of a headline without changing what it says: an ALL CAPS tag
# ("WEEKEND:", "HIJACK PROBE"), a stock label ("Exclusive —", "Video:") or an ellipsis
CAPS_KICKER = re.compile(r'^(?:[A-Z][A-Z0-9\s\'’&]{1,30}(?:\s*[:—–|]|\s{2,}))+\s*')
LABEL_KICKER = re.compile(
    r'^(?:(?:exclusive|watch|video|live|breaking|opinion|analysis|updated?)\s*[:—–|-]\s*)+', re.IGNORECASE)
ELLIPSIS = re.compile(r'^[…\s.]+|[…\s.]+$')
LIST_NUMBER = re.compile(r'^\s*\d{1,2}\s*[,.)]\s+')  # a rank from a "most read" list, not part of the headline
VIEW_COUNT = re.compile(r'^\s*[\d.,]+[kKmM]?\s+views\s*:\s*', re.IGNORECASE)  # "114.7k views : "
# Live blogs keep one url and swap in a headline for each new development, so their changes aren't edits
# (an all-caps LIVE tag counts; the plain word "live" doesn't: "Live music returns", "Best cities to live in")
LIVE = re.compile(r'(?-i:\bLIVE\b)|\blive (?:updates?|blog|coverage)\b|\bas it happened\b', re.IGNORECASE)
# Below this share of words in common, the url now carries a different story (reused or rotating), not a rewrite
MIN_OVERLAP = 0.2
WORD = re.compile(r"[\w$%'’]+")


def _words(text: str) -> list[str]:
    return [w.lower().replace('’', "'") for w in WORD.findall(text)]


def _core(text: str) -> list[str]:
    """The words that carry a headline's meaning, without kickers, case or punctuation."""
    text = ELLIPSIS.sub('', LIST_NUMBER.sub('', VIEW_COUNT.sub('', text.strip())))
    return _words(LABEL_KICKER.sub('', CAPS_KICKER.sub('', text)))


def overlap(before: str, after: str) -> float:
    a, b = set(_core(before)), set(_core(after))
    return len(a & b) / max(len(a | b), 1)


def is_minor(before: str, after: str) -> bool:
    a, b = _core(before), _core(after)
    if a == b:
        return True
    joined_a, joined_b = ' '.join(a), ' '.join(b)
    return joined_a in joined_b or joined_b in joined_a


def diff_html(before: str, after: str) -> tuple[str, str]:
    """Both versions as html, with removed words marked <del> in the old one and added words <ins> in the new."""
    old, new = before.split(), after.split()
    matcher = difflib.SequenceMatcher(a=[w.lower() for w in old], b=[w.lower() for w in new], autojunk=False)
    old_html, new_html = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        old_part = html.escape(' '.join(old[i1:i2]))
        new_part = html.escape(' '.join(new[j1:j2]))
        if op == 'equal':
            old_html.append(old_part)
            new_html.append(new_part)
            continue
        if old_part:
            old_html.append(f'<del>{old_part}</del>')
        if new_part:
            new_html.append(f'<ins>{new_part}</ins>')
    return ' '.join(old_html), ' '.join(new_html)


def find_edits(days: int = WINDOW_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(edits, minor): one row per rewrite in the last `days`, newest first."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    columns = {
        'article_id': Headline.article_id, 'title': Headline.title, 'first': Headline.first_accessed,
        'last': Headline.last_accessed, 'news': Headline.news_score, 'event': Headline.event_score,
        'loaded': Headline.loaded_score, 'url': Article.url, 'agency': Agency.name, 'bias': Agency._bias,  # noqa
    }
    with Session() as s:
        rows = s.query(*columns.values()).join(Headline.article).join(Article.agency).filter(
            Headline.last_accessed > since).all()
    df = pd.DataFrame(rows, columns=list(columns))
    df = df[df.groupby('article_id')['title'].transform('nunique') > 1]
    empty = pd.DataFrame()
    if df.empty:
        return empty, empty

    edits, minor = [], []
    for _, group in df.sort_values('first').groupby('article_id'):
        records = group.to_dict('records')
        for old, new in zip(records, records[1:]):
            if old['title'].strip() == new['title'].strip() or old['last'] >= new['first']:
                continue  # same words, or both on the page at once
            if any(r['news'] is not None and r['news'] < NEWS_THRESHOLD for r in (old, new)):
                continue
            if LIVE.search(old['title']) or LIVE.search(new['title']) or overlap(old['title'], new['title']) < MIN_OVERLAP:
                continue  # a live blog or a reused url, not a rewrite
            clean = lambda t: LIST_NUMBER.sub('', VIEW_COUNT.sub('', t.strip())).strip()  # noqa: E731
            old['title'], new['title'] = clean(old['title']), clean(new['title'])
            old_html, new_html = diff_html(old['title'], new['title'])
            row = {
                'agency': new['agency'], 'bias': new['bias'], 'url': new['url'],
                'before': old['title'].strip(), 'after': new['title'].strip(),
                'before_html': old_html, 'after_html': new_html,
                # the change happened between these two scrapes
                'last_seen_before': old['last'], 'first_seen_after': new['first'],
                'event_before': old['event'], 'event_after': new['event'],
                'loaded_before': old['loaded'], 'loaded_after': new['loaded'],
            }
            (minor if is_minor(row['before'], row['after']) else edits).append(row)

    def frame(rows):
        return pd.DataFrame(rows).sort_values('first_seen_after', ascending=False) if rows else empty
    return frame(edits), frame(minor)


def edit_rates(edits: pd.DataFrame, days: int = WINDOW_DAYS, min_headlines: int = 10) -> pd.DataFrame:
    """Edits per 100 headlines for every outlet with at least `min_headlines` headlines in the window, including the
    ones that made none, most-editing first."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    with Session() as s:
        rows = s.query(Agency.name, Agency._bias, func.count(Headline.id)).join(  # noqa prot attr
            Headline.article).join(Article.agency).filter(Headline.first_accessed > since).group_by(Agency.name).all()
    rates = pd.DataFrame(rows, columns=['agency', 'bias', 'headlines'])
    rates = rates[rates['headlines'] >= min_headlines].copy()
    counts = edits.groupby('agency').size() if not edits.empty else pd.Series(dtype=int)
    rates['edits'] = rates['agency'].map(counts).fillna(0).astype(int)
    rates['per_100'] = 100 * rates['edits'] / rates['headlines']
    return rates.sort_values(['per_100', 'edits'], ascending=False)


# What a rewrite changed, judged by the language model looking at both versions side by side. Comparing two separate
# scores (each version scored on its own) mostly measured scoring noise: identical headlines came out "plainer"
JUDGMENTS = os.path.join(Config.data, 'edit_judgments.json')
JUDGE_PROMPT = """A news outlet rewrote a headline.

Before: {before}
After: {after}

change: in under 12 words, what the rewrite changed (e.g. "softened 'slams' to 'criticizes'", "added the death toll",
"named the suspect", "only fixed a typo")
wording: more_loaded (the outlet's own words got more emotional or judgmental), plainer, or same
news: better (the event now sounds better for the people involved), worse, or same"""
JUDGE_SCHEMA = {"type": "object", "properties": {
    "change": {"type": "string", "maxLength": 100},
    "wording": {"type": "string", "enum": ["more_loaded", "plainer", "same"]},
    "news": {"type": "string", "enum": ["better", "worse", "same"]}},
    "required": ["change", "wording", "news"]}


def judge_edits(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """(before, after) -> {change, wording, news}, from a cache of earlier judgments; new pairs are judged once."""
    try:
        with open(JUDGMENTS) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    key = lambda b, a: hashlib.sha1(f'{b}\n{a}'.encode()).hexdigest()  # noqa: E731
    fresh = 0
    for before, after in pairs:
        k = key(before, after)
        if k in cache or llm.backend() is None:
            continue
        answer = llm.complete_json(JUDGE_PROMPT.format(before=before, after=after), JUDGE_SCHEMA, max_tokens=80)
        if answer:
            cache[k] = {**answer, 'model': llm.model()}
            fresh += 1
    if fresh:
        with open(JUDGMENTS, 'w') as f:
            json.dump(cache, f)
        logger.info("Judged %d new headline changes", fresh)
    return {(b, a): cache[key(b, a)] for b, a in pairs if key(b, a) in cache}
