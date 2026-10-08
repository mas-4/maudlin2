"""Newsletters, podcasts and political video channels, collected into the database for the long run (side_item) and,
for the news-of-the-day ones, shown on the front page.

Sources are classified by how they relate to the news cycle, not by format (#135): news-of-the-day sources react to
this week's news, several stories at a time (Pod Save America, Breaking Points, Up First); thinking sources take one
subject at a time, often not tied to the week (The Remnant, Noahpinion). Only `publish` sources appear on the site;
everything is archived.

Polite by design: each feed is read at most every REFRESH, with conditional requests (ETag / Last-Modified, so an
unchanged feed sends nothing back), requests to the same host a few seconds apart, and only the newest items parsed.
A feed that fails just waits for its next turn."""
import os
import time
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td
from urllib.parse import urlparse

import pytz
import requests as rq
from bs4 import BeautifulSoup as Soup
from sqlalchemy.exc import IntegrityError

from app.investigations import _date, _summary
from app.models import Session, SqlLock, SideItem
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

STATE = os.path.join(Config.data, 'sidefeeds_state.json')  # ETag / Last-Modified / last fetch per source
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
REFRESH = td(hours=2)
BIG_FEED = td(hours=6)  # feeds of many megabytes (thousands of items) are read less often
HOST_PAUSE = 5  # seconds between requests to one host (several shows share megaphone, substack, youtube)
HOST_WORKERS = 8  # hosts read at once (each host still one request at a time)
NEWEST = 40  # items parsed per feed (some podcast feeds hold thousands)
YOUTUBE = 'https://www.youtube.com/feeds/videos.xml?channel_id='


def _source(key, name, kind, group, url, publish=False, refresh=None):
    return {'key': key, 'name': name, 'kind': kind, 'group': group, 'url': url, 'publish': publish,
            'refresh': refresh or REFRESH}


