import os
import pathlib
import re
from enum import Enum
from datetime import datetime as dt, timedelta as td
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

    class Paths:
        ROOT = str(pathlib.Path(__file__).parent.parent.parent)
        EMAIL_CREDS = os.path.join(ROOT, '.creds')
        NETLIFY_CREDS = os.path.join(ROOT, '.netlify_creds')
        DROPBOX_CREDS = os.path.join(ROOT, '.dropbox_creds')
        TOPICS_FILE = os.path.join(ROOT, 'topics.yml')

    class Patterns:
        SLASH_DATE = re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')
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

        @staticmethod
        def now_func():
            return dt.now(Constants.TimeConstants.timezone).strftime('%Y-%m-%d %H:%M:%S')

    class Headers:
        class UserAgents:
            desktop_google_bot = 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/W.X.Y.Z Safari/537.36'
            maudlin = 'Maudlin Bot'
            firefox = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
            chrome = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            edge = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
            safari = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15'
            iphone = 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
            android = 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36'
            ipad = 'Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
            linux = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            windows = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15'

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
