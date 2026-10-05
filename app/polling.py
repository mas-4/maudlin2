"""Polling averages computed from VoteHub's raw poll feed (CC BY 4.0, https://votehub.com/polls/api/).

We average the polls ourselves rather than republishing someone else's average, so the method is ours to
explain: recent polls count more, bigger samples count more (with diminishing returns), likely and
registered voter polls count more than all-adult polls, partisan-sponsored polls are left out, and a
pollster that publishes often has its weight split across its polls so it can't drown out the others."""
import io
import json
import os
import re
import time
from datetime import date, timedelta as td
from typing import Optional

import numpy as np
import pandas as pd
import requests as rq

from app.utils import Config, Constants, get_logger
from app.utils.store import write_json

logger = get_logger(__name__)

POLLS_URL = 'https://api.votehub.com/polls'
POLLS_FILE = os.path.join(Config.data, 'polls.json')
REFRESH_SECONDS = 60 * 60  # polls trickle in a few a day; hourly is plenty

WINDOW_DAYS = 45
HALF_LIFE_DAYS = 14
TYPICAL_SAMPLE = 600
SAMPLE_CAP = 3000
POPULATION_WEIGHTS = {'lv': 1.0, 'rv': 1.0, 'v': 1.0, 'a': 0.7}
SERIES_DAYS = 180
RACE_WINDOW_DAYS = 60
MIN_RACE_POLLS = 2
# Below this many polls in the window our own national average is too thin to chart. VoteHub's approval and
# generic ballot coverage stopped in July 2026, so until it recovers the page leans on the published averages.
MIN_CHART_POLLS = 15

# Published polling averages, as tabulated (with sources) on Wikipedia, CC BY-SA 4.0
WIKIPEDIA_API = 'https://en.wikipedia.org/w/api.php'
WIKIPEDIA_UA = 'Maudlin Bot (https://maudlin.news)'
AGGREGATES_FILE = os.path.join(Config.data, 'aggregates.json')
AGGREGATE_PAGES = {
    'approval': 'Opinion_polling_on_the_second_Trump_presidency',
    'generic': '2026_United_States_House_of_Representatives_elections',
}


def fetch_polls(force: bool = False):
    """Refresh the local copy of the poll feed if it's older than REFRESH_SECONDS. Never raises."""
    if not force and os.path.exists(POLLS_FILE) and time.time() - os.path.getmtime(POLLS_FILE) < REFRESH_SECONDS:
        return
    try:
        response = rq.get(POLLS_URL, timeout=Config.timeout,
                          headers={'User-Agent': Constants.Headers.UserAgents.maudlin})
        response.raise_for_status()
        polls = response.json()
    except Exception as e:  # noqa
        logger.error("Failed to fetch polls: %s", e)
        return
    write_json(POLLS_FILE, polls)
    logger.info("Fetched %d polls from VoteHub", len(polls))


def _clean(cell) -> str:
    return re.sub(r'\[[^]]*]', '', str(cell)).strip()


def _percent(cell) -> Optional[float]:
    match = re.search(r'-?\d+(\.\d+)?', _clean(cell).replace('\u2212', '-'))
    return float(match.group()) if match else None


def _aggregate_table(html: str, required: set[str]) -> list[dict]:
    """Rows of the first table naming poll aggregators that has all the `required` columns."""
    for table in pd.read_html(io.StringIO(html)):
        columns = {str(c): c for c in table.columns}
        first = str(table.columns[0]).lower()
        if 'aggregat' not in first or not required <= set(columns):
            continue
        rows = []
        for _, row in table.iterrows():
            source = _clean(row.iloc[0])
            if not source or source.lower() in ('average', 'nan'):
                continue
            rows.append({'source': source, **{name: _percent(row[columns[name]]) for name in required}})
        return rows
    return []