# kind: newsletter, podcast, video, call-in, fact-check or satire. group: left, right, center or crossover (a loose lean by reputation, for
# balance and colors; AllSides ratings, where they exist, stay in ratings.csv). publish: news of the day, shown on site
SOURCES = [
    # News of the day (published)
    _source('psa', 'Pod Save America', 'podcast', 'left', 'https://audioboom.com/channels/5166624.rss', True),
    _source('bulwarkpod', 'The Bulwark Podcast', 'podcast', 'left', 'https://audioboom.com/channels/5114286.rss', True),
    _source('hacks', 'Hacks on Tap', 'podcast', 'left', 'https://feeds.megaphone.fm/VMP7545057845', True),
    _source('hcr', 'Letters from an American', 'newsletter', 'left', 'https://heathercoxrichardson.substack.com/feed', True),
    _source('popinfo', 'Popular Information', 'newsletter', 'left', 'https://popular.info/feed', True),
    _source('downballot', 'The Downballot', 'newsletter', 'left', 'https://www.the-downballot.com/feed', True),
    _source('breakingpoints', 'Breaking Points', 'podcast', 'center',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            'e7fd5ae7-7621-4e41-9b85-b0ab0164b634/4c1a5135-4197-47c9-b19b-b0ab0164b667/podcast.rss', True),
    _source('upfirst', 'Up First (NPR)', 'podcast', 'center', 'https://feeds.npr.org/510318/podcast.xml', True),
    _source('nprpolitics', 'NPR Politics Podcast', 'podcast', 'center', 'https://feeds.npr.org/510310/podcast.xml', True),
    _source('ruthless', 'Ruthless', 'podcast', 'right', 'https://feeds.megaphone.fm/FOXM5875505224', True),
    _source('megyn', 'The Megyn Kelly Show', 'podcast', 'right', 'https://feeds.simplecast.com/RV1USAfC', True),
    _source('erickson', 'Erick Erickson', 'newsletter', 'right', 'https://ewerickson.substack.com/feed', True),
    _source('foxrundown', 'Fox News Rundown', 'podcast', 'right', 'https://feeds.megaphone.fm/FOXM1880458659', True),
    _source('yt_hasan', 'Hasan Piker', 'video', 'left', YOUTUBE + 'UCnI_h3e6b5jGLfly2SY57SA', True),
    # YouTube channel ids checked Oct 8 against each channel's handle page (six had gone quiet: moved channels)
    _source('yt_destiny', 'Destiny', 'video', 'left', YOUTUBE + 'UC554eY5jNUfDq3yDOJYirOQ', True),
    _source('yt_vaush', 'Vaush', 'video', 'left', YOUTUBE + 'UCdUD6racxisHiSX9iWFcuug', True),
    _source('yt_majority', 'The Majority Report', 'video', 'left', YOUTUBE + 'UC-3jIAlnQmbbVMV6gR7K8aQ', True),
    _source('yt_pakman', 'David Pakman Show', 'video', 'left', YOUTUBE + 'UCvixJtaXuNdMPUGdOPcY8Ag', True),
    _source('yt_secular', 'Secular Talk', 'video', 'left', YOUTUBE + 'UCldfgbzNILYZA4dmDt4Cd6A', True),
    _source('yt_btc', 'Brian Tyler Cohen', 'video', 'left', YOUTUBE + 'UCR6fEDtZ7_McUwc1fI8_xKw', True),
    _source('yt_meidas', 'MeidasTouch', 'video', 'left', YOUTUBE + 'UCJgZJZZbnLFPr5GJdCuIwpA', True),
    _source('yt_tyt', 'The Young Turks', 'video', 'left', YOUTUBE + 'UC1yBKRuGpC1tSM73A0ZjYjQ', True),
    _source('yt_mockler', 'Adam Mockler', 'video', 'left', YOUTUBE + 'UC8DA4o0SyaGfyVaBLbF5EXg', True),
    _source('yt_timcast', 'Timcast IRL', 'video', 'right', YOUTUBE + 'UCLwNTXWEjVd2qIHLcXxQWxA', True),
    _source('yt_benny', 'Benny Johnson', 'video', 'right', YOUTUBE + 'UCLdP3jmBYe9lAZQbY6OSYjw', True),
    _source('yt_shapiro', 'Ben Shapiro', 'video', 'right', YOUTUBE + 'UCxUQLGMbb2cI8CqiwZ0WhAQ', True),
    # (Dan Bongino's channel retired Oct 8: no uploads since June 2025; The Dan Bongino Show podcast carries him)
    _source('yt_walsh', 'Matt Walsh', 'video', 'right', YOUTUBE + 'UCO01ytfzgXYy4glnPJm4PPQ', True),
    # News outlets' own daily news podcasts (feeds found through Apple's podcast directory, Oct 3)
    _source('reutersworld', 'Reuters World News', 'podcast', 'center', 'https://feeds.megaphone.fm/reutersworldnews', True),
    _source('bbcglobal', 'BBC Global News Podcast', 'podcast', 'center', 'https://podcasts.files.bbci.co.uk/p02nq0gn.rss',
            True),
    _source('wsjwhatsnews', "WSJ What's News", 'podcast', 'center',
            'https://video-api.shdsvc.dowjones.io/api/podcasts/feed/the%20wall%20street%20journal%20whats%20news', True),
    _source('bloombergnow', 'Bloomberg News Now', 'podcast', 'center',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            'd9566f78-0464-4367-9dcc-b05700aeec6f/7f880b3c-7f67-4b4b-b520-b05700af9172/podcast.rss', True),
    _source('politicoplaybook', 'Politico Playbook', 'podcast', 'center', 'https://feeds.megaphone.fm/ASD6963560714',
            True),
    _source('economistintel', 'The Intelligence (Economist)', 'podcast', 'center',
            'https://access.acast.com/rss/d556eb54-6160-4c85-95f4-47d9f5216c49', True),
    _source('cnn5things', 'CNN 5 Things', 'podcast', 'left', 'https://feeds.megaphone.fm/WMHY2007701094', True),
    _source('guardianfocus', 'Today in Focus (Guardian)', 'podcast', 'left',
            'https://www.theguardian.com/news/series/todayinfocus/podcast.xml', True),
    _source('morningwire', 'Morning Wire', 'podcast', 'right', 'https://rss.pdrl.fm/3f8a3d/feeds.megaphone.fm/BVDWV8747925072',
            True),
    # Archived for research
    _source('remnant', 'The Remnant', 'podcast', 'right', 'https://feeds.megaphone.fm/DISPME4897766830'),
    _source('daily', 'The Daily (NYT)', 'podcast', 'center', 'https://feeds.simplecast.com/Sl5CSM3S'),
    _source('todayexplained', 'Today, Explained', 'podcast', 'left', 'https://feeds.megaphone.fm/VMP5705694065'),
    _source('dispatchpod', 'The Dispatch Podcast', 'podcast', 'right', 'https://feeds.megaphone.fm/DISPME9513417677'),
    _source('advisory', 'Advisory Opinions', 'podcast', 'right', 'https://feeds.megaphone.fm/DISPME4573820108'),
    _source('strict', 'Strict Scrutiny', 'podcast', 'left', 'https://audioboom.com/channels/5166629.rss'),
    _source('tucker', 'The Tucker Carlson Show', 'podcast', 'right', 'https://feeds.megaphone.fm/RSV1597324942'),
    _source('warroom', "Bannon's War Room", 'podcast', 'right', 'https://listen.warroom.org/feed.xml'),
    _source('kye', 'Know Your Enemy', 'podcast', 'left', 'https://feeds.simplecast.com/MQHnVVgK'),
    _source('lrc', 'Left, Right & Center', 'podcast', 'center', 'https://leftrightandcenter-feed.kcrw.com'),
    # Ordinary voters in their own words: recorded focus groups (swing and crossover voters), kept for research on how
    # people talk about the news; transcribed from Oct 4 2026 on
    _source('focusgroup', 'The Focus Group', 'podcast', 'crossover', 'https://audioboom.com/channels/5114313.rss'),
    # Jubilee's Surrounded: one guest against 20-25 people who disagree with them, the people speaking for themselves
    # (Oct 6, the user asked for Jubilee; its Middle Ground has no audio feed, and its YouTube feed is now mostly clips)
    _source('surrounded', 'Surrounded (Jubilee)', 'podcast', 'crossover',
            'https://feeds.speakeasystudio.ai/feeds/h2wLC7fJo0Nnyrly/feed.xml'),
    _source('krugman', 'Paul Krugman', 'newsletter', 'left', 'https://paulkrugman.substack.com/feed'),
    _source('silver', 'Silver Bulletin', 'newsletter', 'center', 'https://www.natesilver.net/feed'),
    _source('slowboring', 'Slow Boring', 'newsletter', 'center', 'https://www.slowboring.com/feed'),
    _source('noahpinion', 'Noahpinion', 'newsletter', 'center', 'https://www.noahpinion.blog/feed'),
    _source('persuasion', 'Persuasion', 'newsletter', 'center', 'https://www.persuasion.community/feed'),
    _source('tangle', 'Tangle', 'newsletter', 'center', 'https://www.readtangle.com/feed'),
    _source('dish', 'The Weekly Dish', 'newsletter', 'center', 'https://andrewsullivan.substack.com/feed'),
    _source('racket', 'Racket News', 'newsletter', 'crossover', 'https://www.racket.news/feed'),
    _source('fp', 'The Free Press', 'newsletter', 'right', 'https://www.thefp.com/feed'),
    _source('hanania', 'Richard Hanania', 'newsletter', 'right', 'https://www.richardhanania.com/feed'),
    _source('rufo', 'Christopher F. Rufo', 'newsletter', 'right', 'https://christopherrufo.com/feed'),
    _source('argument', 'The Argument', 'newsletter', 'left', 'https://www.theargumentmag.com/feed'),
    _source('steady', 'Steady (Dan Rather)', 'newsletter', 'left', 'https://steady.substack.com/feed'),
    # Long-form talk on YouTube: archived (Pod Save America's channel duplicates its podcast)
    _source('yt_psa', 'Pod Save America (YouTube)', 'video', 'left', YOUTUBE + 'UC0jYTMDGoHT_Q6HQ7SFtGXg'),
    _source('yt_pbd', 'PBD Podcast', 'video', 'right', YOUTUBE + 'UCIHdDJ0tjn_3j-FS7s_X1kQ'),
    _source('yt_crowder', 'Steven Crowder', 'video', 'right', YOUTUBE + 'UCMAtX9eFBpwc4LtgvbqsOpQ'),
    _source('yt_candace', 'Candace Owens', 'video', 'right', YOUTUBE + 'UCL0u5uz7KZ9q-pe-VC8TY-w'),
    _source('yt_rogan', 'Joe Rogan Experience', 'video', 'crossover', YOUTUBE + 'UCzQUP1qoWDoEbmsQxvdjxgQ'),
    _source('yt_theo', 'Theo Von', 'video', 'crossover', YOUTUBE + 'UC5AQEUAwCh1sGDvkQtkDWUQ'),
    # (Flagrant's channel retired Oct 8: no uploads since January 2024; Flagrant (podcast) carries it)
    _source('yt_dore', 'The Jimmy Dore Show', 'video', 'crossover', YOUTUBE + 'UC3M7l8ved_rYQ45AVzS0RGA'),
    # NPR's 5-minute newscast at the top of every hour: titles are only timestamps and the feed holds the last four,
    # so it's read hourly and archived (its audio links) for transcription later, not shown
    _source('nprnewsnow', 'NPR News Now', 'podcast', 'center', 'https://feeds.npr.org/500005/podcast.xml',
            refresh=td(minutes=55)),
    # ABC's hourly newscast: the feed holds only the latest, so it's read hourly too
    _source('abcupdate', 'ABC News Update', 'podcast', 'center', 'https://feeds.megaphone.fm/ESP9792844572',
            refresh=td(minutes=55)),
    _source('nbctopstory', 'Top Story with Tom Llamas (NBC)', 'podcast', 'center', 'https://podcastfeeds.nbcnews.com/l7QocwtX'),
    _source('ajthetake', 'The Take (Al Jazeera)', 'podcast', 'center',
            'https://www.omnycontent.com/d/playlist/9c074afa-3313-47e8-b802-a9f900789975/'
            '09af2160-238f-48b2-b20b-ad4b00ebd8e7/b86dddc1-67a5-41c2-a13c-ad4b00ebd8f5/podcast.rss'),
    # The streamers' and YouTube shows' own podcast feeds (#158, #164): their audio, which the YouTube channels above
    # only give titles for. Official feeds only (found in Apple's directory by publisher, Oct 4), never fans'
    # re-uploads; archived and transcribed, never shown
    _source('pod_majority', 'The Majority Report (podcast)', 'podcast', 'left', 'https://majorityfm.libsyn.com/rss'),
    _source('pod_pakman', 'David Pakman Show (podcast)', 'podcast', 'left', 'https://feeds.megaphone.fm/SHHWD4599743349'),
    _source('pod_kulinski', 'The Kyle Kulinski Show', 'podcast', 'left', 'https://rss.buzzsprout.com/2035634.rss'),
    _source('pod_btc', 'No Lie with Brian Tyler Cohen', 'podcast', 'left', 'https://rss.art19.com/no-lie'),
    _source('pod_meidas', 'The MeidasTouch Podcast', 'podcast', 'left',
            'https://rss.amperwave.net/v2/feed/audacynetwork/16aa3c6bf526fae9db63070c73cad09f'),
    _source('pod_tyt', 'The Young Turks (podcast)', 'podcast', 'left',
            'https://rss.pdrl.fm/5e32e9/feeds.megaphone.fm/theyoungturks'),
    _source('pod_mockler', 'The Adam Mockler Show', 'podcast', 'left', 'https://audioboom.com/channels/5174578.rss'),
    _source('pod_timcast', 'Timcast IRL (podcast)', 'podcast', 'right',
            'https://rss.libsyn.com/shows/574450/destinations/4973860.xml'),
    _source('pod_benny', 'The Benny Show', 'podcast', 'right', 'https://feeds.megaphone.fm/BENNYMED7549931483'),
    _source('pod_bongino', 'The Dan Bongino Show', 'podcast', 'right', 'https://feeds.megaphone.fm/WWO3519750118'),
    _source('pod_walsh', 'The Matt Walsh Show', 'podcast', 'right',
            'https://rss.pdrl.fm/1fc256/feeds.megaphone.fm/BVDWV7762869899'),
    _source('pod_crowder', 'Louder with Crowder', 'podcast', 'right',
            'https://rss.libsyn.com/shows/576250/destinations/4990850.xml'),
    _source('pod_candace', 'Candace (podcast)', 'podcast', 'right', 'https://feeds.megaphone.fm/candace'),
    _source('pod_pbd', 'PBD Podcast (podcast)', 'podcast', 'right', 'https://anchor.fm/s/2fa50a94/podcast/rss'),
    _source('pod_rogan', 'The Joe Rogan Experience (podcast)', 'podcast', 'crossover',
            'https://feeds.megaphone.fm/GLT1412515089'),
    # Oct 8, the person: Ted Cruz, Charlie Sykes and David Frum (their official feeds, from Apple's directory)
    _source('pod_cruz', 'Verdict with Ted Cruz', 'podcast', 'right',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            '2bee9419-43de-46ce-8996-af2a01167517/84cf551f-a33b-41d8-b112-af2a01167541/podcast.rss', refresh=BIG_FEED),
    _source('pod_sykes', 'To the Contrary with Charlie Sykes', 'podcast', 'left',
            'https://feeds.acast.com/public/shows/67a407e5340a5590cd2953ad'),
    _source('pod_frum', 'The David Frum Show', 'podcast', 'left', 'https://feeds.megaphone.fm/thedavidfrumshow'),
    _source('pod_theo', 'This Past Weekend w/ Theo Von', 'podcast', 'crossover',
            'https://feeds.megaphone.fm/thispastweekend'),
    _source('pod_flagrant', 'Flagrant (podcast)', 'podcast', 'crossover', 'https://feeds.megaphone.fm/APPI6857213837'),
    _source('pod_dore', 'The Jimmy Dore Show (podcast)', 'podcast', 'crossover',
            'https://thejimmydoreshow.libsyn.com/rss'),
    # Call-in shows (#153): ordinary people phoning in about the news, as raw talk for the folklore research; archived
    # and transcribed, never shown. Full shows with callers in free feeds: none on the left (Hartmann's and the
    # Majority Report's caller hours are YouTube-only or for members), so public radio stands in there. iHeart's
    # feeds (omnycontent) are over 10 MB each, so they're read every six hours, not two
    _source('jessekelly', 'The Jesse Kelly Show', 'call-in', 'right',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            '723a5526-8c62-4255-8c8b-ae2c007cfcc1/f2551c6e-95ed-4d33-9cfb-ae2c007cfcf9/podcast.rss', refresh=BIG_FEED),
    _source('claybuck', 'Clay Travis & Buck Sexton', 'call-in', 'right',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            '57c236de-aec0-46c1-b141-ae3c00026d77/1776c4cc-50a1-410f-a2de-ae3c00026dfa/podcast.rss', refresh=BIG_FEED),
    _source('michaelberry', 'The Michael Berry Show', 'call-in', 'right',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            '32ad6995-949b-47b5-bfa5-b2ce01483175/785d2727-e393-40b7-8309-b2ce01483193/podcast.rss', refresh=BIG_FEED),
    _source('levin', 'The Mark Levin Show', 'call-in', 'right', 'https://feeds.megaphone.fm/mark-levin-podcast'),
    _source('lehrer', 'The Brian Lehrer Show (WNYC)', 'call-in', 'center', 'https://feeds.simplecast.com/C8a1jmw4'),
    _source('kqedforum', 'Forum (KQED)', 'call-in', 'center', 'https://feeds.megaphone.fm/KQINC9557381633'),
    _source('onea', '1A (WAMU/NPR)', 'call-in', 'center', 'https://feeds.npr.org/510316/podcast.xml'),
    # Fact-checkers (#153): what claims are circulating and how they were rated, tied to the stories and folklore
    # narratives they check (app/analysis/factchecks.py). All 'center' so they share one neutral color
    _source('politifact', 'PolitiFact', 'fact-check', 'center', 'https://www.politifact.com/rss/factchecks/'),
    _source('factcheckorg', 'FactCheck.org', 'fact-check', 'center', 'https://www.factcheck.org/feed/'),
    _source('snopes', 'Snopes', 'fact-check', 'center', 'https://www.snopes.com/feed/'),
    _source('leadstories', 'Lead Stories', 'fact-check', 'center', 'https://leadstories.com/atom.xml'),
    _source('sciencefeedback', 'Science Feedback', 'fact-check', 'center', 'https://science.feedback.org/feed/'),
    _source('fullfact', 'Full Fact', 'fact-check', 'center', 'https://fullfact.org/feed/'),
    _source('newsguard', 'NewsGuard Reality Check', 'fact-check', 'center', 'https://www.newsguardrealitycheck.com/feed'),
    # Satire (#139): jokes about the news, matched to the stories they joke about (app/analysis/satire.py) and shown
    # only as such, never counted as coverage or in any measure. Leans by reputation
    _source('babylonbee', 'The Babylon Bee', 'satire', 'right', 'https://babylonbee.com/feed'),
    _source('onion', 'The Onion', 'satire', 'left', 'https://theonion.com/feed/'),
    _source('borowitz', 'The Borowitz Report', 'satire', 'left', 'https://www.borowitzreport.com/feed'),
    _source('newyorkerhumor', 'New Yorker humor', 'satire', 'left', 'https://www.newyorker.com/feed/humor'),
    _source('mcsweeneys', "McSweeney's", 'satire', 'left', 'https://feeds.feedburner.com/mcsweeneys'),
    _source('reductress', 'Reductress', 'satire', 'left', 'https://reductress.com/feed/'),
    _source('hardtimes', 'The Hard Times', 'satire', 'left', 'https://thehardtimes.net/feed/'),
    _source('newsthump', 'NewsThump', 'satire', 'left', 'https://newsthump.com/feed/'),
    _source('duffelblog', 'Duffel Blog', 'satire', 'center', 'https://www.duffelblog.com/rss/'),
    _source('clickhole', 'ClickHole', 'satire', 'center', 'https://clickhole.com/feed/'),
]
BY_KEY = {s['key']: s for s in SOURCES}


