import os
import pathlib
import re
from enum import Enum
from datetime import datetime as dt, timedelta as td, timezone as tz


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
    Country.ca: 'Canada'
}

class Constants:
    class Paths:
        ROOT = str(pathlib.Path(__file__).parent.parent)
        EMAIL_CREDS = os.path.join(ROOT, '.creds')

    class Patterns:
        DATE_URL = re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')

    class TimeConstants:
        last_hour = dt.now()
        last_hour = last_hour.replace(hour=last_hour.hour - 1)
        midnight = dt.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = midnight - td(days=1)
        timezone = tz(td(hours=-5))
        now = dt.now(timezone).strftime('%Y-%m-%d %H:%M:%S')
        five_minutes_ago = dt.now() - td(minutes=5)