def fetch_aggregates(force: bool = False):
    """Refresh the published approval and generic ballot averages from Wikipedia. Never raises."""
    if not force and os.path.exists(AGGREGATES_FILE) and \
            time.time() - os.path.getmtime(AGGREGATES_FILE) < REFRESH_SECONDS:
        return
    required = {'approval': {'Approve', 'Disapprove'}, 'generic': {'Democrats', 'Republicans'}}
    aggregates = {}
    for key, page in AGGREGATE_PAGES.items():
        try:
            response = rq.get(WIKIPEDIA_API, timeout=Config.timeout, headers={'User-Agent': WIKIPEDIA_UA}, params={
                'action': 'parse', 'page': page, 'prop': 'text', 'format': 'json', 'formatversion': 2})
            response.raise_for_status()
            rows = _aggregate_table(response.json()['parse']['text'], required[key])
        except Exception as e:  # noqa
            logger.error("Failed to fetch %s aggregates: %s", key, e)
            return
        if not rows:
            logger.warning("No %s aggregate table found on %s; the page layout may have changed", key, page)
            return
        aggregates[key] = {'page': page, 'rows': rows}
    write_json(AGGREGATES_FILE, aggregates)
    logger.info("Fetched published averages: %s", {k: len(v['rows']) for k, v in aggregates.items()})


def load_polls() -> pd.DataFrame:
    """One row per poll answer: poll metadata plus `choice` and `pct`."""
    if not os.path.exists(POLLS_FILE):
        return pd.DataFrame()
    with open(POLLS_FILE, 'rt') as f:
        polls = json.load(f)
    rows = [{**{k: p[k] for k in ('id', 'poll_type', 'subject', 'pollster', 'sample_size', 'population',
                                  'end_date', 'partisan', 'url')},
             'choice': a['choice'], 'pct': a['pct']}
            for p in polls for a in p['answers']]
    df = pd.DataFrame(rows)
    df['end_date'] = pd.to_datetime(df['end_date']).dt.date
    # The feed occasionally carries a typo'd future field date; a poll can't have finished yet
    return df[(df['end_date'] <= date.today()) & df['partisan'].isna()]


def poll_weights(polls: pd.DataFrame, as_of: date) -> pd.Series:
    """Weight for each poll (one row per poll) as of a given day."""
    age = polls['end_date'].map(lambda d: (as_of - d).days)
    recency = 0.5 ** (age / HALF_LIFE_DAYS)
    sample = np.sqrt(polls['sample_size'].fillna(TYPICAL_SAMPLE).clip(upper=SAMPLE_CAP) / TYPICAL_SAMPLE)
    population = polls['population'].map(POPULATION_WEIGHTS).fillna(0.85)
    per_pollster = 1 / polls.groupby('pollster')['id'].transform('count')
    return recency * sample * population * per_pollster


def weighted_average(answers: pd.DataFrame, as_of: date, window: int = WINDOW_DAYS) -> dict[str, float]:
    """Weighted mean share for each choice across polls that ended in the window before `as_of`."""
    recent = answers[(answers['end_date'] <= as_of) & (answers['end_date'] > as_of - td(days=window))]
    if recent.empty:
        return {}
    polls = recent.drop_duplicates('id').set_index('id')
    weights = poll_weights(polls.reset_index(), as_of).set_axis(polls.index)
    table = recent.pivot_table(index='id', columns='choice', values='pct')
    w = weights.reindex(table.index)
    return {choice: float(np.average(table[choice].dropna(), weights=w[table[choice].notna()]))
            for choice in table.columns if table[choice].notna().any()}


