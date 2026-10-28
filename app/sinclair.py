"""Sinclair's local stations and The National Desk, read from their homepages for research (Oct 28). The question is
the "barbell": an outlet running mostly straight news around a small share of centrally made pieces, as Sinclair's
must-runs sit inside otherwise local news. A study reads each headline; this keeps what it needs.

The National Desk (TND), Sinclair's national news, is an ordinary outlet: its headlines are saved and join stories.
The stations are kept for research only. Their national pieces are TND's copy (the same piece, on the same slug, on
every station that runs it), so counting each station as an outlet would make one syndicated piece look like five
outlets on a story, and five mostly local front pages would also thin every "share of outlets" measure. So a
station's homepage headlines are saved as StationSightings under the station, never as Headlines: they stay out of
stories, lean bars, outlet counts and the outlets' pages, and the stations aren't in registry.Scrapers.

Every sighting keeps its station, link, wording, place and times, and nothing is dropped because another site saved
the same headline first (the front-page scrapers' dedupe is by wording across outlets). TND's own homepage is kept as
sightings too, so `sightings()` can say for each station headline whether TND's homepage ran the same piece, and on
how many of our Sinclair sites it appeared."""
import re
from datetime import datetime as dt
from urllib.parse import urlsplit

import pandas as pd
import pytz
from bs4 import BeautifulSoup as Soup, Tag

from app import scraper_health
from app.models import Session, SqlLock, StationSighting, Agency
from app.scraper import Scraper
from app.utils import get_logger

logger = get_logger(__name__)

NATIONAL_DESK = 'The National Desk'
# Class names carry a build hash (TeaserLink_teaserText__g1DQc), so they're matched by their stable start
STATION_TEASER = re.compile(r'^TeaserLink_teaserLink__')
STATION_TITLE = re.compile(r'^TeaserLink_teaserText__')
TND_TITLE = re.compile(r'^index-module_title__')
SKIP_PATHS = ('/sponsored/',)  # paid posts, not the station's news


def slug(url: str) -> str:
    """The piece a link names: its path's last part, lowercased. Sinclair's sites share one system, so a syndicated
    piece keeps its slug from site to site (komonews.com/news/nation-world/x,
    thenationaldesk.com/news/americas-news-now/x)."""
    parts = [p for p in urlsplit(url).path.split('/') if p]
    return parts[-1].lower()[:255] if parts else ''


def section(url: str) -> str:
    """The link's section, its path without the slug: 'news/nation-world', 'news/local'"""
    parts = [p for p in urlsplit(url).path.split('/') if p]
    return '/'.join(parts[:-1])


def _text(tag: Tag) -> str:
    # WJLA's headlines sometimes start with a byte-order mark (\ufeffCollege Park's…), invisible but not equal
    return re.sub(r'\s+', ' ', tag.get_text(' ', strip=True).replace('\ufeff', '').replace('\u200b', '')).strip()


def station_items(soup: Soup, home: str) -> list[tuple[str, str]]:
    """(link, headline) for each story teaser on a Sinclair station's homepage, top to bottom, each link once. The
    teaser's headline only, not the summary that comes with it; links lose their query (?teaserSource=trending marks
    the sidebar's repeats); sponsored posts are left out."""
    out, seen = [], set()
    for a in soup.find_all('a', href=True, class_=STATION_TEASER):
        title = a.find(class_=STATION_TITLE)
        if title is None:
            continue
        url = _absolute(a['href'], home)
        text = _text(title)
        if not text or url in seen or any(p in urlsplit(url).path for p in SKIP_PATHS):
            continue
        seen.add(url)
        out.append((url, text))
    return out


def national_desk_items(soup: Soup, home: str) -> list[tuple[str, str, Tag]]:
    """(link, headline, the headline's tag) for each story on The National Desk's homepage, top to bottom"""
    out, seen = [], set()
    for a in soup.find_all('a', href=True):
        title = a.find(class_=TND_TITLE)
        if title is None:
            continue
        url = _absolute(a['href'], home)
        text = _text(title)
        if text and url not in seen:
            seen.add(url)
            out.append((url, text, title))
    return out


