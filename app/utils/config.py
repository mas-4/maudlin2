import logging
import os
from datetime import datetime as dt, timedelta as td
from random import random
from typing import Any

import yaml

from app.utils.constants import Constants


def read_creds(path):
    if os.path.exists(path):
        with open(path, 'rt') as f_in:
            return f_in.read().strip()
    return ''


class SpecialDate:
    def __init__(self, rawdict: dict[str, Any]):
        self.name: str = rawdict['name']
        self.date: dt = rawdict['date']  # had no idea yaml automatically converted this
        self.topic: str = rawdict['topic']


class Config:
    use_color = True
    logging_level = logging.INFO
    debug: bool = False
    site_name = 'Maudlin'
    strf = '%Y-%m-%d %H:%M:%S'
    run_selenium = True
    timeout = 15  # seconds for requests

    # We want to exclude perpetual links that are not distinguishable by html (like on Drudge) but capture articles
    # that have sat on the web page for days, like on Current Affairs. The age of the database is the primary filter
    # here. So resets cause drudge to get dumb.
    first_accessed = dt.now() - td(days=3)
    last_accessed = Constants.TimeConstants.twentyfive_minutes_ago
    exempted_foreign_media = ["The Economist", "BBC", "The Guardian", "Financial Times", "Reuters", "The Independent"]
    headline_cutoff = 128

    output_dir = os.path.join(Constants.Paths.ROOT, 'data')
    log_file = f'{output_dir}/app.log'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    dayreport_file = os.path.join(output_dir, 'day-report.json')
    assets = os.path.join(Constants.Paths.ROOT, 'app', 'site', 'static')
    build = os.path.join(Constants.Paths.ROOT, 'build')
    if not os.path.exists(build):
        os.makedirs(build)

    db_file_name = 'data.db'
    db_file_path = str(os.path.join(output_dir, db_file_name))
    connection_string = 'sqlite:///' + db_file_path
    newsletter = os.path.join(output_dir, 'newsletter.html')

    @staticmethod
    def time_between_requests() -> float:  # this is a function so that we can make it random if necessary
        return random() * 2 + 2

    emails = []
    email = ''
    pw = ''
    domain = ''

    if os.path.exists(Constants.Paths.EMAIL_CREDS):
        with open(Constants.Paths.EMAIL_CREDS, 'rt') as f_in:
            emails, domain, email, pw = f_in.read().strip().splitlines()
            emails_to_notify = emails.split(',')

    netlify = read_creds(Constants.Paths.NETLIFY_CREDS)
    dropbox = read_creds(Constants.Paths.DROPBOX_CREDS)

    with open(Constants.Paths.SPECIAL_DATES, 'rt') as f_in:
        special_dates = [SpecialDate(x) for x in yaml.safe_load(f_in)]
        special_dates.sort(key=lambda x: x.date)