def parse(xml: str) -> list[dict]:
    """The newest items of an RSS or Atom feed (podcast and YouTube feeds included): title, url, published, summary."""
    soup = Soup(xml, 'xml')
    items = []
    for item in soup.find_all(['item', 'entry'])[:NEWEST]:
        title = item.find('title')
        link = item.find('link')
        url = (link.get('href') or link.get_text(strip=True)) if link is not None else None
        if not url:  # podcast items without a link: their guid or audio file still identifies them
            guid, enclosure = item.find('guid'), item.find('enclosure')
            url = (guid.get_text(strip=True) if guid is not None else None) or \
                  (enclosure.get('url') if enclosure is not None else None)
        when = item.find(['pubDate', 'published', 'updated'])
        summary = item.find(['description', 'summary']) or item.find('media:description')
        if title is None or not url:
            continue
        enclosure = item.find('enclosure')
        audio = enclosure.get('url') if enclosure is not None and 'audio' in (enclosure.get('type') or 'audio') else None
        guid = item.find('guid') or item.find('id')
        items.append({'title': title.get_text(strip=True), 'url': url[:500], 'audio': (audio or '')[:500] or None,
                      'published': _date(when.get_text() if when else None),
                      'summary': _summary(summary.get_text() if summary else '', 400),
                      'guid': (guid.get_text(strip=True) if guid is not None else '') or audio or ''})
    # Some podcast feeds give every episode the show's page as its link (Simplecast, NBC and Dow Jones did from Oct 4:
    # each new episode looked already stored and was dropped, The Daily and the Brian Lehrer Show among them). An item
    # whose link another item shares is told apart by its guid (or audio file), after a # so the link still opens.
    links = Counter(i['url'] for i in items)
    for i in items:
        if links[i['url']] > 1 and i['guid']:
            i['url'] = f"{i['url'].split('#')[0]}#{i['guid']}"[:500]
        del i['guid']
    return items


