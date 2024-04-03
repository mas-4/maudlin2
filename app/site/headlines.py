import os

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
            df = self.get_headlines(s)
        def formattitle(x):
            t = x.title.replace("'", "").replace('"', '')
            t_trunc = t[:255] + '...' if len(t) > 255 else t
            return f'<a title="{t}" href="{x.url}">{x.agency} - {t_trunc}</a>'
        df['title'] = df.apply(formattitle, axis=1)
        def formattopic(x):
            if not x.topic:
                return ''
            topicfile = x.topic.replace(' ', '_') + '.html'
            return f'<a href="{topicfile}.html">{x.topic}</a>'
        df['topic'] = df.apply(formattopic, axis=1)
        # Truncate headline_df['title'] to 255 characters and append a ... if it is longer
        df = df[
            ['title', 'first_accessed', 'last_accessed', 'score', 'topic', 'vader_compound', 'afinn']
        ]
        df.sort_values(by='score', ascending=False, inplace=True)
        with open(os.path.join(Config.build, 'headlines.html'), 'wt') as f:
            f.write(self.template.render(
                title='Headlines',
                tabledata=df.values.tolist(),
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
            h.article.agency.country.name,
            '' if not h.article.topic else h.article.topic.name,
            '' if not h.article.topic else round(h.article.topic_score, 2)
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
                'country',
                'topic',
                'topic_score'
            ])
        return HeadlinesPage.filter_score_sort(df)

    @staticmethod
    def filter_score_sort(df):
        # df = df[df['country'].isin(['us', 'gb'])] Taken care of by query
        # drop rows where country == gb and agency != The Economist, BBC, The Guardian
        # df = df[~((df['country'] == 'gb') & (~df['agency'].isin(['The Economist', 'BBC', 'The Guardian'])))]
        # drop the sun
        df = df[~(df['agency'] == 'The Sun')]
        df = calculate_xkeyscore(df.copy())
        # combine agency name and title Agency - Title
        return df

if __name__ == '__main__':
    HeadlinesPage().generate()