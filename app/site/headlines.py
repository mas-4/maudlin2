import os
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz

from app.models import Session, Headline
from app.queries import Queries
from app.site import j2env
from app.site.common import calculate_xkeyscore
from app.utils.config import Config
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class HeadlinesPage:
    template = j2env.get_template('headlines.html')

    def generate(self):
        logger.info("Generating headlines page...")
        with Session() as s:
            headline_df = self.get_headlines(s)
        urls = headline_df.set_index('title')['url'].to_dict()
        headline_df = headline_df[
            ['title', 'first_accessed', 'last_accessed', 'position', 'score', 'vader_compound', 'afinn']
        ]
        headline_df.sort_values(by='score', ascending=False, inplace=True)
        with open(os.path.join(Config.build, 'headlines.html'), 'wt') as f:
            f.write(self.template.render(
                title='Headlines',
                tabledata=headline_df.values.tolist(),
                urls=urls,
            ))
        logger.info("...done")

    @staticmethod
    def get_headlines(s):
        headlines: list[Headline] = Queries.get_current_headlines(s).order_by(
            Headline.position.asc(),  # prominence
            Headline.first_accessed.desc()
        ).all()

        df = pd.DataFrame([[
            h.title,
            h.article.agency.name,
            h.first_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone).strftime(
                '%b %-d %-I:%M %p'),
            h.last_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone).strftime(
                '%-I:%M %p'),
            h.position,
            round(h.vader_compound, 2),
            round(h.afinn, 2),
            h.article.url,
            h.article.agency.country.name
        ] for h in headlines],
            columns=[
                'title',
                'agency',
                'first_accessed',
                'last_accessed',
                'position',
                'vader_compound',
                'afinn',
                'url',
                'country'
            ])
        return HeadlinesPage.filter_score_sort(df)

    @staticmethod
    def filter_score_sort(df):
        df = df[df['country'].isin(['us', 'gb'])]
        # drop rows where country == gb and agency != The Economist, BBC, The Guardian
        df = df[~((df['country'] == 'gb') & (~df['agency'].isin(['The Economist', 'BBC', 'The Guardian'])))]
        # drop the sun
        df = df[~(df['agency'] == 'The Sun')]
        df = calculate_xkeyscore(df)
        # combine agency name and title Agency - Title
        df['title'] = df['agency'] + ' - ' + df['title']
        return df