def _load_state() -> dict:
    return read_json(STATE, {})


def save(source: str, items: list[dict], now: dt) -> int:
    """Store new items (one row per source and url, never overwritten); returns how many were new."""
    new = 0
    with Session() as s, SqlLock:
        known = {u for (u,) in s.query(SideItem.url).filter(SideItem.source == source)}
        for item in items:
            if item['url'] in known:
                continue
            published = dt.fromisoformat(item['published']).replace(tzinfo=None) if item['published'] else None
            s.add(SideItem(source=source, title=item['title'][:500], url=item['url'], published=published,
                           summary=item['summary'], audio=item.get('audio'), first_seen=now))
            known.add(item['url'])
            new += 1
        try:
            s.commit()
        except IntegrityError:  # another run stored them first
            s.rollback()
            return 0
    return new


def _fetch_host(host_sources: list[dict], state: dict) -> list[tuple[dict, dict, list[dict] | None]]:
    """One host's sources in turn, HOST_PAUSE apart: (source, its new state entry, items or None if unchanged or
    failed). Fetching only; the items are saved by the caller, one source at a time."""
    out = []
    for i, src in enumerate(host_sources):
        if i:
            time.sleep(HOST_PAUSE)
        entry = dict(state.get(src['key'], {}))
        headers = {'User-Agent': USER_AGENT}
        if entry.get('etag'):
            headers['If-None-Match'] = entry['etag']
        if entry.get('modified'):
            headers['If-Modified-Since'] = entry['modified']
        items = None
        try:
            response = rq.get(src['url'], headers=headers, timeout=Config.timeout)
            if response.status_code != 304:
                response.raise_for_status()
                items = parse(response.text)
                entry = {'etag': response.headers.get('ETag'), 'modified': response.headers.get('Last-Modified')}
        except Exception as e:  # noqa: BLE001 - one source failing mustn't stop the run; it waits for its next turn
            logger.warning("Side feeds: %s failed (%s)", src['name'], e)
        out.append((src, entry, items))
    return out