def _absolute(href: str, home: str) -> str:
    href = href.strip()
    if href.startswith('//'):
        href = 'https:' + href
    elif not href.startswith('http'):
        href = home.rstrip('/') + '/' + href.lstrip('/')
    return href.split('?')[0].split('#')[0]


def record(agency_id: int, items: list[tuple[str, str]], now: dt = None) -> int:
    """Save one homepage read: (link, headline) top to bottom. Returns how many were new. A link seen again keeps its
    first sighting and its highest place; a new wording of it is a row of its own."""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    new = 0
    with Session() as s, SqlLock:
        rows = {(r.url, r.title): r for r in s.query(StationSighting).filter(
            StationSighting.agency_id == agency_id, StationSighting.url.in_([u for u, _ in items]))}
        for position, (url, title) in enumerate(items):
            row = rows.get((url, title))
            if row is None:
                row = StationSighting(agency_id=agency_id, url=url, slug=slug(url), title=title, position=position,
                                      first_seen=now)
                s.add(row)
                rows[(url, title)] = row
                new += 1
            row.position = min(row.position, position)
            row.last_seen = now
        s.commit()
    return new


class StationScraper(Scraper):
    """A Sinclair station's homepage, kept for research: its headlines are StationSightings, never Headlines (see the
    module's note). One request a run, like any front page. Not in registry.Scrapers; main runs ResearchScrapers too."""
    market: str = ''

    def __init__(self):
        super().__init__()
        self.sightings: list[tuple[str, str]] = []

    def setup(self, soup: Soup):
        self.sightings = station_items(soup, self.url)

    def post_run(self):
        self.found = len(self.sightings)
        new = record(self.agency_id, self.sightings)
        bugle = logger.info if self.found else logger.warning
        bugle("%s (research only): %d headlines on its homepage, %d new", self.agency, self.found, new)
        scraper_health.record(self.agency, self.url, found=self.found, kept=self.found, added=new)


def sightings(since: dt = None) -> pd.DataFrame:
    """Every Sinclair sighting (stations and The National Desk), for the study: outlet, url, section, slug, title,
    position, first_seen, last_seen, and per piece (slug), over all our sightings:
      national_desk: The National Desk's own homepage ran it. Strict: TND's homepage shows about 20 pieces at a
        time, so a TND piece that never reached it reads False here (the `sites` count still catches it).
      sites: how many of our Sinclair sites (stations and TND) ran it. Two or more is syndicated, but not always
        made centrally: neighbouring stations (WJLA and WBFF, Washington and Baltimore) share regional pieces, so
        look at `section` (news/local or news/nation-world) as well.
    `since` keeps the rows last seen from then (naive UTC); the flags still look at every sighting."""
    with Session() as s:
        rows = s.query(Agency.name, StationSighting.url, StationSighting.slug, StationSighting.title,
                       StationSighting.position, StationSighting.first_seen, StationSighting.last_seen) \
            .join(Agency, Agency.id == StationSighting.agency_id).all()
    cols = ['outlet', 'url', 'slug', 'title', 'position', 'first_seen', 'last_seen']
    df = pd.DataFrame(rows, columns=cols)
    df.insert(2, 'section', df['url'].map(section) if not df.empty else pd.Series(dtype=str))
    on_tnd = set(df.loc[df['outlet'] == NATIONAL_DESK, 'slug'])
    df['national_desk'] = df['slug'].isin(on_tnd)
    df['sites'] = df.groupby('slug')['outlet'].transform('nunique') if not df.empty else pd.Series(dtype=int)
    if since is not None:
        df = df[df['last_seen'] >= since]
    return df.reset_index(drop=True)