def margins(answers: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """Collapse each poll's two answers into one `Margin` row (a minus b), keeping the poll metadata."""
    table = answers.pivot_table(index='id', columns='choice', values='pct')
    margin = (table[a] - table[b]).dropna().rename('pct')
    meta = answers.drop_duplicates('id').set_index('id').drop(columns=['choice', 'pct'])
    return meta.join(margin, how='inner').reset_index().assign(choice='Margin')


def average_series(answers: pd.DataFrame, choices: list[str]) -> pd.DataFrame:
    """Daily average for each choice over the last SERIES_DAYS days."""
    today = date.today()
    rows = []
    for offset in range(SERIES_DAYS, -1, -1):
        day = today - td(days=offset)
        avg = weighted_average(answers, day)
        if all(c in avg for c in choices):
            rows.append({'date': day, **{c: avg[c] for c in choices}})
    return pd.DataFrame(rows)


class Polling:
    """Everything the polling page needs, computed once per build."""

    def __init__(self):
        df = load_polls()
        self.available = not df.empty
        if not self.available:
            logger.warning("No poll data at %s", POLLS_FILE)
            return
        generic = df[(df['poll_type'] == 'generic-ballot') & df['choice'].isin(['Dem', 'Rep'])]
        approval = df[(df['poll_type'] == 'approval') & (df['subject'] == 'Donald Trump')
                      & df['choice'].isin(['Approve', 'Disapprove'])]
        # Some generic ballot polls force a two-way choice and some allow undecided, so their levels aren't
        # comparable; the margin is
        self.generic = average_series(margins(generic, 'Dem', 'Rep'), ['Margin'])
        self.approval = average_series(approval, ['Approve', 'Disapprove'])
        self.generic_polls = generic['id'].nunique()
        self.approval_polls = approval['id'].nunique()
        self.senate = self.races(df[df['poll_type'] == 'us-senator'])
        self.updated = df['end_date'].max()
        recent = date.today() - td(days=WINDOW_DAYS)
        self.generic_recent = generic[generic['end_date'] > recent]['id'].nunique()
        self.approval_recent = approval[approval['end_date'] > recent]['id'].nunique()
        self.chart_generic = self.generic_recent >= MIN_CHART_POLLS and not self.generic.empty
        self.chart_approval = self.approval_recent >= MIN_CHART_POLLS and not self.approval.empty
        self.aggregates = self.published_averages()

    @staticmethod
    def published_averages() -> dict:
        """Each published average plus their mean, for approval and the generic ballot."""
        if not os.path.exists(AGGREGATES_FILE):
            return {}
        with open(AGGREGATES_FILE, 'rt') as f:
            aggregates = json.load(f)
        for key, (a, b) in {'approval': ('Approve', 'Disapprove'), 'generic': ('Democrats', 'Republicans')}.items():
            if key not in aggregates:
                continue
            rows = [r for r in aggregates[key]['rows'] if r[a] is not None and r[b] is not None]
            for r in rows:
                r['margin'] = round(r[a] - r[b], 1)
            aggregates[key]['rows'] = rows
            aggregates[key]['mean'] = {col: round(float(np.mean([r[col] for r in rows])), 1)
                                       for col in (a, b, 'margin')} if rows else None
        return aggregates

    @staticmethod
    def races(answers: pd.DataFrame) -> list[dict]:
        """Current average for each Senate race with enough recent polling, closest races first."""
        today = date.today()
        races = []
        for subject, group in answers.groupby('subject'):
            recent = group[group['end_date'] > today - td(days=RACE_WINDOW_DAYS)]
            if recent.empty:
                continue
            # The newest poll defines the matchup; older polls without both of its leaders are primary polls
            newest = recent[recent['id'] == recent.sort_values('end_date')['id'].iloc[-1]]
            matchup = set(newest.nlargest(2, 'pct')['choice'])
            has_both = recent.groupby('id')['choice'].transform(lambda c: matchup <= set(c))
            recent = recent[has_both & recent['choice'].isin(matchup)]
            if recent['id'].nunique() < MIN_RACE_POLLS:
                continue
            avg = weighted_average(recent, today, RACE_WINDOW_DAYS)
            top = sorted(avg.items(), key=lambda kv: kv[1], reverse=True)[:2]
            if len(top) < 2:
                continue
            (leader, lead_pct), (trailer, trail_pct) = top
            races.append({
                'state': subject.replace('2026 ', ''),
                'leader': leader, 'leader_pct': round(lead_pct, 1),
                'trailer': trailer, 'trailer_pct': round(trail_pct, 1),
                'margin': round(lead_pct - trail_pct, 1),
                'polls': int(recent['id'].nunique()),
                'latest': recent['end_date'].max(),
            })
        return sorted(races, key=lambda r: r['margin'])