def fetch_sidefeeds(force: bool = False):
    """Read every source that's due: the hosts side by side (HOST_WORKERS at once), each host's sources in turn with a
    pause between requests to it, so no host is asked faster than before. Read one after another, the 50 hosts took
    about 5 minutes a run (Oct 7), mostly waiting on YouTube's and Megaphone's two dozen feeds each."""
    from concurrent.futures import ThreadPoolExecutor
    state = _load_state()
    now = dt.now(pytz.UTC)
    due = [src for src in SOURCES if force or not state.get(src['key'], {}).get('fetched')
           or now - dt.fromisoformat(state[src['key']]['fetched']) >= src['refresh']]
    by_host = defaultdict(list)
    for src in due:
        by_host['.'.join(urlparse(src['url']).hostname.split('.')[-2:])].append(src)
    total = 0
    with ThreadPoolExecutor(max_workers=HOST_WORKERS) as pool:
        for fetched in pool.map(lambda sources: _fetch_host(sources, state), by_host.values()):
            for src, entry, items in fetched:
                if items is not None:
                    total += save(src['key'], items, now.replace(tzinfo=None))
                entry['fetched'] = now.isoformat()
                state[src['key']] = entry
    write_json(STATE, state)
    logger.info("Side feeds: read %d sources, %d new items", len(due), total)


