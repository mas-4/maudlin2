import os
import pathlib
import re
from datetime import datetime as dt, timedelta as td
from enum import Enum

import pytz


class Bias(Enum):
    extreme_left = -3
    left = -2
    left_center = -1
    unbiased = 0
    right_center = 1
    right = 2
    extreme_right = 3

    def __str__(self):
        return self.name.replace('_', ' ').title()

    @classmethod
    def to_dict(cls):
        return {str(e.value): str(e) for e in cls}


class Credibility(Enum):
    very_low = 0
    low = 1
    mixed = 2
    mostly_factual = 3
    high = 4
    very_high = 5

    def __str__(self):
        return self.name.replace('_', ' ').title()

    @classmethod
    def to_dict(cls):
        return {str(e.value): str(e) for e in cls}


class Country(Enum):
    us = 0
    gb = 1
    qa = 2
    cn = 3
    in_ = 4
    sa = 5
    de = 6
    fr = 7
    jp = 8
    ru = 9
    sg = 10
    ua = 11
    tw = 12
    ca = 13
    au = 14

    def __str__(self):
        return country_pretty[self]


country_pretty = {
    Country.us: 'United States',
    Country.gb: 'Great Britain',
    Country.qa: 'Qatar',
    Country.cn: 'China',
    Country.in_: 'India',
    Country.sa: 'Saudi Arabia',
    Country.de: 'Germany',
    Country.fr: 'France',
    Country.jp: 'Japan',
    Country.ru: 'Russia',
    Country.sg: 'Singapore',
    Country.ua: 'Ukraine',
    Country.tw: 'Taiwan',
    Country.ca: 'Canada',
    Country.au: 'Australia'
}


class Constants:
    class Thresholds:
        topic_score = 0.05
        min_headline_words = 4
        page_repeat_limit = 3  # the same text this many times on one page is navigation

    class Election:
        republican_pattern = r'\b(?:republicans?|gop|trump|vance|maga)\b'
        democrat_pattern = r'\b(?:democrats?|democratic|dems?|jeffries|schumer)\b'
        party_terms = ['Republican', 'GOP', 'Trump', 'Vance', 'MAGA', 'Democrat', 'Dem', 'Jeffries', 'Schumer']

    class Paths:
        ROOT = str(pathlib.Path(__file__).parent.parent.parent)
        EMAIL_CREDS = os.path.join(ROOT, '.creds')
        NETLIFY_CREDS = os.path.join(ROOT, '.netlify_creds')
        DROPBOX_CREDS = os.path.join(ROOT, '.dropbox_creds')
        ANTHROPIC_CREDS = os.path.join(ROOT, '.anthropic_creds')
        TOPICS_FILE = os.path.join(ROOT, 'topics.yml')
        SPECIAL_DATES = os.path.join(ROOT, 'special-dates.yml')
        NEWSINESS_DATA = os.path.join(ROOT, 'newsiness.csv')

    class Patterns:
        SLASH_DATE = re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')
        SLASH_MONTH = re.compile(r'/\d{4}/\d{1,2}/')
        BUNCH_OF_NUMBERS_DOT_HTML = re.compile(r'\d+\.html')
        DASH_DATE = re.compile(r'\d{4}-\d{1,2}-\d{1,2}')
        DASH_BUNCH_OF_NUMBERS = re.compile(r'-\d+$')

    class TimeConstants:
        timezone = pytz.timezone('America/New_York')
        last_hour = dt.now()
        try:
            last_hour = last_hour.replace(hour=last_hour.hour - 1)
        except ValueError:
            last_hour = last_hour.replace(day=last_hour.day - 1, hour=23)
        midnight = dt.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = midnight - td(days=1)
        now = dt.now(timezone).strftime('%Y-%m-%d %H:%M:%S')
        ten_minutes_ago = (dt.now(pytz.UTC) - td(minutes=10)).replace(tzinfo=None)
        twentyfive_minutes_ago = (dt.now(pytz.UTC) - td(minutes=25)).replace(tzinfo=None)

        @staticmethod
        def now_func():
            return dt.now(Constants.TimeConstants.timezone).strftime('%Y-%m-%d %H:%M:%S')

    class Headers:
        class UserAgents:
            maudlin = 'Maudlin Bot'
            # Matches a current desktop Firefox release, for sites that turn away self-identified bots
            firefox = 'Mozilla/5.0 (X11; Linux x86_64; rv:157.0) Gecko/20100101 Firefox/157.0'

        # Some sites want the accept headers a browser sends, not just the user agent
        firefox = {
            'User-Agent': UserAgents.firefox,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

        minimal_set = {
            'Accept': 'text/html',
            'Accept-Language': 'en-US,en;q=0.5',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
        }
