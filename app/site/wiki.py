"""A little background on each outlet: the opening sentences of its English Wikipedia article (quoted, not
rewritten, CC BY-SA 4.0) and a few facts from Wikidata (CC0): owner, parent organization, founded, country,
headquarters. Articles are matched by hand in outlet_wiki.csv.

Polite by design: Wikipedia's API returns 20 articles' openings per request and Wikidata 50 items per request, so
the whole list is about a dozen requests, spaced out, refreshed weekly and cached in data/outlet_wiki.json."""
import csv
import json
import os
import time
from datetime import datetime as dt, timedelta as td
from typing import Optional

import pytz
import requests as rq

from app.utils import Config, Constants, get_logger

logger = get_logger(__name__)

MAPPING = os.path.join(Constants.Paths.ROOT, 'outlet_wiki.csv')
CACHE = os.path.join(Config.data, 'outlet_wiki.json')
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
WIKIPEDIA_API = 'https://en.wikipedia.org/w/api.php'
WIKIDATA_API = 'https://www.wikidata.org/w/api.php'
REFRESH = td(days=7)
PAUSE = 5  # seconds between requests
SENTENCES = 2
# Wikidata properties shown on the outlets page
FACTS = {'P127': 'owner', 'P749': 'parent', 'P571': 'founded', 'P17': 'country', 'P159': 'headquarters'}


def mapping() -> dict[str, str]:
    """Outlet name -> Wikipedia article title (outlets with a blank title have no article)."""
    with open(MAPPING, newline='') as f:
        rows = csv.DictReader(line for line in f if not line.startswith('#'))
        return {r['outlet']: r['wikipedia'].strip() for r in rows if r['wikipedia'].strip()}


def _get(url: str, **params) -> dict:
    response = rq.get(url, params={'format': 'json', **params}, headers={'User-Agent': USER_AGENT},
                      timeout=Config.timeout)
    response.raise_for_status()
    time.sleep(PAUSE)
    return response.json()


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def openings(titles: list[str]) -> dict[str, dict]:
    """Requested title -> {title, extract, qid} from Wikipedia, following redirects; missing and disambiguation pages
    are left out."""
    found = {}
    for batch in _chunks(titles, 20):
        data = _get(WIKIPEDIA_API, action='query', formatversion=2, redirects=1, prop='extracts|pageprops',
                    exintro=1, explaintext=1, exsentences=SENTENCES, exlimit=20,
                    ppprop='wikibase_item|disambiguation', titles='|'.join(batch))['query']
        # Requested title -> final title, through normalization and redirects
        hops = {h['from']: h['to'] for h in data.get('normalized', []) + data.get('redirects', [])}
        pages = {p['title']: p for p in data.get('pages', [])}
        for title in batch:
            final = title
            while final in hops:
                final = hops[final]
            page = pages.get(final)
            if not page or page.get('missing') or 'disambiguation' in page.get('pageprops', {}):
                logger.warning("Outlet wiki: no usable article for %r", title)
                continue
            found[title] = {'title': page['title'], 'extract': (page.get('extract') or '').strip(),
                            'qid': page.get('pageprops', {}).get('wikibase_item')}
    return found


def _claim_values(entity: dict, prop: str) -> list:
    """A property's current values: past ones (with an end date) and deprecated ones are dropped, and when some are
    marked preferred, only those count."""
    claims = [c for c in entity.get('claims', {}).get(prop, [])
              if c.get('rank') != 'deprecated' and 'P582' not in c.get('qualifiers', {})]
    if any(c.get('rank') == 'preferred' for c in claims):
        claims = [c for c in claims if c.get('rank') == 'preferred']
    values = []
    for claim in claims:
        value = claim.get('mainsnak', {}).get('datavalue', {}).get('value')
        if isinstance(value, dict) and 'id' in value:
            values.append(value['id'])
        elif isinstance(value, dict) and 'time' in value:
            values.append(value['time'].lstrip('+')[:4])  # the year
    return values


def facts(qids: list[str]) -> dict[str, dict]:
    """QID -> {owner: [...], parent: [...], founded: '1801', country: [...], headquarters: [...]} with labels."""
    raw = {}
    for batch in _chunks(qids, 50):
        entities = _get(WIKIDATA_API, action='wbgetentities', ids='|'.join(batch), props='claims')['entities']
        for qid, entity in entities.items():
            raw[qid] = {key: _claim_values(entity, prop) for prop, key in FACTS.items()}
    referenced = sorted({v for f in raw.values() for k, vs in f.items() if k != 'founded' for v in vs})
    labels = {}
    for batch in _chunks(referenced, 50):
        entities = _get(WIKIDATA_API, action='wbgetentities', ids='|'.join(batch), props='labels',
                        languages='en')['entities']
        labels.update({qid: e.get('labels', {}).get('en', {}).get('value') for qid, e in entities.items()})
    out = {}
    for qid, f in raw.items():
        out[qid] = {k: [labels[v] for v in vs if labels.get(v)] for k, vs in f.items() if k != 'founded'}
        out[qid]['founded'] = min(f['founded']) if f['founded'] else None
    return out


def _load() -> dict:
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def refresh(force: bool = False) -> None:
    """Fetch every mapped outlet's opening and facts, at most weekly. A failure keeps the last good cache."""
    cache = _load()
    fetched = cache.get('fetched')
    if not force and fetched and dt.now(pytz.UTC) - dt.fromisoformat(fetched) < REFRESH:
        return
    titles = mapping()
    try:
        found = openings(sorted(set(titles.values())))
        known = facts(sorted({p['qid'] for p in found.values() if p['qid']}))
    except Exception as e:  # noqa: background info must never take down a run
        logger.warning("Outlet wiki refresh failed (%s); keeping the last copy", e)
        return
    outlets = {}
    for outlet, title in titles.items():
        page = found.get(title)
        if page:
            outlets[outlet] = {**page, **known.get(page['qid'], {}),
                               'url': 'https://en.wikipedia.org/wiki/' + page['title'].replace(' ', '_')}
    with open(CACHE, 'w') as f:
        json.dump({'fetched': dt.now(pytz.UTC).isoformat(), 'outlets': outlets}, f)
    logger.info("Outlet wiki: %d of %d outlets", len(outlets), len(titles))


def info(name: str) -> Optional[dict]:
    """The cached background for one outlet, or None."""
    return _load().get('outlets', {}).get(name)


def all_info() -> dict[str, dict]:
    return _load().get('outlets', {})