def recent(days: int = 3, limit: int = 12, per_source: int = 1) -> list[dict]:
    """The newest items from published sources, newest first, at most `per_source` each."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    published = [s['key'] for s in SOURCES if s['publish']]
    with Session() as s:
        rows = s.query(SideItem).filter(SideItem.source.in_(published), SideItem.published >= since) \
            .order_by(SideItem.published.desc()).all()
        s.expunge_all()
    picked, counts = [], defaultdict(int)
    for row in rows:
        if counts[row.source] >= per_source:
            continue
        counts[row.source] += 1
        src = BY_KEY[row.source]
        picked.append({'title': row.title, 'url': row.url, 'summary': row.summary or '',
                       'published': row.published.replace(tzinfo=pytz.UTC).isoformat(),
                       'source': src['name'], 'kind': src['kind'], 'group': src['group']})
        if len(picked) == limit:
            break
    return picked


def of_kind(kind: str, days: int = 3) -> list[dict]:
    """Every item from sources of this kind (satire, fact-check) from the last `days`, newest first."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    keys = [s['key'] for s in SOURCES if s['kind'] == kind]
    with Session() as s:
        rows = s.query(SideItem).filter(SideItem.source.in_(keys), SideItem.published >= since) \
            .order_by(SideItem.published.desc()).all()
        s.expunge_all()
    return [{'title': row.title, 'url': row.url, 'summary': row.summary or '',
             'published': row.published.replace(tzinfo=pytz.UTC).isoformat(), 'source': BY_KEY[row.source]['name'],
             'group': BY_KEY[row.source]['group']} for row in rows]


def satire(days: int = 3) -> list[dict]:
    return of_kind('satire', days)


def source_for(key: str) -> dict | None:
    return BY_KEY.get(key)
